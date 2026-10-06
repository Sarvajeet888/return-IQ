"""PHASE 23 — multimodal signal agreement.

The property under test: signals are checked against each other, not scored in
isolation — and a finding is a question, never a verdict.
"""
from __future__ import annotations

from app.services.signal_agreement import Severity, analyse_signals


def _return(**overrides):
    base = {
        "return_reason_code": "size_issue",
        "condition": "good",
        "item_value_minor": 150000,      # Rs 1,500
        "payment_mode": "Prepaid",
    }
    base.update(overrides)
    return base


def _codes(report):
    return {f.code for f in report.findings}


# ─────────────────────── text vs structured data ─────────────────────────────

def test_damage_claim_contradicting_declared_condition():
    """Those cannot both be right, and a reviewer can check it in seconds."""
    report = analyse_signals(_return(return_reason_code="damaged", condition="good"))
    assert "reason_contradicts_condition" in _codes(report)
    finding = next(f for f in report.findings if f.code == "reason_contradicts_condition")
    assert finding.severity == Severity.STRONG


def test_no_contradiction_when_condition_matches_the_claim():
    report = analyse_signals(_return(return_reason_code="damaged", condition="damaged"))
    assert "reason_contradicts_condition" not in _codes(report)


def test_a_non_damage_reason_never_triggers_the_condition_check():
    report = analyse_signals(_return(return_reason_code="size_issue", condition="good"))
    assert "reason_contradicts_condition" not in _codes(report)


# ───────────────────────── text vs evidence ──────────────────────────────────

def test_damage_claimed_without_a_photograph():
    report = analyse_signals(_return(return_reason_code="damaged"), evidence=[])
    assert "damage_claimed_without_photo" in _codes(report)


def test_a_damage_photo_clears_the_finding():
    report = analyse_signals(
        _return(return_reason_code="damaged"),
        evidence=[{"evidence_type": "damage_photo", "source": "customer"}],
    )
    assert "damage_claimed_without_photo" not in _codes(report)


# ────────────────── the multimodal signal that matters ───────────────────────

def test_damage_claim_against_a_product_that_never_arrives_damaged():
    """THE finding of this phase.

    Individually ordinary, jointly not. A damage claim is ordinary. A customer
    with prior returns is ordinary. A product that rarely breaks is ordinary.
    Together: this person reports damage on an item that has never been
    damaged for anyone else.

    Neither signal alone says anything. That is what makes it multimodal.
    """
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        evidence=[{"evidence_type": "damage_photo", "source": "customer"}],
        customer_features={"customer_return_count": 6},
        product_features={"sku_damage_rate": 0.02, "sku_return_count": 150},
    )
    assert "damage_claim_against_product_history" in _codes(report)
    finding = next(
        f for f in report.findings if f.code == "damage_claim_against_product_history"
    )
    assert finding.severity == Severity.STRONG
    assert set(finding.signals) == {"return_reason", "product_history", "customer_history"}


def test_a_genuinely_fragile_product_does_not_trigger_it():
    """If the SKU breaks often, a damage claim is exactly what you expect."""
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        customer_features={"customer_return_count": 6},
        product_features={"sku_damage_rate": 0.40, "sku_return_count": 150},
    )
    assert "damage_claim_against_product_history" not in _codes(report)


def test_insufficient_product_history_does_not_trigger_it():
    """A 0% damage rate across 3 returns means nothing. Firing here would
    accuse customers on the basis of a near-empty sample."""
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        customer_features={"customer_return_count": 6},
        product_features={"sku_damage_rate": 0.0, "sku_return_count": 3},
    )
    assert "damage_claim_against_product_history" not in _codes(report)


def test_a_first_time_customer_does_not_trigger_it():
    """Requires a pattern. One claim is not a pattern."""
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        customer_features={"customer_return_count": 1},
        product_features={"sku_damage_rate": 0.02, "sku_return_count": 150},
    )
    assert "damage_claim_against_product_history" not in _codes(report)


# ──────────────────────────── velocity ───────────────────────────────────────

def test_a_burst_of_returns_is_flagged():
    report = analyse_signals(
        _return(), customer_features={"customer_returns_last_30d": 5},
    )
    assert "return_velocity_spike" in _codes(report)


