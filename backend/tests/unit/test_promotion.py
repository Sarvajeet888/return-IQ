"""PHASE 28 — model promotion gates.

The property under test: a model that fails the Phase 18/19 criteria cannot
reach production silently.
"""
from __future__ import annotations

import pytest

from app.ml.promotion import (
    MAX_CALIBRATION_ERROR,
    MAX_SCORE_SPREAD,
    ModelCard,
    evaluate_promotion,
)


def _card(**overrides):
    """A model that passes everything."""
    base = dict(
        version="v1.2.0",
        model_key="fraud",
        training_dataset_id="ds-2026-07",
        training_period=("2026-01-01", "2026-06-30"),
        training_rows=8_400,
        code_version="a1b2c3d",
        owner="om@kalman.example",
        primary_metric="pr_auc",
        metric_value=0.42,
        baseline_value=0.06,
        score_spread=0.02,
        calibration_error=0.04,
        failing_segments=[],
        replaces="v1.1.0",
    )
    base.update(overrides)
    return ModelCard(**base)


def _failed(decision):
    return {c.name for c in decision.blocking_failures}


# ─────────────────────────── the gate opens ──────────────────────────────────

def test_a_good_model_is_promoted():
    """The gate must open, or it is a wall and the feature is a lie."""
    decision = evaluate_promotion(_card())
    assert decision.allowed is True
    assert decision.blocking_failures == []
    assert "All promotion checks passed" in decision.as_dict()["verdict"]


# ────────────────────── each check blocks on its own ─────────────────────────

def test_a_model_that_cannot_beat_the_baseline_is_blocked():
    """"Always guess the average" is free. A model that ties it lends false
    authority to a coin flip."""
    decision = evaluate_promotion(_card(metric_value=0.061, baseline_value=0.06))
    assert "beats_baseline" in _failed(decision)
    assert decision.allowed is False


def test_a_worse_than_baseline_model_is_blocked():
    decision = evaluate_promotion(_card(metric_value=0.03, baseline_value=0.06))
    assert "beats_baseline" in _failed(decision)


def test_lower_is_better_metrics_are_handled():
    """MAE improving means going DOWN. Treating every metric as
    higher-is-better would block every good regression model and promote every
    bad one."""
    good = evaluate_promotion(
        _card(primary_metric="mae", metric_value=120.0, baseline_value=180.0,
              calibration_error=None),
        lower_metric_is_better=True,
    )
    bad = evaluate_promotion(
        _card(primary_metric="mae", metric_value=220.0, baseline_value=180.0,
              calibration_error=None),
        lower_metric_is_better=True,
    )
    assert "beats_baseline" not in _failed(good)
    assert "beats_baseline" in _failed(bad)


def test_an_unstable_model_is_blocked():
    """Phase 18 measured this: at a 6% base rate, PR-AUC varied by 0.165
    across seeds alone. A model that disagrees with itself is reporting a
    lucky draw."""
    decision = evaluate_promotion(_card(score_spread=MAX_SCORE_SPREAD + 0.1))
    assert "stable_across_seeds" in _failed(decision)


def test_a_miscalibrated_model_is_blocked():
    """Phase 24 multiplies these probabilities by costs. A model off by 15
    percentage points makes the money wrong, not just the score."""
    decision = evaluate_promotion(
        _card(calibration_error=MAX_CALIBRATION_ERROR + 0.05)
    )
    assert "calibrated" in _failed(decision)


def test_calibration_is_not_required_for_regression_models():
    """It is not a meaningful concept for a model predicting rupees."""
    decision = evaluate_promotion(_card(calibration_error=None))
    calibration = next(c for c in decision.checks if c.name == "calibrated")
    assert calibration.blocking is False
    assert decision.allowed is True


def test_failing_segments_block_promotion():
    """Phase 19 measured this: overall MAE Rs 395 while electronics was off by
    Rs 1,882. A merchant whose entire catalogue sits in a failing segment
    experiences this as "the product does not work"."""
    decision = evaluate_promotion(_card(failing_segments=["electronics", "furniture"]))
    assert "no_failing_segments" in _failed(decision)
    detail = next(c for c in decision.checks if c.name == "no_failing_segments").detail
    assert "electronics" in detail


# ───────────────────────────── provenance ────────────────────────────────────

def test_missing_provenance_blocks_promotion():
    """Six months from now, "why is the model behaving differently?" is
    answerable only if you can see what it trained on and who deployed it."""
    decision = evaluate_promotion(_card(training_dataset_id="", owner=""))
    assert "provenance_recorded" in _failed(decision)
    detail = next(c for c in decision.checks if c.name == "provenance_recorded").detail
    assert "training_dataset_id" in detail
    assert "owner" in detail


def test_recorded_provenance_appears_in_the_detail():
    decision = evaluate_promotion(_card())
    detail = next(c for c in decision.checks if c.name == "provenance_recorded").detail
    assert "ds-2026-07" in detail
    assert "8,400 rows" in detail
    assert "a1b2c3d" in detail


def test_a_first_model_notes_it_has_no_rollback_target():
    """Non-blocking, but worth knowing before promoting: there is nothing to
    fall back to."""
    decision = evaluate_promotion(_card(replaces=None))
    rollback = next(c for c in decision.checks if c.name == "rollback_target")
    assert rollback.blocking is False
    assert "nothing to roll back to" in rollback.detail
    assert decision.allowed is True


# ────────────────────────────── overrides ────────────────────────────────────

def test_an_override_allows_promotion_and_is_recorded():
    """A gate with no override gets bypassed by copying files around it, which
    leaves no trace at all. An override that is recorded is strictly better.
    """
    decision = evaluate_promotion(
        _card(failing_segments=["electronics"]),
        override_reason=(
            "Electronics is 2% of this merchant's volume and is handled "
            "manually under an agreed exception."
        ),
        override_by="om@kalman.example",
    )
    payload = decision.as_dict()

    assert decision.allowed is True
    assert payload["overridden"] is True
    assert payload["override_by"] == "om@kalman.example"
    # The failures are still listed — the override permits, it does not erase.
    assert payload["blocking_failures"] == ["no_failing_segments"]


def test_an_anonymous_override_is_refused():
    with pytest.raises(ValueError, match="named person"):
        evaluate_promotion(
            _card(failing_segments=["electronics"]),
            override_reason="It is fine, we checked it and it looks okay to me",
            override_by=None,
        )


def test_a_thin_override_reason_is_refused():
    with pytest.raises(ValueError, match="at least 20 characters"):
        evaluate_promotion(
            _card(failing_segments=["electronics"]),
            override_reason="fine",
            override_by="om@kalman.example",
        )


# ─────────────────────── multiple failures reported ──────────────────────────

def test_every_failure_is_reported_not_just_the_first():
    """Fixing one blocker and rerunning to discover the next is how a
    promotion takes a week."""
    decision = evaluate_promotion(_card(
        metric_value=0.05, baseline_value=0.06,
        score_spread=0.3,
        calibration_error=0.4,
        failing_segments=["electronics"],
        owner="",
    ))
    assert len(decision.blocking_failures) >= 5


def test_the_verdict_explains_what_to_do_next():
    decision = evaluate_promotion(_card(score_spread=0.9))
    verdict = decision.as_dict()["verdict"]
    assert "Fix them" in verdict
    assert "written override" in verdict


def test_every_check_explains_why_it_exists():
    """A blocked promotion with an unexplained reason gets overridden by
    whoever is in a hurry."""
    for check in evaluate_promotion(_card()).checks:
        assert check.detail
        assert len(check.detail) > 40
