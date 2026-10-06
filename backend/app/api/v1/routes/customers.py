"""
Customer Management (Phase 5.4)
Covers: full CRUD, search, analytics, blacklist, notes, import/export.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.money import Money
from app.api.v1.deps import get_current_org, get_current_user, require_role
from app.db import store
from app.schemas.schemas import CustomerCreate, CustomerUpdate

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get("/")
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    risk_level: str | None = None,
    is_blacklisted: bool | None = None,
    org: dict = Depends(get_current_org),
) -> dict:
    """List customers with pagination, search, and risk-level filtering."""
    if search:
        customers = store.search_customers(org["id"], search, limit=500)
    else:
        customers = store.get_customers_for_org(org["id"])

    if risk_level:
        customers = [c for c in customers if c.get("risk_level") == risk_level]
    if is_blacklisted is not None:
        customers = [c for c in customers if bool(c.get("is_blacklisted")) == is_blacklisted]

    total = len(customers)
    start = (page - 1) * page_size
    items = customers[start:start + page_size]

    # Enrich each customer with their return history summary
    enriched = []
    for c in items:
        returns = store.get_returns_for_org(org["id"])
        cust_returns = [r for r in returns if r.get("customer_identifier") == c.get("email")]
        enriched.append({
            **c,
            "return_count": len(cust_returns),
        })

    return {
        "items": enriched,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/", status_code=201)
async def create_customer(
    payload: CustomerCreate,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    customer = store.store_customer({
        "id": str(uuid.uuid4()),
        "org_id": org["id"],
        "name": payload.name,
        "email": payload.email.lower(),
        "phone": payload.phone,
        "city": payload.city,
        "joined_at": datetime.now(UTC),
    })
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "create_customer", "detail": f"Customer {payload.email} created",
    })
    return customer


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    org: dict = Depends(get_current_org),
) -> dict:
    c = store.get_customer(customer_id)
    if not c or c.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Include return history for this customer
    all_returns = store.get_returns_for_org(org["id"])
    cust_returns = [r for r in all_returns if r.get("customer_identifier") == c.get("email")]

    fraud_count = 0
    total_value_minor = 0
    for r in cust_returns:
        pred = store.get_prediction(r["id"], org["id"])
        if pred and float(pred.get("fraud_score", 0)) > 70:
            fraud_count += 1
        total_value_minor += int(r.get("item_value_minor") or 0)

    return {
        **c,
        "return_history": cust_returns[:20],
        "analytics": {
            "total_returns": len(cust_returns),
            "total_return_value": Money(
                total_value_minor, org.get("currency") or "INR"
            ).as_dict(),
            "suspected_fraud_count": fraud_count,
            "return_rate": round(len(cust_returns) / max(c.get("total_orders", 1), 1) * 100, 1),
        },
    }


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    c = store.get_customer(customer_id)
    if not c or c.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Customer not found")
    updates = payload.model_dump(exclude_none=True)
    updated = store.update_customer(customer_id, updates)
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "update_customer", "detail": f"Customer {customer_id} updated",
    })
    return updated


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: str,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    c = store.get_customer(customer_id)
    if not c or c.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Customer not found")
    store.update_customer(customer_id, {"status": "deleted"})
    return {"message": "Customer deleted"}


@router.post("/{customer_id}/blacklist")
async def blacklist_customer(
    customer_id: str,
    reason: str = Query(default=""),
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """Add customer to blacklist — prevents new returns from this identifier."""
    c = store.get_customer(customer_id)
    if not c or c.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Customer not found")
    store.add_customer_to_blacklist(
        org_id=org["id"],
        customer_identifier=c["email"],
        reason=reason,
        user_id=user["id"],
    )
    store.update_customer(customer_id, {"is_blacklisted": True, "risk_level": "critical"})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "blacklist_customer",
        "detail": f"Customer {c['email']} blacklisted. Reason: {reason}",
    })
    store.add_notification({
        "org_id": org["id"],
        "type": "customer_blacklisted",
        "title": "🚫 Customer Blacklisted",
        "message": f"{c['name']} ({c['email']}) has been blacklisted.",
        "severity": "warning",
    })
    return {"message": f"Customer {c['email']} blacklisted", "reason": reason}


@router.get("/{customer_id}/analytics")
async def get_customer_analytics(
    customer_id: str,
    org: dict = Depends(get_current_org),
) -> dict:
    """Deep analytics for a single customer."""
    c = store.get_customer(customer_id)
    if not c or c.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Customer not found")

    all_returns = store.get_returns_for_org(org["id"])
    cust_returns = [r for r in all_returns if r.get("customer_identifier") == c.get("email")]

    reason_breakdown: dict[str, int] = {}
    category_breakdown: dict[str, int] = {}
    risk_scores = []
    costs = []

    for r in cust_returns:
        reason = r.get("return_reason_code", "unknown")
        reason_breakdown[reason] = reason_breakdown.get(reason, 0) + 1
        cat = r.get("item_category", "unknown")
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
        pred = store.get_prediction(r["id"], org["id"])
        if pred:
            risk_scores.append(float(pred.get("risk_score", 0)))
            costs.append(int(pred.get("predicted_cost_minor") or 0))

    return {
        "customer": c,
        "total_returns": len(cust_returns),
        "avg_risk_score": round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0,
        "total_predicted_cost": round(sum(costs), 2),
        "reason_breakdown": [{"reason": k, "count": v} for k, v in reason_breakdown.items()],
        "category_breakdown": [{"category": k, "count": v} for k, v in category_breakdown.items()],
    }


@router.get("/export/csv")
async def export_customers_csv(
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> StreamingResponse:
    """Export all customers to CSV."""
    customers = store.get_customers_for_org(org["id"])
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "name", "email", "phone", "city",
        "total_orders", "total_returns", "fraud_score", "risk_level", "joined_at",
    ])
    writer.writeheader()
    for c in customers:
        writer.writerow({k: c.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "export_customers", "detail": f"Exported {len(customers)} customers to CSV",
    })
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers_export.csv"},
    )
