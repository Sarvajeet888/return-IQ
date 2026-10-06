"""
AI & ML User Experience (Phase 5.11)
Prediction history, explanations, confidence scores, manual override,
feedback collection, model version display, and AI performance dashboard.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.money import Money
from app.api.v1.deps import get_current_org, get_current_user, require_role
from app.db import store
from app.ml.explainability import attribution_caveat

router = APIRouter(prefix="/api/v1/ai", tags=["ai-ml"])


class ManualOverride(BaseModel):
    routing_decision: str
    reason: str


class PredictionFeedback(BaseModel):
    prediction_id: str
    was_accurate: bool
    comments: str | None = None


@router.get("/predictions/history")
async def prediction_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    routing_decision: str | None = None,
    org: dict = Depends(get_current_org),
) -> dict:
    """
    All predictions for this org with optional routing_decision filter.
    Useful for the AI platform dashboard — shows what the model has been
    deciding and whether those decisions correlate with outcomes.
    """
    all_returns = store.get_returns_for_org(org["id"])
    predictions = []
    for r in all_returns:
        pred = store.get_prediction(r["id"], org["id"])
        if pred:
            if routing_decision and pred.get("routing_decision") != routing_decision:
                continue
            predictions.append({
                "return_id": r["id"],
                "order_id": r.get("platform_order_id"),
                "created_at": pred.get("created_at"),
                "routing_decision": pred.get("routing_decision"),
                "risk_score": pred.get("risk_score"),
                "fraud_score": pred.get("fraud_score"),
                "confidence_score": pred.get("confidence_score"),
                "model_version": pred.get("model_version"),
                "predicted_cost": Money(int(pred.get("predicted_cost_minor") or 0),
                                    pred.get("currency") or "INR").as_dict(),
            })

    predictions.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    total = len(predictions)
    start = (page - 1) * page_size
    return {
        "items": predictions[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/predictions/{return_id}/explain")
async def explain_prediction(
    return_id: str,
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Full explainability for a prediction.
    Returns the stored feature_snapshot and explainability dict, plus a
    human-readable interpretation of the top cost driver.

    The explainability values come from XGBoost's feature_importances_
    (set in Phase 4.13) — they're importance-weighted, not full SHAP values.
    The interpretation is honest about that.
    """
    r = store.get_return_by_id(return_id)
    if not r or (r.get("org_id") != org["id"] and r.get("merchant_id") != org["id"]):
        raise HTTPException(status_code=404, detail="Return not found")

    pred = store.get_prediction(return_id, org["id"])
    if not pred:
        raise HTTPException(status_code=404, detail="No prediction for this return")

    explainability = pred.get("explainability") or {}
    feature_snapshot = pred.get("feature_snapshot") or {}

    # PHASE 21: the hardcoded causal narratives that used to live here have
    # been removed. They mapped whichever feature ranked highest onto invented
    # prose — "festive-season returns correlate with bulk purchasing and
    # impulse buying", "COD returns carry cash reconciliation overhead" — and
    # presented it to merchants as though the model had produced it.
    #
    # The model knows nothing about impulse buying. Those were stories a
    # developer wrote. The roadmap is explicit: never present explanations as
    # causal proof when they are only model-attribution signals.
    #
    # Measured alongside: the underlying attribution barely varies. Across 300
    # randomised returns, distance ranked first in 300/300 and two orderings
    # covered 92% of cases. So the narrative was not only causal-sounding, it
    # was near-constant — the same explanation for a Rs 90,000 electronics
    # item and a Rs 1,500 t-shirt.
    top_driver = explainability.get("top_cost_driver", "unknown")
    attribution = attribution_caveat()

    return {
        "return_id": return_id,
        "prediction": {
            "routing_decision": pred.get("routing_decision"),
            "risk_score": pred.get("risk_score"),
            "fraud_score": pred.get("fraud_score"),
            "confidence_score": pred.get("confidence_score"),
            "predicted_cost": Money(int(pred.get("predicted_cost_minor") or 0),
                                    pred.get("currency") or "INR").as_dict(),
            "model_version": pred.get("model_version"),
        },
        "explainability": explainability,
        "top_attributed_feature": top_driver,
        "attribution_method": attribution["method"],
        "attribution_caveat": attribution["caveat"],
        "causal_disclaimer": attribution["disclaimer"],
        "feature_snapshot": feature_snapshot,
        "methodology_note": (
            "Cost prediction uses a trained XGBoost model. "
            "Feature importances are from the model's feature_importances_ attribute "
            "(gain-based), not SHAP values. "
            "Fraud/damage scores are rule-based (see Phase 4 audit)."
        ),
    }


