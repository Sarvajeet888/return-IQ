"""PHASE 33 — integration platform: webhook security.

THE VULNERABILITY THIS FIXES
----------------------------
`webhook_url` was `Optional[str]` with no validation. Verified against the
running API — every one of these returned **200 OK**:

    http://169.254.169.254/latest/meta-data/iam/security-credentials/
    http://127.0.0.1:8000/api/v1/admin/orgs
    http://10.0.0.5:5432/
    file:///etc/passwd
    banana

The first is the serious one. `169.254.169.254` is the cloud instance metadata
endpoint on AWS, GCP and Azure. A merchant — or anyone who compromises one
merchant account — sets that as their webhook URL, and ReturnIQ's own server
fetches **the IAM credentials of the machine it runs on** and delivers them to
an attacker-controlled destination.

That is server-side request forgery, and a webhook field is its classic
vector: the whole feature is "the customer tells us a URL and we make requests
to it".

WHY THIS IS DIFFERENT FROM ORDINARY INPUT VALIDATION
----------------------------------------------------
A blocklist of bad hostnames does not work, and reaching for one is the usual
mistake. `169.254.169.254` has many equivalent spellings: `0251.0376.0376.0376`
in octal, `2852039166` as a decimal integer, `[::ffff:169.254.169.254]` in
IPv6, or any attacker-controlled DNS name with an A record pointing there.

So the check is on the **resolved address**, not the string — and it is an
allowlist of what may be reached (public unicast addresses) rather than a
blocklist of what may not.

THE REMAINING GAP, STATED HONESTLY
----------------------------------
Resolving at validation time and connecting later leaves a DNS rebinding
window: the name resolves to a public address when checked and a private one
when fetched. Closing it properly requires resolving once and connecting to
that pinned IP, which belongs in the HTTP client rather than here.
`PINNING_REQUIRED` documents that, and the delivery layer is where it must be
implemented.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlparse

__all__ = [
    "WebhookUrlError",
    "PINNING_REQUIRED",
    "validate_webhook_url",
    "sign_payload",
    "verify_signature",
    "SIGNATURE_TOLERANCE_SECONDS",
]


class WebhookUrlError(ValueError):
    """A webhook URL that must not be called."""


# Only https. A webhook carries return data, customer identifiers and
# sometimes signed URLs; delivering that over plaintext hands it to anyone on
# the path. Allowing http "for testing" means it reaches production.
_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"https"})

# Ports that are almost never a legitimate webhook receiver but are very
# commonly an internal service. Blocked in addition to the address checks, as
# defence in depth for a public host that also exposes a database.
_BLOCKED_PORTS: Final[frozenset[int]] = frozenset({
    22, 23, 25, 445, 1433, 3306, 5432, 6379, 9200, 11211, 27017,
})

SIGNATURE_TOLERANCE_SECONDS: Final[int] = 300

# Documented, not implemented here. See the module docstring.
PINNING_REQUIRED: Final[str] = (
    "The delivery client must resolve the hostname once and connect to that "
    "pinned IP. Validating a name here and resolving it again at request time "
    "leaves a DNS rebinding window: the name can answer with a public address "
    "when checked and a private one when fetched."
)


def _parse_literal_address(
    host: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Recognise an address literal in any spelling the OS resolver accepts.

    `ipaddress.ip_address()` alone is NOT sufficient, and assuming it was
    let two evasions through in my first version:

        https://0251.0376.0376.0376/   octal          -> 169.254.254.254
        https://2852039166/            decimal integer -> 169.254.169.254

    Both are rejected by `ip_address()` and both are happily resolved by
    `inet_aton()`, which is what the operating system actually uses. So a URL
    that this function called "a hostname" would have been passed to the
    resolver and connected straight to the cloud metadata endpoint.

    `inet_aton` is therefore consulted as well — it is the more permissive
    parser, and the safe check is the one that matches whatever will really
    be dialled.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass

    # Reject anything inet_aton would accept as IPv4, including the shorthand
    # and non-decimal forms. A genuine hostname contains at least one
    # character that is neither a digit nor a dot.
    if all(c.isdigit() or c == "." for c in host):
        try:
            return ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host)))
        except OSError:
            pass

    # Bracketed IPv6, e.g. [::ffff:169.254.169.254]
    stripped = host.strip("[]")
    if stripped != host:
        try:
            address = ipaddress.ip_address(stripped)
            # An IPv4-mapped IPv6 address is the IPv4 address wearing a
            # costume; check what it actually points at.
            mapped = getattr(address, "ipv4_mapped", None)
            return mapped or address
        except ValueError:
            pass

    return None


def _is_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Is this address safe to send a request to?

    An allowlist of properties rather than a blocklist of ranges. `is_private`
    alone misses loopback, link-local (which is where cloud metadata lives),
    reserved and multicast — and the point of link-local is precisely the
    address that leaks credentials.
    """
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_webhook_url(url: str, *, resolve: bool = True) -> str:
    """Refuse any URL that could reach something other than the open internet.

    `resolve=False` exists for tests and offline validation. It is not a
    convenience flag for production: without resolution this checks only the
    literal string, and a hostname is exactly how an attacker avoids writing
    a literal address.
    """
    if not url or not url.strip():
        raise WebhookUrlError("A webhook URL is required.")

    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise WebhookUrlError(
            f"Webhook URLs must use https. {parsed.scheme or 'no'} scheme is "
            f"not allowed — webhooks carry return and customer data, and "
            f"plaintext delivery hands it to anyone on the network path."
        )

    if not parsed.hostname:
        raise WebhookUrlError("That is not a valid URL.")

    host = parsed.hostname

    if parsed.port and parsed.port in _BLOCKED_PORTS:
        raise WebhookUrlError(
            f"Port {parsed.port} is a database or administrative service, not "
            f"a webhook receiver."
        )

    literal = _parse_literal_address(host)

    if literal is not None:
        if not _is_public_address(literal):
            raise WebhookUrlError(
                f"{host} is not a public address. Webhooks cannot be sent to "
                f"private networks, loopback, or cloud metadata endpoints — "
                f"that would make ReturnIQ's server fetch internal resources "
                f"on your behalf."
            )
        return url.strip()

    if not resolve:
        return url.strip()

    try:
        # Every address the name resolves to, not just the first. A hostname
        # with both a public and a private A record would otherwise pass on
        # whichever the resolver happened to return.
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise WebhookUrlError(
            f"{host} could not be resolved. Check the address is correct and "
            f"publicly reachable."
        ) from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not _is_public_address(address):
            raise WebhookUrlError(
                f"{host} resolves to {address}, which is not a public "
                f"address. Webhooks cannot be sent to private networks, "
                f"loopback, or cloud metadata endpoints."
            )

    return url.strip()


