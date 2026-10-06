"""PHASE 33 — webhook security.

Two surfaces: outbound URLs a merchant configures (SSRF), and inbound
deliveries anyone can attempt (forgery and replay).
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from app.services.webhook_security import (
    SIGNATURE_TOLERANCE_SECONDS,
    WebhookUrlError,
    redact_for_log,
    sign_payload,
    validate_webhook_url,
    verify_signature,
)


def _valid(url: str) -> str:
    return validate_webhook_url(url, resolve=False)


# ──────────────────────────── SSRF defence ───────────────────────────────────

def test_the_cloud_metadata_endpoint_is_refused():
    """THE vulnerability.

    169.254.169.254 is the instance metadata endpoint on AWS, GCP and Azure.
    A merchant setting it as their webhook URL makes ReturnIQ's own server
    fetch the IAM credentials of the machine it runs on and deliver them to an
    attacker-controlled destination.
    """
    with pytest.raises(WebhookUrlError, match="not a public address"):
        _valid("https://169.254.169.254/latest/meta-data/")


def test_octal_and_decimal_spellings_are_also_refused():
    """A blocklist of hostnames does not work, and reaching for one is the
    usual mistake.

    Both of these resolve to link-local addresses, and BOTH passed my first
    version — `ipaddress.ip_address()` rejects them while `inet_aton()`, which
    is what the OS resolver actually uses, resolves them happily:

        0251.0376.0376.0376  -> 169.254.254.254
        2852039166           -> 169.254.169.254
    """
    for spelling in ("https://0251.0376.0376.0376/", "https://2852039166/"):
        with pytest.raises(WebhookUrlError, match="not a public address"):
            _valid(spelling)


def test_ipv4_mapped_ipv6_is_refused():
    """An IPv4-mapped IPv6 address is the IPv4 address wearing a costume."""
    with pytest.raises(WebhookUrlError):
        _valid("https://[::ffff:169.254.169.254]/hook")


def test_shorthand_addresses_are_refused():
    with pytest.raises(WebhookUrlError):
        _valid("https://127.1/hook")


def test_loopback_and_private_networks_are_refused():
    for url in (
        "https://127.0.0.1:8000/hook",
        "https://10.0.0.5/hook",
        "https://192.168.1.1/hook",
        "https://172.16.0.1/hook",
        "https://[::1]/hook",
    ):
        with pytest.raises(WebhookUrlError):
            _valid(url)


def test_plaintext_http_is_refused():
    """Webhooks carry return data and customer identifiers. Allowing http
    'for testing' means it reaches production."""
    with pytest.raises(WebhookUrlError, match="must use https"):
        _valid("http://example.com/hook")


def test_non_http_schemes_are_refused():
    for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://example.com/"):
        with pytest.raises(WebhookUrlError, match="must use https"):
            _valid(url)


def test_database_ports_are_refused():
    """Defence in depth for a public host that also exposes a database."""
    for port in (5432, 3306, 6379, 27017):
        with pytest.raises(WebhookUrlError, match="not a webhook receiver"):
            _valid(f"https://example.com:{port}/hook")


def test_nonsense_is_refused():
    with pytest.raises(WebhookUrlError):
        _valid("banana")
    with pytest.raises(WebhookUrlError):
        _valid("")


def test_legitimate_urls_are_accepted():
    """The validator must not block real integrations, or merchants route
    around it."""
    assert _valid("https://hooks.example.com/returniq")
    assert _valid("https://api.merchant.co.in/webhooks/returns?v=2")
    assert _valid("https://93.184.216.34/hook")          # a public literal


def test_resolution_is_on_by_default():
    """A hostname is exactly how an attacker avoids writing a literal
    address, so `resolve=False` must not be the default."""
    import inspect
    assert inspect.signature(validate_webhook_url).parameters["resolve"].default is True


# ─────────────────────── inbound: forgery and replay ─────────────────────────

def test_a_valid_signature_verifies():
    payload = json.dumps({"event": "return.created"}).encode()
    header = sign_payload(payload, "secret").header()
    assert verify_signature(payload, header, "secret") is True


def test_a_tampered_body_fails():
    """The reason to verify at all: an unverified inbound webhook lets anyone
    who guesses the endpoint create returns or trigger refunds in a merchant's
    account, with no credential."""
    header = sign_payload(b'{"amount":100}', "secret").header()
    assert verify_signature(b'{"amount":99999}', header, "secret") is False


def test_the_wrong_secret_fails():
    payload = b'{"event":"x"}'
    header = sign_payload(payload, "secret-a").header()
    assert verify_signature(payload, header, "secret-b") is False


def test_an_old_delivery_is_rejected():
    """Replay defence. Without a window, a captured delivery is valid
    forever."""
    payload = b'{"event":"x"}'
    old = int(time.time()) - SIGNATURE_TOLERANCE_SECONDS - 60
    header = sign_payload(payload, "secret", timestamp=old).header()
    assert verify_signature(payload, header, "secret") is False


def test_a_future_timestamp_is_rejected():
    """Not a clock-skew allowance — a far-future timestamp is someone
    extending their own replay window."""
    payload = b'{"event":"x"}'
    future = int(time.time()) + SIGNATURE_TOLERANCE_SECONDS + 60
    header = sign_payload(payload, "secret", timestamp=future).header()
    assert verify_signature(payload, header, "secret") is False


def test_the_timestamp_is_inside_the_signed_material():
    """Signing the body alone would let an attacker attach any timestamp they
    like to a captured payload and have it verify as fresh."""
    payload = b'{"event":"x"}'
    signature = sign_payload(payload, "secret", timestamp=1_000_000)

    forged = f"t={int(time.time())},v1={signature.value}"
    assert verify_signature(payload, forged, "secret") is False


def test_a_malformed_header_fails_closed():
    payload = b'{"event":"x"}'
    for header in ("", "garbage", "t=abc,v1=def", "v1=onlysignature", "t=123"):
        assert verify_signature(payload, header, "secret") is False


def test_a_missing_secret_fails_closed():
    payload = b'{"event":"x"}'
    header = sign_payload(payload, "secret").header()
    assert verify_signature(payload, header, "") is False


def test_signatures_differ_per_payload_and_per_timestamp():
    a = sign_payload(b"one", "secret", timestamp=1000).value
    b = sign_payload(b"two", "secret", timestamp=1000).value
    c = sign_payload(b"one", "secret", timestamp=2000).value
    assert len({a, b, c}) == 3


# ──────────────────────────── log hygiene ────────────────────────────────────

def test_customer_identifiers_are_redacted_from_delivery_logs():
    """Delivery logs are read during debugging by whoever is available, and
    retained far longer than anyone intends. A log containing the full payload
    is a second copy of customer data with weaker access controls than the
    database it came from."""
    redacted = redact_for_log({
        "return_id": "RI-1",
        "customer_identifier": "9876543210",
        "delivery_address": "12 MG Road, Pune",
        "status": "approved",
    })

    assert redacted["return_id"] == "RI-1"
    assert redacted["status"] == "approved"
    assert redacted["customer_identifier"] == "[redacted]"
    assert redacted["delivery_address"] == "[redacted]"


# ──────────────────────────── end-to-end ─────────────────────────────────────

def test_the_settings_endpoint_refuses_hostile_urls(app_client):
    """Verified against the running API before the fix: every one of these
    returned 200 OK."""
    email = f"hook_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Hook Tester", "email": email, "password": "HookPass123",
        "org_name": f"Hook Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1:8000/api/v1/admin/orgs",
        "file:///etc/passwd",
        "banana",
    ):
        resp = app_client.patch("/api/v1/org/settings", headers=headers,
                                json={"webhook_url": url})
        assert resp.status_code == 422, f"{url} was accepted"


def test_the_settings_endpoint_accepts_a_real_url(app_client):
    email = f"hook_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Hook Tester", "email": email, "password": "HookPass123",
        "org_name": f"Hook Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = app_client.patch("/api/v1/org/settings", headers=headers,
                            json={"webhook_url": "https://example.com/returniq"})
    assert resp.status_code == 200, resp.text
