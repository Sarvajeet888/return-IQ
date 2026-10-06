"""PHASE 31 — the customer return portal.

WHY THIS PHASE MATTERS MORE THAN ITS POSITION
---------------------------------------------
Every phase from 15 onward ends the same way: blocked on real data. The models
cannot be trained, benchmarked or evaluated because no labelled outcomes
exist, and none exist because no returns flow through the system.

This is the flywheel:

    Customer requests a return   -> features, with timestamps      (Phase 16)
    Reason and evidence captured -> provenance, hashes             (Phase 13)
    Pickup, transit, inspection  -> processing time                (Model G)
    Disposition decided          -> the decision label             (Model I)
    Actual cost and recovery     -> the money labels               (Models A, E)
    Fraud confirmed or not       -> the fraud label                (Model B)

Every arrow produces a row the current dataset does not have.

THE HARD PROBLEM: ACCESS WITHOUT ACCOUNTS
------------------------------------------
Customers do not have ReturnIQ logins and never will. Asking a shopper to
create an account to return a t-shirt is how a return portal goes unused, and
an unused portal generates no data.

So the endpoints are public, and public endpoints over other people's orders
are the most dangerous surface in the product. Three specific risks:

**Enumeration.** `GET /portal/orders/ORD-10001` with an incrementing suffix
walks a merchant's entire order book. Order IDs are merchant-chosen and often
sequential.

**Silent PII exposure.** A lookup that returns the customer's name, address
and phone to anyone holding an order number is a data breach with a
convenient interface.

**Cross-tenant confusion.** Order IDs are unique per merchant, not globally.
`ORD-1001` may exist at fifty merchants.

THE DESIGN
----------
Lookup requires **order ID plus a matching contact detail**. Knowing the order
number is not enough; you must already know something about the order. That
converts enumeration from "walk the sequence" into "guess the sequence and the
phone number", which is a different problem entirely.

A successful lookup issues a **scoped token** — valid for one return, for a
limited window, doing nothing else. Every subsequent action carries it.
Nothing in the portal accepts a bare order ID.

Responses are **minimised**: enough for the customer to recognise their own
order, never enough to profile someone else's.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

__all__ = [
    "PortalError",
    "LookupResult",
    "PORTAL_TOKEN_TTL",
    "normalise_contact",
    "contact_matches",
    "mask_contact",
    "issue_portal_token",
    "hash_portal_token",
    "minimise_order",
]


class PortalError(ValueError):
    """A portal request that cannot be served."""


# Short. The portal is a single sitting: look up an order, pick a reason,
# upload photos, done. A token that outlives the session is a credential
# sitting in a browser history or a shared device.
PORTAL_TOKEN_TTL: Final[timedelta] = timedelta(hours=2)

_TOKEN_BYTES: Final[int] = 32


def normalise_contact(value: str) -> str:
    """Reduce a phone number or email to a comparable form.

    Customers type their number differently from however the merchant's
    platform stored it: +91 98765 43210, 09876543210, 9876543210. Comparing
    raw strings would reject the legitimate customer while doing nothing to
    stop an attacker, who only needs one format to work.

    For phone numbers the last 10 digits are compared. India uses 10-digit
    subscriber numbers, and this tolerates country codes and leading zeros
    without treating them as different people.
    """
    if not value:
        return ""

    text = value.strip().lower()

    if "@" in text:
        return text

    digits = "".join(c for c in text if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def contact_matches(provided: str, stored: str) -> bool:
    """Constant-time comparison of normalised contact details.

    `compare_digest` rather than `==`. A plain comparison returns as soon as
    it finds a differing character, so response time leaks how many leading
    characters were correct — enough to recover a phone number digit by digit
    against an endpoint that will happily be called ten thousand times.
    """
    a = normalise_contact(provided)
    b = normalise_contact(stored)
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


def mask_contact(value: str) -> str:
    """Show enough for a customer to recognise their own detail, no more.

    Used in the "we've sent a link to ..." confirmation. Displaying the full
    address would let anyone holding an order number harvest it.
    """
    if not value:
        return ""

    if "@" in value:
        local, _, domain = value.partition("@")
        head = local[0] if local else ""
        return f"{head}{'*' * max(len(local) - 1, 3)}@{domain}"

    digits = "".join(c for c in value if c.isdigit())
    return f"{'*' * max(len(digits) - 4, 0)}{digits[-4:]}" if digits else ""


def issue_portal_token() -> str:
    """A single-return access token.

    256 bits from the OS CSPRNG. Not derived from the order ID or the return
    ID — a derived token is guessable by anyone who knows the derivation, and
    the derivation always leaks eventually.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_portal_token(raw: str) -> str:
    """SHA-256, stored instead of the token itself.

    Same reasoning as Phase 5's invitation tokens: this is a credential, so
    database read access must not become account access. SHA-256 rather than
    bcrypt because the token has 256 bits of entropy — brute force is not the
    threat model, and a slow hash on every portal request would be a
    self-inflicted denial of service.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LookupResult:
    found: bool
    order: dict[str, Any] | None
    token: str | None
    expires_at: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "order": self.order,
            "access_token": self.token,
            "expires_at": self.expires_at,
            "message": self.message,
        }


def minimise_order(order: dict[str, Any]) -> dict[str, Any]:
    """Strip an order down to what the customer needs to recognise it.

    The customer already knows their own name and address — showing it back
    adds nothing they need and everything an attacker wants. What they need is
    enough to confirm "yes, this is the order I mean": the item, roughly when,
    and its value.

    Explicitly excluded: customer_identifier, full address, internal IDs,
    fraud and risk scores, cost predictions, merchant margins. A customer who
    can see their own fraud score learns exactly which behaviour to avoid
    next time.
    """
    return {
        "order_reference": order.get("platform_order_id"),
        "item": order.get("sku"),
        "category": order.get("item_category"),
        "ordered_on": str(order.get("created_at", ""))[:10],
        "value": order.get("item_value"),
    }


def build_lookup_response(
    order: dict[str, Any] | None,
    provided_contact: str,
    *,
    now: datetime | None = None,
) -> LookupResult:
    """Decide what to return for an order lookup attempt.

    **The same response for "no such order" and "wrong contact detail."**
    Distinguishing them turns the endpoint into an order-number oracle: an
    attacker learns which numbers are real without needing the contact detail
    at all, and can then focus effort on those.

    This costs genuine usability — a customer who mistypes their phone number
    is told the order was not found, which is confusing. That trade is
    deliberate: the confused customer contacts support, while the alternative
    hands out a merchant's order book.
    """
    now = now or datetime.now(UTC)

    generic = LookupResult(
        found=False, order=None, token=None, expires_at=None,
        message=(
            "We could not find an order matching those details. Check the "
            "order number and the phone number or email used to place it."
        ),
    )

    if not order:
        return generic

    stored_contact = order.get("customer_identifier", "")
    if not contact_matches(provided_contact, stored_contact):
        return generic

    token = issue_portal_token()
    return LookupResult(
        found=True,
        order=minimise_order(order),
        token=token,
        expires_at=(now + PORTAL_TOKEN_TTL).isoformat(),
        message="Order found. You can start a return below.",
    )
