"""
COD Risk (pre-shipment fraud/RTO scoring).

Sellers call POST /score right after an order is placed, before shipping,
to decide whether to ship immediately, call to confirm, or hold for
manual review.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission
from app.api.v1.deps import get_current_org, require_permission
from app.db import store
from app.schemas.schemas import CODRiskScoreRequest, CODRiskScoreResponse
from app.services.cod_risk_service import score_cod_order

router = APIRouter(prefix="/api/v1/cod-risk", tags=["cod-risk"])

# Warehouse/finance/org_admin roles are the ones who'd act on a
# ship/hold decision -- same role set already used for shipping-adjacent
# actions elsewhere in this codebase.
# PHASE 6: was require_role("org_admin", "warehouse_manager", "finance").
# Neither warehouse_manager nor finance is an assignable role, so this was
# org_admin-only in practice while looking delegable. COD_SCORE is held by
# analyst and above, which is what the original role list intended.
_can_score = require_permission(Permission.COD_SCORE)


@router.post("/score", response_model=CODRiskScoreResponse)
async def score_order(
    payload: CODRiskScoreRequest,
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_score),
) -> CODRiskScoreResponse:
    """Score a COD order for fraud/RTO risk BEFORE it ships."""
    result = score_cod_order(
        org_id=org["id"],
        platform_order_id=payload.platform_order_id,
        customer_phone=payload.customer_phone,
        customer_name=payload.customer_name,
        delivery_address=payload.delivery_address,
        delivery_pincode=payload.delivery_pincode,
        order_value=payload.order_value.to_money(),
    )
    return CODRiskScoreResponse(**result)


@router.get("/assessments")
async def list_assessments(
    limit: int = Query(50, ge=1, le=200),
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_score),
) -> list[dict]:
    """Recent COD risk assessments for this org, most recent first."""
    return store.get_cod_risk_assessments_for_org(org["id"], limit=limit)
