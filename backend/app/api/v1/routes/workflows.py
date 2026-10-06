"""
Workflow Automation (Phase 5.12)
CRUD for workflow rules + SLA tracking endpoints.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_org, require_role
from app.db import store
from app.services import workflow_validation
from app.schemas.schemas import WorkflowRuleCreate, WorkflowRuleUpdate

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.get("/rules")
async def list_rules(org: dict = Depends(get_current_org)) -> list:
    return store.get_workflow_rules(org["id"])


@router.post("/rules", status_code=201)
async def create_rule(
    payload: WorkflowRuleCreate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Create a workflow automation rule.

    Example — auto-approve low-risk returns:
    {
      "name": "Auto-approve low risk",
      "rule_type": "auto_approve",
      "conditions": {"risk_score_lt": 20, "item_value_lt": 500},
      "action": {"status": "approved", "notify": true},
      "priority": 1
    }
    """
    # PHASE 32: validate before saving.
    #
    # Previously `conditions` was dict[str, Any] with no checking, so
    # {"banana_split_eq": "yes"} returned 201 Created. The rule appeared in
    # the merchant's list as active and never fired — the only trace a warning
    # line in a log nobody reads.
    proposed = {
        "name": payload.name,
        "rule_type": payload.rule_type,
        "conditions": payload.conditions,
        "action": payload.action,
        "priority": payload.priority,
        "is_active": payload.is_active,
    }
    try:
        workflow_validation.validate_rule(proposed)
    except workflow_validation.RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Conflicts are a warning, not a refusal. A merchant may deliberately
    # stage a replacement rule before disabling the old one, and blocking that
    # would push them into disabling protection first.
    existing = store.get_workflow_rules(org["id"])
    conflicts = workflow_validation.find_conflicts(existing + [proposed])

    rule = store.create_workflow_rule({
        "id": str(uuid.uuid4()),
        "org_id": org["id"],
        "name": payload.name,
        "rule_type": payload.rule_type,
        "conditions": payload.conditions,
        "action": payload.action,
        "priority": payload.priority,
        "is_active": payload.is_active,
        "triggered_count": 0,
        "created_by": user["id"],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    })

    if conflicts.conflicts:
        rule = {**rule, "conflict_warning": conflicts.as_dict()}
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "create_workflow_rule",
        "detail": f"Rule '{payload.name}' created",
    })
    return rule


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: WorkflowRuleUpdate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    updates = payload.model_dump(exclude_none=True)
    updated = store.update_workflow_rule(rule_id, org["id"], updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found")
    return updated


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    deleted = store.delete_workflow_rule(rule_id, org["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.get("/sla")
async def list_sla(
    breached_only: bool = False,
    org: dict = Depends(get_current_org),
) -> list:
    """List SLA records. Use breached_only=true to see overdue returns."""
    if breached_only:
        return store.get_breached_slas(org["id"])
    # Return all SLAs for this org
    from sqlalchemy import select

    from app.db import models
    from app.db.database import SessionLocal
    from app.db.store import _to_dict
    with SessionLocal() as db:
        rows = db.execute(
            select(models.SLATracking).where(models.SLATracking.org_id == org["id"])
        ).scalars().all()
        return [_to_dict(r) for r in rows]


@router.get("/sla/check-breaches")
async def check_sla_breaches(
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Scan all open SLA records for this org and mark overdue ones as breached.
    In production this should be a scheduled background task (cron/celery),
    not a manual endpoint — but having it as an endpoint lets you trigger it
    manually or from a simple cron job that just hits this URL.
    """
    from sqlalchemy import select

    from app.db import models
    from app.db.database import SessionLocal
    with SessionLocal() as db:
        now = datetime.now(UTC)
        open_slas = db.execute(
            select(models.SLATracking).where(
                models.SLATracking.org_id == org["id"],
                models.SLATracking.resolved_at.is_(None),
                models.SLATracking.breached.is_(False),
            )
        ).scalars().all()
        newly_breached = []
        for sla in open_slas:
            if sla.sla_deadline < now:
                sla.breached = True
                newly_breached.append(sla.return_request_id)
                store.add_notification({
                    "org_id": org["id"],
                    "type": "sla_breach",
                    "title": "⏰ SLA Breach",
                    "message": f"Return {sla.return_request_id} has breached its SLA deadline",
                    "severity": "critical",
                })
        db.commit()
    return {"newly_breached": len(newly_breached), "return_ids": newly_breached}
