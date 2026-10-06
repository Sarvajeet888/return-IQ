"""
Admin Panel (Phase 5.10)
Super-admin only routes: user/org management, system settings, feature flags,
health dashboard, ML statistics, API monitoring.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api.v1.deps import require_role
from app.db import models, store
from app.db.database import SessionLocal
from app.schemas.schemas import SystemSettingUpdate

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_super_admin = Depends(require_role("super_admin"))


def _super_admin_dep():
    return require_role("super_admin")


@router.get("/health")
async def health_dashboard(user: dict = Depends(require_role("super_admin", "org_admin"))) -> dict:
    """System health overview: DB stats, ML model status."""
    with SessionLocal() as db:
        org_count = db.execute(select(func.count()).select_from(models.Org)).scalar_one()
        user_count = db.execute(select(func.count()).select_from(models.User)).scalar_one()
        return_count = db.execute(select(func.count()).select_from(models.ReturnRequest)).scalar_one()
        prediction_count = db.execute(select(func.count()).select_from(models.Prediction)).scalar_one()
        outcome_count = db.execute(select(func.count()).select_from(models.PredictionOutcome)).scalar_one()

    from app.services.ml_service import get_model_stats
    ml_stats = get_model_stats()

    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "database": {
            "orgs": org_count,
            "users": user_count,
            "returns": return_count,
            "predictions": prediction_count,
            "labeled_outcomes": outcome_count,
        },
        "ml": ml_stats,
        "version": "5.0.0",
    }


@router.get("/orgs")
async def list_all_orgs(user: dict = Depends(require_role("super_admin"))) -> list:
    """All organizations (super_admin only)."""
    with SessionLocal() as db:
        from app.db.store import _to_dict
        rows = db.execute(select(models.Org)).scalars().all()
        return [_to_dict(r) for r in rows]


@router.get("/users")
async def list_all_users(user: dict = Depends(require_role("super_admin"))) -> list:
    """All users across all orgs (super_admin only)."""
    with SessionLocal() as db:
        from app.db.store import _to_dict
        rows = db.execute(select(models.User)).scalars().all()
        result = [_to_dict(r) for r in rows]
        # Strip password hashes from admin view
        for u in result:
            u.pop("password_hash", None)
        return result


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    status: str = Query(..., description="active | suspended | deleted"),
    admin: dict = Depends(require_role("super_admin")),
) -> dict:
    if status not in {"active", "suspended", "deleted"}:
        raise HTTPException(status_code=400, detail="status must be active | suspended | deleted")
    store.update_user(user_id, {"status": status})
    store.add_audit_log({
        "org_id": admin["org_id"], "user_id": admin["id"],
        "action": "admin_update_user_status",
        "detail": f"User {user_id} status set to {status}",
    })
    return {"user_id": user_id, "status": status}


@router.get("/system-settings")
async def get_system_settings(user: dict = Depends(require_role("super_admin"))) -> list:
    return store.get_system_settings()


@router.put("/system-settings/{key}")
async def set_system_setting(
    key: str,
    payload: SystemSettingUpdate,
    user: dict = Depends(require_role("super_admin")),
) -> dict:
    result = store.set_system_setting(key, payload.value, user["id"])
    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user["id"],
        "action": "update_system_setting",
        "detail": f"System setting '{key}' updated",
    })
    return result


@router.get("/audit-logs")
async def global_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(require_role("super_admin")),
) -> list:
    """Audit logs across all orgs — super_admin view."""
    with SessionLocal() as db:
        from app.db.store import _to_dict
        rows = db.execute(
            select(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


@router.get("/ml-stats")
async def ml_statistics(user: dict = Depends(require_role("super_admin", "org_admin"))) -> dict:
    """ML model statistics and label accumulation progress."""
    fraud_labels = store.count_labeled_outcomes("actual_fraud_confirmed")
    damage_labels = store.count_labeled_outcomes("actual_damage_grade")

    from app.services.ml_service import get_model_stats
    model_stats = get_model_stats()

    return {
        "cost_prediction_model": model_stats,
        "fraud_model": {
            "status": "rule_based",
            "labeled_outcomes_collected": fraud_labels,
            "training_threshold": 200,
            "ready_to_train": fraud_labels >= 200,
            "note": "Collect 200+ outcomes via PATCH /returns/{id}/outcome before training",
        },
        "damage_model": {
            "status": "rule_based",
            "labeled_outcomes_collected": damage_labels,
            "training_threshold": 200,
            "ready_to_train": damage_labels >= 200,
        },
    }


@router.get("/db-statistics")
async def database_statistics(user: dict = Depends(require_role("super_admin"))) -> dict:
    """Row counts for all major tables."""
    with SessionLocal() as db:
        def count(model):
            return db.execute(select(func.count()).select_from(model)).scalar_one()
        return {
            "orgs": count(models.Org),
            "users": count(models.User),
            "api_keys": count(models.ApiKey),
            "return_requests": count(models.ReturnRequest),
            "predictions": count(models.Prediction),
            "prediction_outcomes": count(models.PredictionOutcome),
            "customers": count(models.Customer),
            "notifications": count(models.Notification),
            "audit_logs": count(models.AuditLog),
            "workflow_rules": count(models.WorkflowRule),
            "return_notes": count(models.ReturnNote),
            "return_documents": count(models.ReturnDocument),
            "sla_tracking": count(models.SLATracking),
        }
