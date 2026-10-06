"""PHASE 21 — explainability.

The property under test: an explanation must be either exact and reconciling,
or clearly labelled as approximate. What it must never be is a plausible story
presented as fact.
"""
from __future__ import annotations

import pytest

from app.ml.explainability import (
    CAUSAL_DISCLAIMER,
    attribution_caveat,
    explain_rule_score,
)


def _fraud_rules():
    return [
        ("Customer return history", 35, "This customer returns 45% of orders (above 40%)"),
        ("Payment method", 15, "Paid cash on delivery"),
        ("Return reason", 10, "Reason given: not_as_described"),
        ("Festive period", 8, "Ordered during a festive sales window"),
    ]


# ─────────────────── exact explanations for rule scores ──────────────────────

def test_contributions_sum_to_the_score():
    """The check that separates an exact explanation from a plausible one.

    An explanation with a silent remainder is worse than none — it looks
    complete.
    """
    e = explain_rule_score("fraud_score", 68.0, baseline=0.0, fired=_fraud_rules())
    assert e.reconciles() is True
    assert sum(c.points for c in e.contributions) == 68.0


def test_a_missing_contribution_is_caught():
    """If a rule fires but is not recorded, reconciliation fails rather than
    quietly producing a partial story."""
    incomplete = _fraud_rules()[:2]          # 50 of 68 points
    e = explain_rule_score("fraud_score", 68.0, baseline=0.0, fired=incomplete)
    assert e.reconciles() is False


def test_each_contribution_states_the_condition_that_fired():
    """"Customer return history: +35" is a label. "returns 45% of orders
    (above 40%)" is an explanation — the merchant can check it."""
    e = explain_rule_score("fraud_score", 68.0, baseline=0.0, fired=_fraud_rules())
    for c in e.contributions:
        assert c.because, f"{c.factor} has no stated condition"
        assert len(c.because) > 10


def test_increases_and_reduces_are_separated_and_ordered():
    """The roadmap's shape: main contributors, then risk reducers."""
    fired = _fraud_rules() + [
        ("Established customer", -12, "Account older than two years"),
        ("Verified address", -5, "Delivery address confirmed on three prior orders"),
    ]
    e = explain_rule_score("fraud_score", 51.0, baseline=0.0, fired=fired)

    assert [c.points for c in e.increases] == [35, 15, 10, 8]        # largest first
    assert [c.points for c in e.reduces] == [-12, -5]                # most negative first


def test_a_capped_score_says_so_rather_than_leaving_a_remainder():
    fired = _fraud_rules() + [("Score capped at 100", -8.0, "Rules totalled 108; capped at 100")]
    e = explain_rule_score("fraud_score", 60.0, baseline=0.0, fired=fired)
    assert any("capped" in c.factor.lower() for c in e.contributions)


def test_exact_method_is_labelled_as_exact():
    e = explain_rule_score("fraud_score", 68.0, baseline=0.0, fired=_fraud_rules())
    payload = e.as_dict()
    assert payload["method"] == "exact_rule"
    assert "every point is accounted for" in payload["method_note"]
    assert payload["reconciles"] is True


# ──────────────────────── the causal disclaimer ──────────────────────────────

def test_every_explanation_carries_the_causal_disclaimer():
    """The roadmap: "Never present explanations as causal proof when they are
    only model-attribution signals."
    """
    e = explain_rule_score("fraud_score", 68.0, baseline=0.0, fired=_fraud_rules())
    assert e.as_dict()["disclaimer"] == CAUSAL_DISCLAIMER
    assert attribution_caveat()["disclaimer"] == CAUSAL_DISCLAIMER


def test_the_disclaimer_distinguishes_what_moved_the_score_from_why():
    assert "not why the return happened" in CAUSAL_DISCLAIMER
    assert "not established causes" in CAUSAL_DISCLAIMER


def test_ml_attribution_is_never_labelled_exact():
    caveat = attribution_caveat()
    assert caveat["method"] == "model_attribution"
    assert "approximate" in caveat["caveat"]


