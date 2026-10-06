"""PHASE 30 — organization-specific calibration.

Two properties: a merchant the global model misjudges gets corrected, and no
merchant's data ever touches another's prediction.
"""
from __future__ import annotations

import pytest

from app.ml.org_calibration import (
    MAX_CORRECTION_FACTOR,
    MIN_CALIBRATION_OUTCOMES,
    apply_calibration,
    fit_org_calibration,
)


def _outcomes(n, predicted=100.0, ratio=1.0):
    """n outcomes where actuals are `ratio` times predictions."""
    return [{"predicted": predicted, "actual": predicted * ratio} for _ in range(n)]


# ─────────────────────────── the correction ──────────────────────────────────

def test_a_systematically_underpredicted_org_is_corrected():
    """An electronics seller has a higher base damage rate than an apparel
    seller. A global model trained mostly on apparel under-predicts for them
    consistently — while still ordering their returns correctly."""
    calibration = fit_org_calibration("org-electronics", "cost", _outcomes(500, ratio=1.4))

    assert calibration.applied is True
    assert calibration.factor == pytest.approx(1.4)
    assert "under-predicts by 40%" in calibration.reason


def test_a_systematically_overpredicted_org_is_corrected():
    calibration = fit_org_calibration("org-apparel", "cost", _outcomes(500, ratio=0.7))
    assert calibration.factor == pytest.approx(0.7)
    assert "over-predicts by 30%" in calibration.reason


def test_the_correction_is_applied_to_predictions():
    calibration = fit_org_calibration("org-1", "cost", _outcomes(500, ratio=1.4))
    assert apply_calibration(1000.0, calibration) == pytest.approx(1400.0)


def test_summed_ratios_are_used_not_per_row_ratios():
    """Per-row ratios explode near zero: a single Rs 2 prediction against a
    Rs 400 actual would dominate the entire correction with a ratio of 200."""
    outcomes = _outcomes(400, predicted=100.0, ratio=1.1)
    outcomes.append({"predicted": 2.0, "actual": 400.0})      # ratio of 200

    calibration = fit_org_calibration("org-1", "cost", outcomes)
    # Summed: (400*110 + 400) / (400*100 + 2) = 44400/40002 ~= 1.11
    assert calibration.factor == pytest.approx(1.11, abs=0.02)


# ──────────────────────── refusing to over-fit ───────────────────────────────

def test_too_few_outcomes_leaves_the_global_model_alone():
    """Below the floor a correction is fitted on noise."""
    calibration = fit_org_calibration("org-new", "cost", _outcomes(50, ratio=1.8))

    assert calibration.applied is False
    assert calibration.factor is None
    assert "fitted on noise" in calibration.reason


def test_an_uncalibrated_org_gets_the_global_prediction_unchanged():
    """Falling back is the correct default, not a degraded one. A new merchant
    gets the model trained on everyone else's data — the best available
    estimate for them."""
    calibration = fit_org_calibration("org-new", "cost", _outcomes(50))
    assert apply_calibration(1000.0, calibration) == 1000.0


def test_a_tiny_difference_is_not_applied():
    """A 2% correction is inside the noise of a 200-row sample, and a change
    that does nothing still has to be explained to whoever finds it later."""
    calibration = fit_org_calibration("org-1", "cost", _outcomes(500, ratio=1.02))
    assert calibration.applied is False
    assert "inside the noise" in calibration.reason


def test_an_extreme_correction_is_refused_not_applied():
    """A merchant needing a 3x correction does not have a calibration problem.

    The global model does not describe their business, and quietly scaling its
    output would hide that behind a number that looks adjusted.
    """
    calibration = fit_org_calibration("org-odd", "cost", _outcomes(500, ratio=3.0))

    assert calibration.applied is False
    assert calibration.factor == pytest.approx(3.0)      # reported, not hidden
    assert "does not describe this business" in calibration.reason


def test_an_extreme_correction_in_the_other_direction_is_also_refused():
    calibration = fit_org_calibration("org-odd", "cost", _outcomes(500, ratio=0.2))
    assert calibration.applied is False


def test_the_boundary_of_the_correction_limit():
    just_inside = fit_org_calibration(
        "org-1", "cost", _outcomes(500, ratio=MAX_CORRECTION_FACTOR - 0.01),
    )
    just_outside = fit_org_calibration(
        "org-1", "cost", _outcomes(500, ratio=MAX_CORRECTION_FACTOR + 0.01),
    )
    assert just_inside.applied is True
    assert just_outside.applied is False


# ──────────────────────────── tenant isolation ───────────────────────────────

def test_two_orgs_produce_independent_calibrations():
    """Phase 4's rule applied to ML. A calibration fitted on merchant A and
    applied to merchant B is one merchant's commercial behaviour leaking into
    another's predictions — harder to notice than a data leak and just as much
    a breach.
    """
    a = fit_org_calibration("org-a", "cost", _outcomes(500, ratio=1.4))
    b = fit_org_calibration("org-b", "cost", _outcomes(500, ratio=0.75))

    assert a.factor == pytest.approx(1.4)
    assert b.factor == pytest.approx(0.75)
    assert a.org_id != b.org_id
    assert apply_calibration(1000.0, a) != apply_calibration(1000.0, b)


def test_a_calibration_records_which_org_it_belongs_to():
    """Without this, a calibration object could be applied to the wrong org
    with nothing in the data to reveal it."""
    calibration = fit_org_calibration("org-a", "cost", _outcomes(500, ratio=1.4))
    assert calibration.org_id == "org-a"
    assert calibration.model_key == "cost"


# ────────────────────────────── edge cases ───────────────────────────────────

def test_rows_missing_a_prediction_or_actual_are_not_counted():
    """A row without an outcome is not evidence of anything, and counting it
    toward the minimum would let an org cross the threshold on empty rows."""
    outcomes = _outcomes(150, ratio=1.4) + [
        {"predicted": 100.0, "actual": None} for _ in range(100)
    ]
    calibration = fit_org_calibration("org-1", "cost", outcomes)

    assert calibration.outcomes_used == 150
    assert calibration.applied is False        # 150 < the 200 floor


def test_zero_predictions_report_no_level_to_correct():
    outcomes = [{"predicted": 0.0, "actual": 100.0} for _ in range(500)]
    calibration = fit_org_calibration("org-1", "cost", outcomes)
    assert calibration.applied is False
    assert "no level to correct" in calibration.reason


def test_no_outcomes_at_all_is_handled():
    calibration = fit_org_calibration("org-new", "cost", [])
    assert calibration.applied is False
    assert calibration.outcomes_used == 0


def test_exactly_the_minimum_number_of_outcomes_calibrates():
    calibration = fit_org_calibration(
        "org-1", "cost", _outcomes(MIN_CALIBRATION_OUTCOMES, ratio=1.3),
    )
    assert calibration.applied is True