@router.post("/predictions/{return_id}/override")
async def manual_override(
    return_id: str,
    payload: ManualOverride,
    user: dict = Depends(require_role("org_admin", "analyst", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Manually override the AI's routing decision.
    Stores the override reason in the return's notes for audit trail.
    Does not retrain the model — overrides are separate from ground-truth outcomes.
    """
    allowed = {"accept", "reject", "manual_review", "refund_and_keep"}
    if payload.routing_decision not in allowed:
        raise HTTPException(status_code=400, detail=f"routing_decision must be one of {allowed}")

    r = store.get_return_by_id(return_id)
    if not r or (r.get("org_id") != org["id"] and r.get("merchant_id") != org["id"]):
        raise HTTPException(status_code=404, detail="Return not found")

    # Record override in notes
    import uuid
    store.add_return_note({
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "user_id": user["id"],
        "note": f"[MANUAL OVERRIDE] AI decision overridden to '{payload.routing_decision}'. Reason: {payload.reason}",
        "created_at": datetime.now(UTC),
    })
    store.store_return({"id": return_id, "status": f"override_{payload.routing_decision}"})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "manual_override",
        "detail": f"Return {return_id} overridden to {payload.routing_decision}: {payload.reason}",
    })
    return {
        "return_id": return_id,
        "overridden_to": payload.routing_decision,
        "reason": payload.reason,
        "overridden_by": user["id"],
    }


@router.post("/feedback")
async def submit_feedback(
    payload: PredictionFeedback,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Collect qualitative feedback on prediction accuracy.
    This is separate from structured outcome labels (Phase 4.7/4.8) —
    it captures the user's subjective assessment which can help identify
    systematic biases before enough outcome labels exist for retraining.
    """
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "prediction_feedback",
        "detail": f"Prediction {payload.prediction_id}: accurate={payload.was_accurate}. {payload.comments or ''}",
    })
    return {
        "message": "Feedback recorded",
        "prediction_id": payload.prediction_id,
        "was_accurate": payload.was_accurate,
    }


@router.get("/performance")
async def ai_performance_dashboard(org: dict = Depends(get_current_org)) -> dict:
    """
    AI performance metrics: decision distribution, confidence stats,
    and label collection progress.
    """
    all_returns = store.get_returns_for_org(org["id"])
    decisions: dict[str, int] = {}
    confidence_scores = []
    risk_scores = []
    model_versions: dict[str, int] = {}

    for r in all_returns:
        pred = store.get_prediction(r["id"], org["id"])
        if pred:
            d = pred.get("routing_decision", "unknown")
            decisions[d] = decisions.get(d, 0) + 1
            confidence_scores.append(float(pred.get("confidence_score", 0)))
            risk_scores.append(float(pred.get("risk_score", 0)))
            mv = pred.get("model_version", "unknown")
            model_versions[mv] = model_versions.get(mv, 0) + 1

    fraud_labels = store.count_labeled_outcomes("actual_fraud_confirmed")
    damage_labels = store.count_labeled_outcomes("actual_damage_grade")

    return {
        "total_predictions": len(confidence_scores),
        "decision_distribution": decisions,
        "avg_confidence": round(sum(confidence_scores) / len(confidence_scores), 3) if confidence_scores else 0,
        "avg_risk_score": round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0,
        "model_versions_in_use": model_versions,
        "label_collection": {
            "fraud_labels_collected": fraud_labels,
            "damage_labels_collected": damage_labels,
            "fraud_training_ready": fraud_labels >= 200,
            "damage_training_ready": damage_labels >= 200,
        },
    }