def test_the_attribution_caveat_carries_the_measured_finding():
    """Measured during this phase: across 300 randomised returns spanning
    Rs 200-90,000, 0.1-25kg and 10-2,500km, distance ranked first in 300/300
    and two orderings covered 92% of cases.

    A merchant told "distance was the main driver" for every return they ever
    submit is not being explained anything.
    """
    caveat = attribution_caveat()["caveat"]
    assert "300" in caveat
    assert "92%" in caveat


# ───────────── the invented narratives must not come back ────────────────────

def test_no_causal_narratives_remain_in_the_api():
    """REGRESSION GUARD.

    `ai_ux.py` mapped whichever feature ranked highest onto hardcoded prose
    and served it to merchants as though the model produced it:

        "Festive-season returns correlate with bulk purchasing and impulse
         buying"
        "COD returns carry higher fraud risk and cash reconciliation overhead"

    The model knows nothing about impulse buying. Those were stories a
    developer wrote. This scans live code (comments stripped, since the
    migration note quotes them deliberately) and fails if they return.
    """
    import pathlib

    route = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app/api/v1/routes/ai_ux.py"
    )
    code = "\n".join(
        line.split("#", 1)[0] for line in route.read_text().splitlines()
    )

    for phrase in (
        "impulse buying",
        "driver_interpretations",
        "top_driver_interpretation",
    ):
        assert phrase not in code, (
            f"{phrase!r} is back in live code — a causal narrative is being "
            f"presented as a model explanation."
        )


def test_the_api_still_reports_attribution_with_its_caveat():
    """Removing the narrative must not remove the information — the feature
    is still named, it is just no longer wrapped in an invented reason."""
    import pathlib

    route = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app/api/v1/routes/ai_ux.py"
    )
    code = route.read_text()
    assert "top_attributed_feature" in code
    assert "attribution_caveat" in code
    assert "causal_disclaimer" in code


# ───────────────────────── end-to-end wiring ─────────────────────────────────

def test_score_return_attaches_an_exact_fraud_explanation():
    from app.services.ml_service import score_return

    result = score_return(
        features={
            "product_value": 8000.0, "actual_weight": 0.5, "volumetric_weight": 0.6,
            "chargeable_weight": 0.6, "courier": "Delhivery", "category": "electronics",
            "payment_mode": "COD", "return_reason": "not_as_described",
            "pickup_tier": 1, "destination_tier": 2, "distance_km": 300,
            "fragile": 0, "festive": 1,
            "customer_return_rate": 0.45, "merchant_return_rate": 0.15,
        },
        item_value=8000.0, risk_threshold=50.0, condition="good",
    )

    explanation = result["fraud_explanation"]
    assert explanation["method"] == "exact_rule"
    assert explanation["reconciles"] is True
    assert explanation["score"] == 68.0

    # 35 + 15 + 10 + 8 = 68
    points = [c["points"] for c in explanation["increases_score"]]
    assert sum(points) == 68.0


def test_a_clean_return_produces_an_empty_but_honest_explanation():
    """No rules fired. The explanation should say nothing contributed, not
    invent a reason for a zero."""
    from app.services.ml_service import score_return

    result = score_return(
        features={
            "product_value": 500.0, "actual_weight": 0.2, "volumetric_weight": 0.2,
            "chargeable_weight": 0.2, "courier": "Delhivery", "category": "apparel",
            "payment_mode": "Prepaid", "return_reason": "size_issue",
            "pickup_tier": 1, "destination_tier": 1, "distance_km": 50,
            "fragile": 0, "festive": 0,
            "customer_return_rate": 0.05, "merchant_return_rate": 0.1,
        },
        item_value=500.0, risk_threshold=50.0, condition="good",
    )

    explanation = result["fraud_explanation"]
    assert explanation["score"] == 0.0
    assert explanation["increases_score"] == []
    assert explanation["reconciles"] is True
