"""
Unit tests for courier remittance reconciliation logic.
"""
from __future__ import annotations

from unittest.mock import patch

from app.core.money import Money
from app.services import remittance_service


def _assessment(order_value: str) -> dict:
    """Assessments now carry minor units + currency, not a float rupee value."""
    return {
        "id": "assess-1",
        "order_value_minor": Money.from_major(order_value, "INR").minor_units,
        "currency": "INR",
    }


def _inr(major: str) -> Money:
    return Money.from_major(major, "INR")


def _line(order_id: str, courier: str, amount: str) -> dict:
    """A remittance line as it arrives over the wire (MoneyIn shape)."""
    return {
        "platform_order_id": order_id,
        "courier": courier,
        "remitted_amount": {"amount": amount, "currency": "INR"},
        "remittance_date": "2026-08-01",
    }


def _stub_create(data):
    return {**data, "id": "rem-1"}


# ── Amounts within tolerance count as matched, not a false-positive flag ──────
def test_matching_amount_is_marked_matched():
    with patch.object(remittance_service.store, "get_cod_risk_assessment_by_order_id", return_value=_assessment("1000.00")), \
         patch.object(remittance_service.store, "create_courier_remittance", side_effect=_stub_create):
        result = remittance_service.reconcile_remittance_line(
            org_id="org-1", platform_order_id="ORD-1", courier="Delhivery",
            remitted=_inr("1000.00"), remittance_date="2026-08-01",
        )
    assert result["status"] == "matched"
    assert result["discrepancy_amount"]["minor_units"] == 0


def test_small_rounding_difference_is_still_matched():
    with patch.object(remittance_service.store, "get_cod_risk_assessment_by_order_id", return_value=_assessment("1000.00")), \
         patch.object(remittance_service.store, "create_courier_remittance", side_effect=_stub_create):
        result = remittance_service.reconcile_remittance_line(
            org_id="org-1", platform_order_id="ORD-1", courier="Delhivery",
            remitted=_inr("998.50"), remittance_date="2026-08-01",  # within the Rs 5 tolerance
        )
    assert result["status"] == "matched"


# ── A real underpayment must be flagged as a mismatch ─────────────────────────
def test_underpayment_is_flagged_mismatch():
    with patch.object(remittance_service.store, "get_cod_risk_assessment_by_order_id", return_value=_assessment("1000.00")), \
         patch.object(remittance_service.store, "create_courier_remittance", side_effect=_stub_create):
        result = remittance_service.reconcile_remittance_line(
            org_id="org-1", platform_order_id="ORD-1", courier="Delhivery",
            remitted=_inr("820.00"), remittance_date="2026-08-01",
        )
    assert result["status"] == "mismatch"
    assert result["discrepancy_amount"]["minor_units"] == -18000
    assert result["discrepancy_amount"]["formatted"] == "-\u20b9180.00"


# ── No known expected amount must be flagged distinctly, never guessed ────────
def test_no_matching_assessment_is_unmatched_not_guessed():
    with patch.object(remittance_service.store, "get_cod_risk_assessment_by_order_id", return_value=None), \
         patch.object(remittance_service.store, "create_courier_remittance", side_effect=_stub_create):
        result = remittance_service.reconcile_remittance_line(
            org_id="org-1", platform_order_id="ORD-UNKNOWN", courier="Delhivery",
            remitted=_inr("500.00"), remittance_date="2026-08-01",
        )
    assert result["status"] == "unmatched_no_expected"
    assert result["expected_amount"] is None
    assert result["discrepancy_amount"] is None


# ── Batch reconciliation correctly tallies each status ────────────────────────
def test_batch_reconcile_tallies_statuses_correctly():
    def fake_lookup(org_id, order_id):
        return {"ORD-A": _assessment("1000.00"), "ORD-B": _assessment("500.00")}.get(order_id)

    with patch.object(remittance_service.store, "get_cod_risk_assessment_by_order_id", side_effect=fake_lookup), \
         patch.object(remittance_service.store, "create_courier_remittance", side_effect=_stub_create):
        result = remittance_service.reconcile_batch("org-1", [
            _line("ORD-A", "BlueDart", "1000.00"),
            _line("ORD-B", "BlueDart", "300.00"),
            _line("ORD-C", "BlueDart", "700.00"),
        ])

    assert result["total_lines"] == 3
    assert result["matched"] == 1
    assert result["mismatched"] == 1
    assert result["unmatched_no_expected"] == 1


# ── Summary correctly aggregates totals per courier ────────────────────────────
def test_summary_aggregates_by_courier():
    fake_rows = [
        {"courier": "BlueDart", "currency": "INR", "remitted_amount_minor": 100000,
         "expected_amount_minor": 100000, "discrepancy_amount_minor": 0, "status": "matched"},
        {"courier": "BlueDart", "currency": "INR", "remitted_amount_minor": 30000,
         "expected_amount_minor": 50000, "discrepancy_amount_minor": -20000, "status": "mismatch"},
        {"courier": "Delhivery", "currency": "INR", "remitted_amount_minor": 70000,
         "expected_amount_minor": None, "discrepancy_amount_minor": None,
         "status": "unmatched_no_expected"},
    ]
    with patch.object(remittance_service.store, "get_remittances_for_org", return_value=fake_rows):
        summary = remittance_service.get_summary("org-1")

    bluedart = next(c for c in summary["by_courier"] if c["courier"] == "BlueDart")
    assert bluedart["total_expected"]["minor_units"] == 150000
    assert bluedart["total_remitted"]["minor_units"] == 130000
    assert bluedart["total_remitted"]["formatted"] == "\u20b91,300.00"
    assert bluedart["mismatch_count"] == 1

    delhivery = next(c for c in summary["by_courier"] if c["courier"] == "Delhivery")
    assert delhivery["unmatched_count"] == 1
    assert delhivery["total_expected"]["minor_units"] == 0  # nothing to compare against