# ─────────────────────────────── signing ─────────────────────────────────────

@dataclass(frozen=True)
class Signature:
    timestamp: int
    value: str

    def header(self) -> str:
        return f"t={self.timestamp},v1={self.value}"


def sign_payload(payload: bytes, secret: str, *, timestamp: int | None = None) -> Signature:
    """Sign an outbound webhook so the receiver can verify it came from us.

    **The timestamp is inside the signed material, not merely alongside it.**
    Signing the body alone lets an attacker replay a captured delivery
    forever, and lets them attach any timestamp they like to make it look
    fresh — the signature would still verify.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return Signature(timestamp=ts, value=digest)


def verify_signature(
    payload: bytes,
    header: str,
    secret: str,
    *,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
    now: int | None = None,
) -> bool:
    """Verify an inbound webhook.

    This is the more dangerous direction. An unverified inbound webhook lets
    anyone who guesses the endpoint create returns, change statuses or trigger
    refunds in a merchant's account — with no credential at all.

    Three checks, all required:
      1. the signature matches the body **and** the timestamp
      2. the timestamp is recent (replay window)
      3. the comparison is constant-time
    """
    if not header or not secret:
        return False

    parts = dict(
        piece.split("=", 1) for piece in header.split(",") if "=" in piece
    )
    raw_ts, provided = parts.get("t"), parts.get("v1")
    if not raw_ts or not provided:
        return False

    try:
        ts = int(raw_ts)
    except ValueError:
        return False

    current = now if now is not None else int(time.time())

    # Rejected in both directions. A far-future timestamp is not a clock skew
    # problem; it is someone extending their own replay window.
    if abs(current - ts) > tolerance_seconds:
        return False

    expected = sign_payload(payload, secret, timestamp=ts).value

    # compare_digest, not ==. A plain comparison returns as soon as it finds a
    # differing character, so response time leaks how many leading hex digits
    # were correct — enough to forge a signature byte by byte against an
    # endpoint that will happily be called a million times.
    return hmac.compare_digest(expected, provided)


def delivery_headers(payload: bytes, secret: str) -> dict[str, str]:
    """Headers for an outbound delivery."""
    signature = sign_payload(payload, secret)
    return {
        "Content-Type": "application/json",
        "X-ReturnIQ-Signature": signature.header(),
        "User-Agent": "ReturnIQ-Webhooks/1.0",
    }


def redact_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip customer identifiers before a delivery is logged.

    Webhook delivery logs are read during debugging, often by whoever is
    available, and are retained far longer than anyone intends. A log that
    contains the full payload is a second copy of customer data with weaker
    access controls than the database it came from.
    """
    sensitive = {
        "customer_identifier", "customer_phone", "customer_email",
        "customer_name", "delivery_address", "origin_pincode",
        "destination_pincode",
    }
    return {
        k: ("[redacted]" if k in sensitive else v)
        for k, v in payload.items()
    }