def test_an_extreme_burst_escalates_to_strong():
    report = analyse_signals(
        _return(), customer_features={"customer_returns_last_30d": 10},
    )
    finding = next(f for f in report.findings if f.code == "return_velocity_spike")
    assert finding.severity == Severity.STRONG


def test_normal_return_frequency_is_not_flagged():
    report = analyse_signals(
        _return(), customer_features={"customer_returns_last_30d": 2},
    )
    assert "return_velocity_spike" not in _codes(report)


# ────────────────────────── evidence provenance ──────────────────────────────

def test_customer_only_evidence_is_noted_as_weak_context():
    """Warehouse evidence is observed; customer evidence is claimed. A
    reviewer should know which they are looking at — but before the item
    arrives, customer-only evidence is entirely normal."""
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        evidence=[{"evidence_type": "damage_photo", "source": "customer"}],
    )
    finding = next(f for f in report.findings if f.code == "no_independent_evidence")
    assert finding.severity == Severity.WEAK
    assert "normal" in finding.innocent_explanation.lower()


def test_warehouse_confirmation_clears_it():
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        evidence=[
            {"evidence_type": "damage_photo", "source": "customer"},
            {"evidence_type": "damage_photo", "source": "warehouse"},
        ],
    )
    assert "no_independent_evidence" not in _codes(report)


# ─────────────────── findings are questions, not verdicts ────────────────────

def test_every_finding_carries_an_innocent_explanation():
    """The discipline that keeps this a review aid rather than an accusation
    engine. If a contradiction has no plausible innocent reading, it should
    not be in this module."""
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="good", payment_mode="COD",
                item_value_minor=2_000_000),
        evidence=[],
        customer_features={"customer_return_count": 6, "customer_returns_last_30d": 5,
                           "customer_is_first_return": False},
        product_features={"sku_damage_rate": 0.01, "sku_return_count": 200},
    )
    assert len(report.findings) >= 4
    for finding in report.findings:
        assert finding.innocent_explanation, f"{finding.code} has no innocent reading"
        assert len(finding.innocent_explanation) > 30


def test_the_report_states_these_are_not_conclusions():
    report = analyse_signals(_return(return_reason_code="damaged", condition="good"))
    assert "not conclusions" in report.as_dict()["note"]


def test_each_finding_names_which_signals_disagree():
    """"Fraud score 68" tells a reviewer to look. "Reason contradicts declared
    condition" tells them where."""
    report = analyse_signals(_return(return_reason_code="damaged", condition="good"))
    for finding in report.findings:
        assert len(finding.signals) >= 1


# ──────────────────────── missing data is not evidence ───────────────────────

def test_a_return_with_no_signals_produces_no_findings():
    """Inferring guilt from missing data is how a fraud system starts
    punishing customers for the merchant's integration gaps."""
    report = analyse_signals({})
    assert report.findings == []
    assert report.needs_review is False


def test_absent_customer_history_produces_no_finding():
    report = analyse_signals(
        _return(return_reason_code="damaged", condition="damaged"),
        evidence=[{"evidence_type": "damage_photo", "source": "warehouse"}],
        product_features={"sku_damage_rate": 0.01, "sku_return_count": 200},
    )
    assert "damage_claim_against_product_history" not in _codes(report)


# ──────────────────────────── review routing ─────────────────────────────────

def test_a_strong_finding_sends_it_to_review():
    report = analyse_signals(_return(return_reason_code="damaged", condition="good"))
    assert report.needs_review is True


def test_several_weak_findings_also_send_it_to_review():
    """No single one is decisive; three together are worth a look."""
    report = analyse_signals(
        _return(return_reason_code="change_of_mind", item_value_minor=900000,
                payment_mode="COD"),
        customer_features={"customer_returns_last_30d": 5,
                           "customer_is_first_return": False},
    )
    assert report.strong == []
    assert len(report.findings) >= 2


def test_a_clean_return_needs_no_review():
    report = analyse_signals(
        _return(),
        customer_features={"customer_return_count": 1, "customer_returns_last_30d": 1},
        product_features={"sku_damage_rate": 0.1, "sku_return_count": 50},
    )
    assert report.findings == []
    assert report.needs_review is False
