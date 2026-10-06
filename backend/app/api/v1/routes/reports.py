"""
Reporting & Export (Phase 5.9)
JSON/CSV reports: summary, fraud, carbon, customer analytics.
PDF generation is noted as requiring weasyprint/reportlab (Phase 5.13 deps).
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.money import Money
from app.api.v1.deps import get_current_org, get_current_user
from app.db import store

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _filter_by_date(items: list[dict], date_from: str | None, date_to: str | None) -> list[dict]:
    """Filter a list of dicts by their 'created_at' field."""
    if not date_from and not date_to:
        return items
    filtered = []
    for item in items:
        ts = (item.get("created_at") or "")[:10]
        if date_from and ts < date_from:
            continue
        if date_to and ts > date_to:
            continue
        filtered.append(item)
    return filtered


@router.get("/summary", response_model=None)
async def summary_report(
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
    format: str = Query("json", description="json | csv"),
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict | StreamingResponse:
    """Overall returns summary report."""
    all_returns = store.get_returns_for_org(org["id"])
    returns = _filter_by_date(all_returns, date_from, date_to)

    total = len(returns)
    decisions: dict[str, int] = {}
    total_cost_minor = 0
    total_carbon = 0.0
    report_currency = org.get("currency") or "INR"
    pred_count = 0

    rows = []
    for r in returns:
        pred = store.get_prediction(r["id"], org["id"])
        row = {
            "return_id": r["id"],
            "order_id": r.get("platform_order_id"),
            "customer": r.get("customer_identifier"),
            "sku": r.get("sku"),
            "category": r.get("item_category"),
            "item_value": Money(int(r.get("item_value_minor") or 0),
                                r.get("currency") or "INR").as_dict(),
            "status": r.get("status"),
            "created_at": (r.get("created_at") or "")[:10],
            "routing_decision": pred.get("routing_decision") if pred else None,
            "risk_score": pred.get("risk_score") if pred else None,
            "predicted_cost": (Money(int(pred.get("predicted_cost_minor") or 0),
                                     pred.get("currency") or "INR").as_dict()
                               if pred else None),
            "carbon_footprint_kg": pred.get("carbon_footprint_kg") if pred else None,
        }
        rows.append(row)
        if pred:
            d = pred.get("routing_decision", "unknown")
            decisions[d] = decisions.get(d, 0) + 1
            total_cost_minor += int(pred.get("predicted_cost_minor") or 0)
            total_carbon += float(pred.get("carbon_footprint_kg", 0))
            pred_count += 1

    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "generate_report", "detail": f"Summary report generated ({total} returns)",
    })

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=summary_report.csv"},
        )

    return {
        "report_type": "summary",
        "generated_at": datetime.now(UTC).isoformat(),
        "date_range": {"from": date_from, "to": date_to},
        "org": org["name"],
        "totals": {
            "returns": total,
            "total_predicted_cost": Money(total_cost_minor, report_currency).as_dict(),
            "total_carbon_kg": round(total_carbon, 2),
            "decisions": decisions,
        },
        "rows": rows,
    }


@router.get("/fraud", response_model=None)
async def fraud_report(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    format: str = Query("json"),
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict | StreamingResponse:
    """Fraud-focused report: high-risk returns and suspected fraud cases."""
    all_returns = store.get_returns_for_org(org["id"])
    returns = _filter_by_date(all_returns, date_from, date_to)

    fraud_rows = []
    for r in returns:
        pred = store.get_prediction(r["id"], org["id"])
        if pred and float(pred.get("fraud_score", 0)) >= 50:
            fraud_rows.append({
                "return_id": r["id"],
                "order_id": r.get("platform_order_id"),
                "customer": r.get("customer_identifier"),
                "fraud_score": pred.get("fraud_score"),
                "risk_score": pred.get("risk_score"),
                "routing_decision": pred.get("routing_decision"),
                "item_value": Money(int(r.get("item_value_minor") or 0),
                                r.get("currency") or "INR").as_dict(),
                "reason_code": r.get("return_reason_code"),
                "payment_mode": r.get("payment_mode"),
                "created_at": (r.get("created_at") or "")[:10],
            })

    fraud_rows.sort(key=lambda x: float(x.get("fraud_score") or 0), reverse=True)

    if format == "csv":
        output = io.StringIO()
        if fraud_rows:
            writer = csv.DictWriter(output, fieldnames=list(fraud_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fraud_rows)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fraud_report.csv"},
        )

    return {
        "report_type": "fraud",
        "generated_at": datetime.now(UTC).isoformat(),
        "high_risk_count": len(fraud_rows),
        "rows": fraud_rows,
    }


@router.get("/carbon", response_model=None)
async def carbon_report(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    format: str = Query("json"),
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict | StreamingResponse:
    """Carbon footprint report broken down by courier and category."""
    all_returns = store.get_returns_for_org(org["id"])
    returns = _filter_by_date(all_returns, date_from, date_to)

    courier_carbon: dict[str, float] = {}
    category_carbon: dict[str, float] = {}
    total_carbon = 0.0
    rows = []

    for r in returns:
        pred = store.get_prediction(r["id"], org["id"])
        carbon = float((pred or {}).get("carbon_footprint_kg", 0))
        courier = r.get("courier", "unknown")
        category = r.get("item_category", "unknown")
        courier_carbon[courier] = courier_carbon.get(courier, 0) + carbon
        category_carbon[category] = category_carbon.get(category, 0) + carbon
        total_carbon += carbon
        rows.append({
            "return_id": r["id"],
            "courier": courier,
            "category": category,
            "carbon_footprint_kg": carbon,
            "created_at": (r.get("created_at") or "")[:10],
        })

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=carbon_report.csv"},
        )

    return {
        "report_type": "carbon",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_carbon_kg": round(total_carbon, 3),
        "by_courier": [{"courier": k, "kg": round(v, 3)} for k, v in sorted(courier_carbon.items(), key=lambda x: -x[1])],
        "by_category": [{"category": k, "kg": round(v, 3)} for k, v in sorted(category_carbon.items(), key=lambda x: -x[1])],
        "rows": rows,
    }


@router.get("/customers", response_model=None)
async def customer_report(
    format: str = Query("json"),
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict | StreamingResponse:
    """Customer analytics report: return rates, fraud scores, segmentation."""
    customers = store.get_customers_for_org(org["id"])
    all_returns = store.get_returns_for_org(org["id"])

    rows = []
    for c in customers:
        cust_returns = [r for r in all_returns if r.get("customer_identifier") == c.get("email")]
        fraud_count = sum(
            1 for r in cust_returns
            if (store.get_prediction(r["id"], org["id"]) or {}).get("fraud_score", 0) > 70
        )
        rows.append({
            "customer_id": c["id"],
            "name": c["name"],
            "email": c["email"],
            "city": c.get("city"),
            "total_returns": len(cust_returns),
            "fraud_returns": fraud_count,
            "fraud_rate": round(fraud_count / max(len(cust_returns), 1) * 100, 1),
            "risk_level": c.get("risk_level"),
            "is_blacklisted": c.get("is_blacklisted", False),
        })

    rows.sort(key=lambda x: float(x.get("fraud_rate") or 0), reverse=True)

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=customer_report.csv"},
        )

    return {
        "report_type": "customers",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_customers": len(rows),
        "blacklisted": sum(1 for r in rows if r["is_blacklisted"]),
        "rows": rows,
    }
