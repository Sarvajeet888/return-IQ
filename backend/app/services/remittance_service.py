"""
Courier Remittance Reconciliation Service.

PLAIN ENGLISH: after a COD order is delivered, the courier is supposed to
forward the cash they collected from the customer back to the seller,
minus their fees. Couriers periodically send a "remittance report" -- a
list of what they say they paid, per order. This service compares that
against what the seller actually expected, and flags any mismatch.

"Expected" comes from a matching CODRiskAssessment row, if this order was
scored pre-shipment via the COD risk feature. If the order was never
scored (predates this feature, or the seller didn't call /cod-risk/score
for it), we have no ground truth to compare against -- that gets marked
unmatched_no_expected rather than silently guessed at.
"""
from __future__ import annotations

from datetime import datetime

from app.core.money import Money
from app.db import store

# Business tolerance, in minor units (paise). Rs 5.00.
#
# HISTORICAL NOTE (Phase 3): this constant used to be justified as absorbing
# "rounding/paise-level differences". That justification was a symptom of the
# float bug, not a business rule -- exact integer arithmetic has no rounding
# differences to absorb. The tolerance is retained because couriers do apply
# small genuine adjustments, but it is now a deliberate *business* decision
# with a stated reason, not a workaround for our own arithmetic. A merchant
# should be able to configure it; that is Phase 32 (workflow rules).
DISCREPANCY_TOLERANCE_MINOR = 500


def reconcile_remittance_line(
    org_id: str,
    platform_order_id: str,
    courier: str,
    remitted: Money,
    remittance_date: str,
    awb_number: str | None = None,
) -> dict:
    assessment = store.get_cod_risk_assessment_by_order_id(org_id, platform_order_id)

    expected: Money | None = None
    if assessment and assessment.get("order_value_minor") is not None:
        expected = Money(
            int(assessment["order_value_minor"]),
            assessment.get("currency") or remitted.currency,
        )

    if expected is None:
        status = "unmatched_no_expected"
        discrepancy: Money | None = None
    else:
        # Money.__sub__ raises CurrencyMismatch rather than silently adding a
        # dollar to a rupee. Letting that propagate is correct: a cross-currency
        # remittance line is a data problem the merchant must see, not something
        # to paper over with an implicit conversion.
        discrepancy = remitted - expected
        status = (
            "matched"
            if abs(discrepancy.minor_units) <= DISCREPANCY_TOLERANCE_MINOR
            else "mismatch"
        )

    record = store.create_courier_remittance({
        "org_id": org_id,
        "platform_order_id": platform_order_id,
        "courier": courier,
        "awb_number": awb_number,
        "remittance_date": datetime.strptime(remittance_date, "%Y-%m-%d"),
        "remitted_amount_minor": remitted.minor_units,
        "currency": remitted.currency,
        "expected_amount_minor": expected.minor_units if expected else None,
        "discrepancy_amount_minor": discrepancy.minor_units if discrepancy else None,
        "status": status,
    })
    return _serialize(record)


def reconcile_batch(org_id: str, lines: list[dict]) -> dict:
    results = [
        reconcile_remittance_line(
            org_id=org_id,
            platform_order_id=line["platform_order_id"],
            courier=line["courier"],
            remitted=Money.from_major(
                line["remitted_amount"]["amount"],
                line["remitted_amount"].get("currency", "INR"),
            ),
            remittance_date=line["remittance_date"],
            awb_number=line.get("awb_number"),
        )
        for line in lines
    ]
    return {
        "total_lines": len(results),
        "matched": sum(1 for r in results if r["status"] == "matched"),
        "mismatched": sum(1 for r in results if r["status"] == "mismatch"),
        "unmatched_no_expected": sum(1 for r in results if r["status"] == "unmatched_no_expected"),
        "results": results,
    }


def get_summary(org_id: str) -> dict:
    """Aggregate every remittance for an org.

    This is the function float drift hurt most: it sums thousands of rows, so
    per-row representation error accumulates into a headline figure that does
    not match the courier's statement. All accumulation is now integer paise;
    Money objects are constructed only at the boundary, for output.
    """
    rows = store.get_remittances_for_org(org_id, limit=10000)

    by_courier: dict[str, dict] = {}
    currency = "INR"
    for r in rows:
        currency = r.get("currency") or currency
        c = by_courier.setdefault(r["courier"], {
            "courier": r["courier"],
            "_expected_minor": 0, "_remitted_minor": 0, "_discrepancy_minor": 0,
            "mismatch_count": 0, "unmatched_count": 0,
        })
        c["_remitted_minor"] += int(r.get("remitted_amount_minor") or 0)
        if r.get("expected_amount_minor") is not None:
            c["_expected_minor"] += int(r["expected_amount_minor"])
            c["_discrepancy_minor"] += int(r.get("discrepancy_amount_minor") or 0)
        if r["status"] == "mismatch":
            c["mismatch_count"] += 1
        elif r["status"] == "unmatched_no_expected":
            c["unmatched_count"] += 1

    by_courier_list = [
        {
            "courier": v["courier"],
            "mismatch_count": v["mismatch_count"],
            "unmatched_count": v["unmatched_count"],
            "total_expected": Money(v["_expected_minor"], currency).as_dict(),
            "total_remitted": Money(v["_remitted_minor"], currency).as_dict(),
            "total_discrepancy": Money(v["_discrepancy_minor"], currency).as_dict(),
        }
        for v in by_courier.values()
    ]

    # Grand totals summed from the same integers, not from the rounded
    # per-courier outputs -- summing already-rounded values is how a total
    # ends up disagreeing with its own breakdown.
    return {
        "by_courier": by_courier_list,
        "total_expected": Money(
            sum(v["_expected_minor"] for v in by_courier.values()), currency
        ).as_dict(),
        "total_remitted": Money(
            sum(v["_remitted_minor"] for v in by_courier.values()), currency
        ).as_dict(),
        "total_discrepancy": Money(
            sum(v["_discrepancy_minor"] for v in by_courier.values()), currency
        ).as_dict(),
    }


def _serialize(record: dict) -> dict:
    remittance_date = record["remittance_date"]
    if isinstance(remittance_date, datetime):
        remittance_date = remittance_date.strftime("%Y-%m-%d")
    return {
        "id": record["id"],
        "platform_order_id": record["platform_order_id"],
        "courier": record["courier"],
        "awb_number": record.get("awb_number"),
        "remittance_date": remittance_date,
        "remitted_amount": Money(
            int(record["remitted_amount_minor"]), record.get("currency") or "INR"
        ).as_dict(),
        "expected_amount": (
            Money(int(record["expected_amount_minor"]), record.get("currency") or "INR").as_dict()
            if record.get("expected_amount_minor") is not None else None
        ),
        "discrepancy_amount": (
            Money(int(record["discrepancy_amount_minor"]), record.get("currency") or "INR").as_dict()
            if record.get("discrepancy_amount_minor") is not None else None
        ),
        "status": record["status"],
    }
