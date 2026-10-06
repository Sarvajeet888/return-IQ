"""PHASE 35 — grounded insight endpoints.

Real data only. `/change` decomposes `item_value_minor` -- an amount a
customer actually returned, not a model's prediction -- so nothing here
depends on the synthetic-data model quality documented in
PHASE_17_FEASIBILITY.md.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_org, get_current_user, require_permission
from app.core.permissions import Permission
from app.db import store
from app.services import audit_service
from app.services.executive_summary import build_summary
from app.services.insight_engine import (
    VALID_DIMENSIONS,
    InsightError,
    compare_dimensions,
    decompose_change,
    narrative,
)

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


def _parse_created_at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        text = str(value).replace("Z", "").replace(" ", "T", 1)
        return datetime.fromisoformat(text.split("+")[0])
    except (ValueError, TypeError):
        return None


def _two_windows(org_id: str, days: int) -> tuple[list[dict], list[dict], tuple, tuple]:
    """Split an org's returns into two equal, adjacent windows.

    Fetches once and partitions in memory rather than issuing two filtered
    queries, so the two windows are guaranteed to be built from the exact
    same snapshot of data -- a row created between two separate queries could
    otherwise appear in neither, or the totals could be computed against
    inconsistent underlying data.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    after_start = now - timedelta(days=days)
    before_start = now - timedelta(days=2 * days)

    all_returns = store.get_returns_for_org(org_id)
    rows_before, rows_after = [], []
    for r in all_returns:
        ts = _parse_created_at(r.get("created_at"))
        if ts is None:
            continue
        if before_start <= ts < after_start:
            rows_before.append(r)
        elif after_start <= ts <= now:
            rows_after.append(r)

    return (
        rows_before, rows_after,
        (before_start.date().isoformat(), after_start.date().isoformat()),
        (after_start.date().isoformat(), now.date().isoformat()),
    )


@router.get("/change")
async def explain_change(
    dimension: str = Query(
        ..., description=f"One of: {', '.join(sorted(VALID_DIMENSIONS))}"
    ),
    days: int = Query(default=30, ge=1, le=180),
    user: dict = Depends(require_permission(Permission.REPORTS_READ)),
    org: dict = Depends(get_current_org),
) -> dict:
    """Why did total returned value change, broken down by one dimension.

    Compares the last `days` days against the `days` before that. Every
    figure returned is an exact sum over this organization's own returns —
    there is no model prediction and no generated text anywhere in this
    response; `narrative` is a direct rendering of the same numbers in the
    JSON body, not an independent description of them.
    """
    rows_before, rows_after, period_before, period_after = _two_windows(
        org["id"], days
    )

    try:
        result = decompose_change(
            rows_before, rows_after,
            value_key="item_value_minor", dimension=dimension,
            currency=org.get("currency") or "INR",
            label="Total return value",
            period_before=period_before, period_after=period_after,
        )
    except InsightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit_service.record(
        org_id=org["id"], user_id=user["id"], action="insight_viewed",
        category=audit_service.Category.DATA,
        detail=f"Change decomposition by {dimension} over {days} days",
    )

    payload = result.as_dict()
    payload["narrative"] = narrative(result)
    return payload


@router.get("/executive-summary")
async def executive_summary(
    days: int = Query(default=30, ge=1, le=180),
    user: dict = Depends(require_permission(Permission.REPORTS_READ)),
    org: dict = Depends(get_current_org),
) -> dict:
    """PHASE 36 — the single call an executive dashboard needs.

    Headline KPIs plus one honestly-picked primary driver of change, reusing
    Phase 35's engine rather than approximating it again. If more than one
    dimension explains a comparable share of the change, both are named --
    this is the same double-counting risk Phase 35 found in the roadmap's
    own example, now guarded at the point where a summary might otherwise
    present one dimension as the single cause.
    """
    rows_before, rows_after, period_before, period_after = _two_windows(
        org["id"], days
    )
    summary = build_summary(
        rows_before, rows_after, currency=org.get("currency") or "INR",
        period_before=period_before, period_after=period_after,
    )

    audit_service.record(
        org_id=org["id"], user_id=user["id"], action="insight_viewed",
        category=audit_service.Category.DATA,
        detail=f"Executive summary viewed over {days} days",
    )

    return summary.as_dict()


@router.get("/change/compare")
async def compare_change_dimensions(
    dimensions: str = Query(
        ..., description="Comma-separated dimensions, e.g. item_category,courier"
    ),
    days: int = Query(default=30, ge=1, le=180),
    user: dict = Depends(require_permission(Permission.REPORTS_READ)),
    org: dict = Depends(get_current_org),
) -> dict:
    """Several dimensions side by side, with the non-additivity warning.

    Exists specifically to surface the finding this phase's own tests
    demonstrate: two dimensions can each independently claim close to the
    full change, because they are different partitions of the same returns,
    not fragments of one pie.
    """
    dims = [d.strip() for d in dimensions.split(",") if d.strip()]
    if not dims:
        raise HTTPException(status_code=422, detail="At least one dimension is required.")

    rows_before, rows_after, period_before, period_after = _two_windows(
        org["id"], days
    )

    try:
        result = compare_dimensions(
            rows_before, rows_after,
            value_key="item_value_minor", dimensions=dims,
            currency=org.get("currency") or "INR",
            label="Total return value",
            period_before=period_before, period_after=period_after,
        )
    except InsightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit_service.record(
        org_id=org["id"], user_id=user["id"], action="insight_viewed",
        category=audit_service.Category.DATA,
        detail=f"Compared change decomposition across {dims} over {days} days",
    )

    return result
