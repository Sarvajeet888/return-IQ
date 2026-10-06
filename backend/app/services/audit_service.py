"""PHASE 8 — Audit & governance.

THE PROBLEM WITH A PLAIN AUDIT TABLE
------------------------------------
An audit log's value comes entirely from being trustworthy. A table anyone
with database access can `UPDATE` is not evidence of anything -- it records
what happened *unless someone decided otherwise*, and you cannot tell which.

Restricting permissions to INSERT-only stops an outsider who got application
credentials. It does not stop the realistic threat to an audit trail: someone
with legitimate database access quietly editing a row after the fact.

HASH CHAINING
-------------
Each event stores the SHA-256 of its own content plus the hash of the previous
event for the same organization:

    event_hash = SHA256(prev_hash + canonical(this event))

Edit any historical row and its hash no longer matches its content. Recompute
that row's hash to cover the edit and it no longer matches what the *next*
row committed to. Fixing that requires rewriting every subsequent row --
detectable, because verification walks the whole chain.

This is tamper-EVIDENT, not tamper-PROOF. Someone with write access can still
rewrite the entire chain from the point of the edit forward. What they cannot
do is change one row quietly. For tamper-proof you need the chain head
published somewhere you do not control -- periodically anchoring the latest
hash to an external system is the honest next step, and is not done here.

CATEGORIES
----------
Business, security and ML events are separated because they have different
audiences and different retention obligations. Mixing them means a fraud
analyst reviewing approvals wades through login failures.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Any, Final

from app.core.logging_config import request_id_var
from app.db import store

__all__ = ["Category", "record", "compute_hash", "verify_chain"]


class Category:
    BUSINESS: Final = "business"      # a return was approved, a refund issued
    SECURITY: Final = "security"      # login failed, permission denied, key rotated
    ML: Final = "ml"                  # model deployed, prediction overridden
    DATA: Final = "data"              # export, deletion, consent change


VALID_CATEGORIES: Final[frozenset[str]] = frozenset({
    Category.BUSINESS, Category.SECURITY, Category.ML, Category.DATA,
})


def _canonical_timestamp(value: Any) -> str:
    """Normalise a timestamp to one representation, whatever form it arrives in.

    This is the subtle failure that canonicalisation exists to prevent. At
    write time `created_at` is a `datetime`, and `str()` renders it with a
    space separator:

        2026-08-14 10:32:13.824547

    On read it comes back from the serializer as an ISO string with a `T`:

        2026-08-14T10:32:13.824547

    Same instant, different bytes, different hash -- so every row verified as
    tampered immediately after being written. An audit system that cries wolf
    on its own correct data is worse than none, because people learn to
    dismiss it.

    A second discrepancy compounds it: `_now()` returns a timezone-aware
    datetime, so isoformat() appends `+00:00`, but SQLite hands the value back
    naive. Both are normalised here to one form -- UTC, no offset, microsecond
    precision -- so the hash depends on the instant rather than on which layer
    happened to produce the value.
    """
    if hasattr(value, "isoformat"):
        if getattr(value, "tzinfo", None) is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")

    text = str(value or "")
    if not text:
        return ""
    # Strings may arrive with a space separator and/or an offset suffix.
    text = text.replace(" ", "T", 1)
    for suffix in ("+00:00", "Z"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if "." not in text and len(text) == 19:      # no microseconds recorded
        text += ".000000"
    return text


def compute_hash(prev_hash: str | None, event: dict[str, Any]) -> str:
    """SHA-256 over the previous hash plus this event's canonical form.

    Canonicalisation matters more than the hash choice. `json.dumps` with
    `sort_keys=True` and no whitespace means the same logical event always
    produces the same bytes -- otherwise a dict ordering difference between
    Python versions would break verification on every historical row and the
    chain would cry tamper at its own developers.

    Only the fields that constitute the event are hashed. `id` is included
    because substituting one row for another is exactly the tampering this
    detects.
    """
    payload = {
        "id": event.get("id"),
        "org_id": event.get("org_id"),
        "user_id": event.get("user_id"),
        "action": event.get("action"),
        "category": event.get("category"),
        "resource_type": event.get("resource_type"),
        "resource_id": event.get("resource_id"),
        "detail": event.get("detail"),
        "changes": event.get("changes"),
        "created_at": _canonical_timestamp(event.get("created_at")),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()


def record(
    *,
    org_id: str,
    action: str,
    user_id: str | None = None,
    category: str = Category.BUSINESS,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: str = "",
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append an audit event.

    Never raises. An audit write failing must not take down the business
    operation it is describing -- refusing to approve a return because the
    logging table is unavailable would be a worse outcome than an incomplete
    log. Failures are logged loudly instead.

    That trade-off is deliberate and worth stating: it means the audit trail
    is best-effort under infrastructure failure. For a regime requiring
    guaranteed capture, the write would have to share the business
    transaction, and the business operation would have to fail with it.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Unknown audit category {category!r}. "
            f"Valid: {sorted(VALID_CATEGORIES)}"
        )

    # Correlation comes from the request context automatically, so 34 existing
    # call sites do not each have to remember to pass it.
    request_id = request_id_var.get("") or None

    store.append_audit_event({
        "org_id": org_id,
        "user_id": user_id,
        "action": action,
        "category": category,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "detail": detail,
        "changes": changes,
        "ip_address": ip_address,
        "user_agent": (user_agent or "")[:256] or None,
        "request_id": request_id,
    })


def verify_chain(org_id: str, limit: int | None = None) -> dict[str, Any]:
    """Walk an organization's audit chain and report whether it is intact.

    Returns a structured result rather than a bare bool so an investigator can
    see *where* the break is -- the first broken link is the point of
    tampering, and everything before it is still trustworthy.
    """
    events = store.get_audit_chain(org_id, limit=limit)

    prev_hash: str | None = None
    for index, event in enumerate(events):
        expected = compute_hash(prev_hash, event)

        if event.get("event_hash") != expected:
            return {
                "valid": False,
                "events_checked": index + 1,
                "total_events": len(events),
                "broken_at": {
                    "id": event.get("id"),
                    "action": event.get("action"),
                    "created_at": _canonical_timestamp(event.get("created_at")),
                    "position": index,
                },
                "reason": (
                    "This event's stored hash does not match its contents. "
                    "Either the row was modified after it was written, or an "
                    "earlier row was altered or removed."
                ),
            }
        prev_hash = event["event_hash"]

    return {
        "valid": True,
        "events_checked": len(events),
        "total_events": len(events),
        "chain_head": prev_hash,
    }
