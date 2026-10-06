"""PHASE 31 — public return portal endpoints.

These are the only unauthenticated routes in ReturnIQ that touch customer
data. Everything here is written on the assumption that the caller is
hostile, because some of them will be.

Design notes are on each endpoint. The three that matter most:

  1. Lookup needs order ID **and** a matching contact detail.
  2. "Not found" and "wrong contact" return the identical response.
  3. Every subsequent action requires the scoped token, never an order ID.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.lifecycle import ReturnStatus
from app.core.money import Money
from app.core.rate_limit import limiter
from app.db import store
from app.services import audit_service, evidence_service, portal_service

router = APIRouter(tags=["portal"])


# ─────────────────────────────── schemas ─────────────────────────────────────

class PortalLookupRequest(BaseModel):
    order_reference: str = Field(..., min_length=1, max_length=100)
    # Phone or email — whichever the customer used. Accepting either avoids a
    # dropdown the customer will get wrong.
    contact: str = Field(..., min_length=3, max_length=255)


class PortalReturnRequest(BaseModel):
    reason_code: str = Field(..., min_length=2, max_length=50)
    # Free text, capped. Customers explain things the reason codes do not
    # cover, and that text is a genuine signal (Phase 23) — but an uncapped
    # field on a public endpoint is a storage attack.
    comment: str = Field(default="", max_length=2000)


def _org_from_request(
    x_returniq_org: str | None = Header(default=None),
) -> str:
    """Which merchant's portal is this?

    Supplied by the merchant's embed configuration, never by the customer.
    A customer-controlled org would let anyone query any merchant's orders by
    changing a header — the portal equivalent of removing tenant isolation.

    In production this resolves from the portal subdomain or a signed embed
    key; the header is the development form.
    """
    if not x_returniq_org:
        raise HTTPException(
            status_code=400,
            detail="This return portal is not configured correctly. Please "
                   "contact the store you ordered from.",
        )
    return x_returniq_org


def _session_or_401(token: str | None) -> dict:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Your session has ended. Please look up your order again.",
        )
    session = store.get_portal_session(
        portal_service.hash_portal_token(token), datetime.now(UTC),
    )
    if not session:
        # One message for expired, revoked and never-existed. Distinguishing
        # them tells an attacker whether a token was ever real.
        raise HTTPException(
            status_code=401,
            detail="Your session has ended. Please look up your order again.",
        )
    return session


# ─────────────────────────────── endpoints ───────────────────────────────────

@router.post("/api/v1/portal/lookup")
@limiter.limit("10/minute")
async def portal_lookup(
    request: Request,
    payload: PortalLookupRequest,
    org_id: str = Depends(_org_from_request),
) -> dict:
    """Find an order using its reference plus a matching contact detail.

    **Rate limited hard.** This is the enumeration surface: order references
    are merchant-chosen and frequently sequential, so an unthrottled endpoint
    walks a merchant's entire order book. Ten a minute is generous for a human
    typing their own order number and useless for a script.

    **Identical response for "no such order" and "wrong contact detail."**
    Distinguishing them turns this into an order-number oracle — an attacker
    learns which references are real without ever guessing a phone number.

    The cost is real: a customer who mistypes their number is told the order
    was not found, which is confusing. That trade is deliberate. The confused
    customer contacts support; the alternative hands out the order book.
    """
    order = store.find_order_for_portal(org_id, payload.order_reference.strip())
    result = portal_service.build_lookup_response(order, payload.contact)

    if result.found and result.token:
        store.create_portal_session({
            "token_hash": portal_service.hash_portal_token(result.token),
            "org_id": org_id,
            "platform_order_id": payload.order_reference.strip(),
            "expires_at": datetime.now(UTC) + portal_service.PORTAL_TOKEN_TTL,
        })

        audit_service.record(
            org_id=org_id,
            action="portal_lookup_succeeded",
            category=audit_service.Category.SECURITY,
            resource_type="order",
            resource_id=payload.order_reference.strip(),
            detail="A customer opened the return portal for this order.",
        )

    return result.as_dict()


@router.post("/api/v1/portal/returns", status_code=201)
@limiter.limit("5/minute")
async def portal_create_return(
    request: Request,
    payload: PortalReturnRequest,
    org_id: str = Depends(_org_from_request),
    x_portal_token: str | None = Header(default=None),
) -> dict:
    """Start a return for the order this session was issued against.

    The order comes from the **session**, never from the request body. A body
    parameter would let a customer look up their own order, then submit a
    return against somebody else's — the classic mistake in
    token-scoped flows.
    """
    session = _session_or_401(x_portal_token)

    if session["org_id"] != org_id:
        # A token issued on one merchant's portal, presented on another's.
        raise HTTPException(status_code=401, detail="Your session has ended.")

    if session.get("return_request_id"):
        raise HTTPException(
            status_code=409,
            detail="A return has already been started for this order. Use the "
                   "tracking link to see its progress.",
        )

    order = store.find_order_for_portal(org_id, session["platform_order_id"])
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    return_id = str(uuid.uuid4())
    store.store_return({
        **{k: v for k, v in order.items() if k not in {"id", "status", "created_at"}},
        "id": return_id,
        "org_id": org_id,
        "return_reason_code": payload.reason_code.strip().lower(),
        "status": ReturnStatus.PENDING,
        "created_at": datetime.now(UTC),
        # Customer-stated condition, recorded as claimed rather than assessed.
        # Phase 23 compares this against the evidence and flags contradictions.
        "condition": "unknown",
    })

    if payload.comment.strip():
        # Stored as evidence, not as a staff note.
        #
        # `return_notes.user_id` is NOT NULL — the table models internal
        # commentary by a named person, and a customer is not one. Relaxing
        # that constraint to accommodate the portal would erode the meaning of
        # every existing row: "who wrote this" would become answerable only
        # sometimes, and a note whose author is unknown is exactly the note an
        # auditor asks about.
        #
        # The customer's own words are their account of what happened, which
        # is what the evidence layer is for — and Phase 23 already compares
        # stated reason against the rest of the signals.
        store.store_return_document({
            "id": str(uuid.uuid4()),
            "return_request_id": return_id,
            "org_id": org_id,
            "uploaded_by_user_id": None,
            "file_name": "customer_statement.txt",
            "file_type": "text/plain",
            "declared_file_type": "text/plain",
            "file_size_bytes": len(payload.comment.strip().encode("utf-8")),
            "storage_key": "",
            "is_damage_photo": False,
            "content_sha256": evidence_service.content_hash(
                payload.comment.strip().encode("utf-8")
            ),
            "source": evidence_service.EvidenceSource.CUSTOMER,
            "evidence_type": evidence_service.EvidenceType.OTHER,
            "created_at": datetime.now(UTC),
            "customer_statement": payload.comment.strip(),
        })

    store.bind_portal_session_to_return(
        portal_service.hash_portal_token(x_portal_token), return_id,
    )

    audit_service.record(
        org_id=org_id,
        action="portal_return_created",
        resource_type="return",
        resource_id=return_id,
        detail=f"Customer started a return: {payload.reason_code}",
    )

    return {
        "return_id": return_id,
        "status": ReturnStatus.PENDING,
        "message": (
            "Your return request has been received. Add photos below if the "
            "item arrived damaged — it helps us process this faster."
        ),
    }


@router.get("/api/v1/portal/returns/{return_id}/status")
@limiter.limit("30/minute")
async def portal_track_return(
    request: Request,
    return_id: str,
    org_id: str = Depends(_org_from_request),
    x_portal_token: str | None = Header(default=None),
) -> dict:
    """Track a return.

    Deliberately narrow. A customer needs to know where their return is and
    what happens next — not the fraud score, not the predicted cost, not the
    disposition recommendation. A customer who can see their own fraud score
    learns precisely which behaviour to avoid next time, which degrades the
    signal for every merchant on the platform.
    """
    session = _session_or_401(x_portal_token)

    if session["org_id"] != org_id or session.get("return_request_id") != return_id:
        raise HTTPException(status_code=401, detail="Your session has ended.")

    r = store.get_return_by_id(return_id)
    if not r or r.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="Return not found.")

    friendly = {
        ReturnStatus.PENDING: "Received — we're reviewing your request",
        ReturnStatus.PREDICTION_DONE: "Received — we're reviewing your request",
        ReturnStatus.UNDER_REVIEW: "Being reviewed by our team",
        ReturnStatus.APPROVED: "Approved — we'll arrange collection",
        ReturnStatus.REJECTED: "Not approved — please contact support",
        ReturnStatus.PICKUP_SCHEDULED: "Collection scheduled",
        ReturnStatus.IN_TRANSIT: "On its way back to us",
        ReturnStatus.RECEIVED: "Received at our warehouse",
        ReturnStatus.INSPECTION: "Being checked by our team",
        ReturnStatus.REFUNDED: "Refunded",
        ReturnStatus.CLOSED: "Completed",
        ReturnStatus.CANCELLED: "Cancelled",
    }

    return {
        "return_id": return_id,
        "status": friendly.get(r.get("status", ""), "In progress"),
        "requested_on": str(r.get("created_at", ""))[:10],
        "item": r.get("sku"),
    }
