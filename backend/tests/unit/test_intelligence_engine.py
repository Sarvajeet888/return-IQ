"""PHASE 14 — Intelligence Engine.

These test a property that is unusual to test but matters more than accuracy
here: that the system does not claim to know more than it does.
"""
from __future__ import annotations

import pytest

from app.services import intelligence_engine as ie
from app.services.intelligence_engine import Confidence, Provenance


def _scoring_result(**overrides):
    base = {
        "predicted_cost_inr": 320.0,
        "fraud_score": 82.0,
        "damage_probability": 0.4,
        "resale_value_estimate": 900.0,
        "carbon_footprint_kg": 2.1,
        "risk_score": 55.0,
        "model_version": "cost_xgb_v1.0.0",
    }
    base.update(overrides)
    return base


# ─────────────────────────── provenance is honest ────────────────────────────

def test_only_the_cost_model_is_labelled_as_ml():
    """The core correction.

    One trained model exists. Four of the other numbers are hand-written
    rules or arithmetic. Labelling them all as "AI" is the overclaim this
    phase removes.
    """
    report = ie.build_report(_scoring_result())
    ml_signals = [s.name for s in report.signals if s.provenance == Provenance.ML_MODEL]
    assert ml_signals == ["predicted_cost"]


def test_fraud_score_is_labelled_a_rule_not_a_model():
    """A merchant reading 'fraud score 82' reasonably assumes a model assessed
    the customer. It is `+= 25 if COD, += 15 if festive`."""
    signal = ie.build_report(_scoring_result()).get("fraud_score")
    assert signal.provenance == Provenance.RULE
    assert "not a trained fraud model" in signal.caveat.lower()


def test_every_signal_states_what_produced_it():
    for signal in ie.build_report(_scoring_result()).signals:
        assert signal.basis, f"{signal.name} has no stated basis"
        assert signal.provenance in {
            Provenance.ML_MODEL, Provenance.RULE,
            Provenance.DERIVED, Provenance.OBSERVED,
        }


def test_the_cost_model_carries_its_synthetic_data_caveat():
    """The top blocker from the baseline audit, attached to the number it
    affects rather than buried in a document nobody opens."""
    signal = ie.build_report(_scoring_result()).get("predicted_cost")
    assert "synthetic" in signal.caveat.lower()


# ────────────────────────────── confidence ───────────────────────────────────

def test_the_ml_signal_is_low_confidence_not_high():
    """It is the only trained model, and it is the *least* trustworthy signal,
    because it is the one trained on data that was generated rather than
    observed. Rules at least do exactly what they say."""
    assert ie.build_report(_scoring_result()).get("predicted_cost").confidence == Confidence.LOW


def test_overall_confidence_is_the_weakest_link():
    """Averaging would let four moderate rules mask the one low-confidence
    model output the recommendation actually depends on."""
    report = ie.build_report(_scoring_result())
    assert Confidence.MODERATE in {s.confidence for s in report.signals}
    assert report.overall_confidence == Confidence.LOW


def test_low_confidence_routes_to_a_human():
    report = ie.build_report(_scoring_result())
    assert report.requires_human_review is True


def test_confidence_is_banded_not_a_false_decimal():
    """0.87 implies a calibration that does not exist. A band says the
    truthful thing: directional, not measured."""
    for signal in ie.build_report(_scoring_result()).signals:
        assert isinstance(signal.confidence, str)
        assert signal.confidence in {
            Confidence.HIGH, Confidence.MODERATE,
            Confidence.LOW, Confidence.UNKNOWN,
        }


# ──────────────── the specific number this phase replaced ────────────────────

def test_reported_confidence_is_capped_while_data_is_synthetic():
    """The old computation could report 0.99.

    It was `min(0.85 + (risk_score < 80)*0.1 + (item_value < 5000)*0.04, 0.99)`
    — arithmetic on the risk score and item value, never consulting the model,
    with a comment citing an unverifiable R2 of 0.999.
    """
    from app.services.ml_service import _MODEL_CONFIDENCE_CEILING
    assert _MODEL_CONFIDENCE_CEILING <= 0.5, (
        "Confidence must stay low while the cost model is trained on "
        "synthetic data. Raise this only after validating predictions "
        "against real returns."
    )


def test_old_confidence_formula_is_gone():
    """Guards against the formula being restored during a future refactor.

    Its four possible outputs had a cliff at item_value 5000: Rs 4,999
    reported 0.99 and Rs 5,001 reported 0.95, for no reason a merchant could
    ever discover.
    """
    import inspect
    import re

    from app.services import ml_service

    source = inspect.getsource(ml_service.score_return)
    # Strip comments before scanning: the migration note deliberately quotes
    # the old formula so the reason survives, and matching that would make the
    # test fail on its own documentation. (First draft of this assertion had
    # an `or True` tacked on, which made it pass unconditionally — exactly the
    # decorative-test failure this project keeps catching. Rewritten.)
    code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", code)

    assert "0.85+(risk_score<80)" not in compact, (
        "The fabricated confidence formula has been reintroduced."
    )
    assert "(item_value<5000)*0.04" not in compact
    assert "_MODEL_CONFIDENCE_CEILING" in compact


# ──────────────────────────── report mechanics ───────────────────────────────

def test_missing_signals_are_omitted_not_invented():
    """A signal the scorer did not produce must be absent, not defaulted to
    zero. Zero fraud risk is a claim; silence is not."""
    result = _scoring_result()
    del result["fraud_score"]
    report = ie.build_report(result)
    assert report.get("fraud_score") is None
    assert "fraud_score" not in {s.name for s in report.signals}


def test_report_serialises_for_the_api():
    payload = ie.build_report(_scoring_result(), return_id="RI-1").as_dict()
    assert payload["return_id"] == "RI-1"
    assert payload["overall_confidence"] == Confidence.LOW
    assert payload["requires_human_review"] is True
    assert len(payload["signals"]) == 6


def test_disclosure_text_explains_the_labels():
    """The report is read by merchants, not only engineers."""
    disclosure = ie.build_report(_scoring_result()).as_dict()["disclosure"]
    assert "hand-written heuristic" in disclosure
    assert "trained model" in disclosure


def test_empty_result_produces_an_empty_report():
    report = ie.build_report({})
    assert report.signals == []
    assert report.overall_confidence == Confidence.UNKNOWN
    assert report.requires_human_review is True      # no basis == not automatic


# ─────────────────────────── end-to-end wiring ───────────────────────────────

def test_score_return_attaches_the_report():
    from app.services.ml_service import score_return

    result = score_return(
        features={
            "product_value": 1500.0, "actual_weight": 0.5, "volumetric_weight": 0.6,
            "chargeable_weight": 0.6, "courier": "Delhivery", "category": "apparel",
            "payment_mode": "COD", "return_reason": "damaged", "pickup_tier": 1,
            "destination_tier": 2, "distance_km": 300, "fragile": 0, "festive": 0,
            "customer_return_rate": 0.2, "merchant_return_rate": 0.15,
        },
        item_value=1500.0,
        risk_threshold=50.0,
        condition="good",
    )

    assert "intelligence" in result
    intelligence = result["intelligence"]
    assert intelligence["overall_confidence"] == Confidence.LOW
    assert intelligence["requires_human_review"] is True

    # And the flat confidence field no longer reports near-certainty.
    assert float(result["confidence_score"]) <= 0.5
