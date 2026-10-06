"""
Returns API — fully backward-compatible with v2, enhanced with enterprise features.
Both JWT auth (dashboard) and X-API-Key (external integrations) are supported.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.lifecycle import (
    InvalidTransition,
    is_terminal,
    next_statuses,
    validate_transition,
)
from app.core.money import Money
from app.api.v1.deps import get_current_org, get_current_user, get_org_from_api_key
from app.core.cache import cached
from app.db import store
from app.services import audit_service
from app.schemas.schemas import PredictionOutcomeSubmit, ReturnRequestCreate, ReturnStatusUpdate
from app.services.feature_mapping import build_feature_dict, check_unmapped_features
from app.services.ml_service import score_return
from app.services.workflow_service import apply_workflow_rules

router = APIRouter(tags=["returns"])


def _get_owned_return_or_404(return_id: str, org: dict) -> dict:
    """Fetch a return and enforce org ownership in one place.

    Was previously copy-pasted in three route handlers (GET by id, PATCH
    status, and the API-key GET-by-id variant) - a security-relevant check
    like this is exactly the kind of thing that's easy to accidentally
    weaken in only one of several copies during a future edit.
    """
    r = store.get_return_by_id(return_id)
    if not r or (r.get("org_id") != org["id"] and r.get("merchant_id") != org["id"]):
        raise HTTPException(status_code=404, detail="Return not found")
    return r


def _build_return_record(payload: ReturnRequestCreate, org: dict, return_id: str, now: datetime) -> dict:
    """Map the incoming request payload onto the stored return-request shape."""
    return {
        "id": return_id,
        "org_id": org["id"],
        "merchant_id": org["id"],  # backward compat
        "platform_order_id": payload.platform_order_id,
        "customer_identifier": payload.customer_identifier,
        "sku": payload.sku,
        "item_category": payload.item_category,
        # Convert once, at the boundary. payload.item_value is a Decimal.
        "item_value_minor": Money.from_major(payload.item_value, payload.currency).minor_units,
        "currency": payload.currency,
        "origin_pincode": payload.origin_pincode,
        "destination_pincode": payload.destination_pincode,
        "weight_grams": payload.weight_grams,
        "volumetric_weight_grams": payload.volumetric_weight_grams,
        "return_reason_code": payload.return_reason_code,
        "courier": payload.courier,
        "payment_mode": payload.payment_mode,
        "fragile": payload.fragile,
        "festive": payload.festive,
        "condition": payload.condition or "good",
        "customer_notes": payload.customer_notes,
        "raw_payload": payload.raw_payload,
        "status": "pending",
        "created_at": now,
    }


def _score_return_record(payload: ReturnRequestCreate, return_data: dict, org: dict) -> dict:
    """Build ML features from the return record and run the scoring pipeline.
    Raises HTTPException(502) if the ML service itself fails, so callers
    don't need to know anything about the scoring internals."""
    customer_count = store.count_customer_returns(payload.customer_identifier, org["id"])
    org_count = store.count_org_returns(org["id"])
    features = build_feature_dict(return_data, customer_count, org_count)
    try:
        return score_return(
            features=features,
            item_value=float(payload.item_value),  # ml_service scores in float; money is persisted exactly below
            risk_threshold=float(org.get("risk_threshold", 50.0)),
            condition=payload.condition,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ML scoring failed: {exc}")


# Fields exposed on the `prediction` sub-object returned to API callers -
# everything in pred_data except bookkeeping fields (id, return_request_id,
# feature_snapshot, which are internal/verbose and not part of the public
# response shape).
_PREDICTION_RESPONSE_FIELDS = (
    "predicted_cost_minor", "currency", "risk_score", "fraud_score",
    "damage_probability", "resale_value_estimate_minor",
    "carbon_footprint_kg", "confidence_score",
    "routing_decision", "model_version", "inference_latency_ms", "explainability",
)


def _build_prediction_record(
    return_id: str, result: dict, now: datetime, currency: str = "INR"
) -> dict:
    """Map a score_return() result onto the stored prediction shape.

    Currency is passed in explicitly rather than read from an outer scope --
    the prediction must be denominated in the same currency as the return it
    belongs to, and defaulting silently would mislabel non-INR orgs.
    """
    return {
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "predicted_cost_minor": Money.from_major(result["predicted_cost_inr"], currency).minor_units,
        "currency": currency,
        "risk_score": float(result["risk_score"]),
        "fraud_score": float(result["fraud_score"]),
        "damage_probability": result["damage_probability"],
        "resale_value_estimate_minor": Money.from_major(result["resale_value_estimate"], currency).minor_units,
        "carbon_footprint_kg": result["carbon_footprint_kg"],
        "confidence_score": result["confidence_score"],
        "routing_decision": result["routing_decision"].value,
        "model_version": result["model_version"],
        "inference_latency_ms": result["inference_latency_ms"],
        "feature_snapshot": result["feature_snapshot"],
        "explainability": result["explainability"],
        "created_at": now,
    }


def _notify_if_high_fraud(org: dict, payload: ReturnRequestCreate, result: dict) -> None:
    if float(result["fraud_score"]) < 70:
        return
    store.add_notification({
        "org_id": org["id"],
        "type": "fraud_alert",
        "title": "🚨 High Fraud Risk Detected",
        "message": f"Return {payload.platform_order_id} flagged with fraud score {float(result['fraud_score']):.0f}/100",
        "severity": "critical",
    })


def _score_and_store(payload: ReturnRequestCreate, org: dict) -> dict:
    """Core scoring logic — shared between JWT and API key flows."""
    return_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    return_data = _build_return_record(payload, org, return_id, now)
    result = _score_return_record(payload, return_data, org)

    return_data["status"] = "prediction_done"
    store.store_return(return_data)

    pred_data = _build_prediction_record(return_id, result, now, payload.currency)
    store.store_prediction(pred_data)

    _notify_if_high_fraud(org, payload, result)

    # Phase 5.12: Apply workflow automation rules immediately after scoring.
    # Rules can auto-approve, auto-reject, set SLA, or escalate.
    workflow_applied = apply_workflow_rules(
        return_id=return_id,
        return_data=return_data,
        pred_data=pred_data,
        org=org,
    )

    response = {
        **return_data,
        "prediction": {k: pred_data[k] for k in _PREDICTION_RESPONSE_FIELDS},
        "workflow_rules_applied": workflow_applied,
    }

    # Phase 9.7: tell the caller if any categorical value fell outside the
    # model's training vocabulary. Those features are silently dropped to
    # all-zeros during one-hot encoding, so the prediction still returns a
    # confident-looking number while actually being less accurate. Callers
    # deserve to know that rather than discovering it from bad outcomes.
    data_warnings = check_unmapped_features(return_data)
    if data_warnings:
        response["data_quality_warnings"] = data_warnings

    return response


# ── JWT-authenticated routes (dashboard) ──────────────────────────────────────
@router.post("/api/v1/returns", status_code=201)
async def create_return_jwt(
    payload: ReturnRequestCreate,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    result = _score_and_store(payload, org)
    store.add_audit_log({"org_id": org["id"], "user_id": user["id"], "action": "create", "detail": f"Return {payload.platform_order_id} submitted"})
    return result


@router.get("/api/v1/returns/dashboard")
@cached(ttl_seconds=30, key_prefix="dashboard")
async def get_dashboard(org: dict = Depends(get_current_org)) -> dict:
    # PHASE 39: measured before caching this. 800 returns in SQLite: 26-35ms
    # typical, one run at 141ms. Recomputed from scratch on every request,
    # exactly as cache.py's own docstring already said -- it was just never
    # applied. Invalidated automatically whenever a return is written
    # (see store.store_return), so this never serves stale data past a
    # single write's round trip.
    return store.get_dashboard_stats(org["id"])


@router.get("/api/v1/returns/analytics")
@cached(ttl_seconds=120, key_prefix="analytics")
async def get_analytics(org: dict = Depends(get_current_org)) -> dict:
    # 120s, not 30s: analytics is a heavier aggregation (46-51ms measured)
    # and less time-sensitive than the headline dashboard numbers -- matches
    # the TTL guidance already written in cache.py's own comments.
    return store.get_analytics_data(org["id"])


@router.get("/api/v1/returns")
async def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    decision: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    org: dict = Depends(get_current_org),
) -> dict:
    filters = {}
    if status:
        filters["status"] = status
    if decision:
        filters["decision"] = decision
    if category:
        filters["category"] = category

    all_returns = store.get_returns_for_org(org["id"], filters)

    if search:
        q = search.lower()
        all_returns = [
            r for r in all_returns
            if q in r.get("platform_order_id", "").lower()
            or q in r.get("sku", "").lower()
            or q in r.get("item_category", "").lower()
            or q in r.get("courier", "").lower()
        ]

    total = len(all_returns)
    start = (page - 1) * page_size
    page_items = all_returns[start:start + page_size]

    items = [{**r, "prediction": store.get_prediction(r["id"], org["id"])} for r in page_items]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/api/v1/returns/{return_id}")
async def get_return(return_id: str, org: dict = Depends(get_current_org)) -> dict:
    r = _get_owned_return_or_404(return_id, org)
    pred = store.get_prediction(return_id, org["id"])
    return {**r, "prediction": pred}


@router.get("/api/v1/returns/{return_id}/transitions")
async def get_allowed_transitions(
    return_id: str,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """PHASE 12: what this return can legally become next.

    Lets the UI render only the buttons that will work. Showing a warehouse
    manager every possible action and rejecting half of them with a 409
    teaches them the software is unreliable, when in fact it is correct.
    """
    r = _get_owned_return_or_404(return_id, org)
    current = r.get("status", "")
    return {
        "current_status": current,
        "allowed_transitions": next_statuses(current),
        "is_terminal": is_terminal(current),
    }


@router.patch("/api/v1/returns/{return_id}/status")
async def update_return_status(
    return_id: str,
    payload: ReturnStatusUpdate,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    current = _get_owned_return_or_404(return_id, org)
    current_status = current.get("status", "")

    # PHASE 12: the lifecycle decides, not the caller. Before this, a refunded
    # return could be set back to pending -- money already out the door -- and
    # then approved and refunded a second time.
    try:
        validate_transition(current_status, payload.status)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    update = {"id": return_id, "status": payload.status}
    if payload.notes:
        update["notes"] = payload.notes
    updated = store.store_return(update)

    audit_service.record(
        org_id=org["id"],
        user_id=user["id"],
        action="return_status_changed",
        resource_type="return",
        resource_id=return_id,
        detail=f"{current_status} -> {payload.status}",
        # Structured before/after, so "what was this return before someone
        # changed it" is a query rather than a search through English prose.
        changes={"status": {"from": current_status, "to": payload.status}},
    )
    return updated


@router.patch("/api/v1/returns/{return_id}/outcome")
async def confirm_return_outcome(
    return_id: str,
    payload: PredictionOutcomeSubmit,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Record what *actually* happened to a return, after the fact - was it
    really fraud, how damaged was the item on inspection, what did it
    really cost, what did it actually resell for.

    This is the missing piece that made a real supervised fraud/damage
    model impossible to build (see Phase 4 ML evaluation): the rule-based
    scores in ml_service.py have never had anything to be checked against.
    Every call here adds one labeled example. Once there are enough
    (ml/train_fraud_model.py checks a minimum count before it'll run),
    training a real model on this data becomes possible.
    """
    _get_owned_return_or_404(return_id, org)
    pred = store.get_prediction(return_id, org["id"])
    if not pred:
        raise HTTPException(status_code=404, detail="No prediction exists for this return yet")

    data = payload.model_dump(exclude_none=True)
    data["confirmed_by_user_id"] = user["id"]
    data["confirmed_at"] = datetime.now(UTC)
    outcome = store.upsert_prediction_outcome(pred["id"], data)

    store.add_audit_log({"org_id": org["id"], "user_id": user["id"], "action": "confirm_outcome",
                         "detail": f"Return {return_id} outcome confirmed"})
    return outcome


# ── API Key routes — backward compatible with v2 ──────────────────────────────
@router.post("/api/v1/ext/returns", status_code=201, tags=["external-api"])
async def create_return_apikey(
    payload: ReturnRequestCreate,
    org: dict = Depends(get_org_from_api_key),
) -> dict:
    """External API endpoint — uses X-API-Key header. Backward compatible with v2."""
    return _score_and_store(payload, org)


@router.get("/api/v1/ext/returns/dashboard", tags=["external-api"])
async def get_dashboard_apikey(org: dict = Depends(get_org_from_api_key)) -> dict:
    return store.get_dashboard_stats(org["id"])


@router.get("/api/v1/ext/returns", tags=["external-api"])
async def list_returns_apikey(org: dict = Depends(get_org_from_api_key)) -> list:
    all_returns = store.get_returns_for_org(org["id"])
    return [{**r, "prediction": store.get_prediction(r["id"], org["id"])} for r in all_returns]


@router.get("/api/v1/ext/returns/{return_id}", tags=["external-api"])
async def get_return_apikey(return_id: str, org: dict = Depends(get_org_from_api_key)) -> dict:
    r = _get_owned_return_or_404(return_id, org)
    return {**r, "prediction": store.get_prediction(return_id, org["id"])}
