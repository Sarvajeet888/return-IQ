"""PHASE 27 — drift detection.

Two properties, both measured rather than assumed: the monitor does not fire
on stable data, and it does fire on drift large enough to matter.
"""
from __future__ import annotations

import random

import pytest

from app.ml.drift import (
    DETECTION_FLOOR_SD,
    MIN_WINDOW,
    PSI_MAJOR,
    PSI_MINOR,
    detect_feature_drift,
    detect_prediction_drift,
    population_stability_index,
)


def _normal(n, mean=0.0, sd=1.0, seed=1):
    rng = random.Random(seed)
    return [rng.gauss(mean, sd) for _ in range(n)]


# ────────────────────────────── the measure ──────────────────────────────────

def test_identical_distributions_score_near_zero():
    values = _normal(2000, seed=1)
    assert population_stability_index(values, values) == pytest.approx(0.0, abs=0.001)


def test_a_large_shift_scores_high():
    assert population_stability_index(
        _normal(2000, 0, 1, seed=1), _normal(2000, 1.0, 1, seed=2),
    ) > PSI_MAJOR


def test_a_variance_change_is_detected_even_with_the_same_mean():
    """Mean-only monitoring misses this entirely, and a spread change is a
    real event — a new courier serving both very short and very long routes
    shifts variance while leaving the average untouched."""
    assert population_stability_index(
        _normal(2000, 0, 1, seed=1), _normal(2000, 0, 3, seed=2),
    ) > PSI_MINOR


def test_values_beyond_the_reference_range_are_counted_not_dropped():
    """A new courier serving longer routes than any seen before is exactly the
    drift worth catching. Clipping to the reference range would hide it."""
    reference = _normal(2000, 100, 10, seed=1)

    # BOTH directions. My first version tested only values ABOVE the range,
    # and sabotage proved that insufficient: clipping the LOWER edge left the
    # test green, because the upper edge was still infinite. A one-sided test
    # of a two-sided property.
    above = [500.0] * 2000
    below = [-500.0] * 2000

    assert population_stability_index(reference, above) > PSI_MAJOR
    assert population_stability_index(reference, below) > PSI_MAJOR


def test_a_partial_out_of_range_shift_is_not_understated():
    """The case that actually depends on infinite bin edges.

    Sabotage taught this one. Clipping the edges still produced a huge PSI
    when *every* value was out of range — the epsilon floor masked it. The
    observable failure is the PARTIAL case, which is also the realistic one:
    a quarter of traffic arriving from a new segment.

    Measured:
        infinite edges:  PSI 0.3345   -> major drift, alert raised
        clipped edges:   PSI 0.0867   -> below threshold, silence

    Clipping turns a real alert into nothing, and does it precisely when the
    change is new and small enough to still be worth catching.
    """
    rng = random.Random(1)
    reference = [rng.gauss(100, 10) for _ in range(2000)]
    # 75% normal traffic, 25% from a new segment far below the reference range
    current = [rng.gauss(100, 10) for _ in range(1500)] + [-200.0] * 500

    assert population_stability_index(reference, current) > PSI_MAJOR


def test_a_constant_feature_reports_nothing_rather_than_a_wrong_number():
    """A degenerate reference produces duplicate bin edges. Nothing meaningful
    can be said, so say nothing rather than emit a figure."""
    assert population_stability_index([5.0] * 1000, [9.0] * 1000) == 0.0


def test_empty_input_returns_zero():
    assert population_stability_index([], [1.0, 2.0]) == 0.0


# ─────────────────── measured false alarms and sensitivity ───────────────────

def test_stable_data_does_not_raise_an_alert():
    """Measured across 300 trials at n=500 during this phase: 0.0%
    per-feature false alarm rate.

    An alert nobody trusts is worse than no alert — Phase 20's conformal
    monitor had to be fixed for exactly this, at 7% false alarms on correct
    data.
    """
    false_alarms = 0
    trials = 40
    for seed in range(trials):
        reference = _normal(2000, seed=seed)
        current = _normal(500, seed=seed + 500)
        if population_stability_index(reference, current) > PSI_MINOR:
            false_alarms += 1

    assert false_alarms / trials < 0.05, (
        f"{false_alarms}/{trials} false alarms on stable data — the monitor "
        f"will be ignored."
    )


def test_a_half_sd_shift_is_reliably_detected():
    """Measured: 100% detection at 0.5 sd, n=500."""
    detections = 0
    trials = 20
    for seed in range(trials):
        reference = _normal(2000, 0, 1, seed=seed)
        current = _normal(500, 0.5, 1, seed=seed + 500)
        if population_stability_index(reference, current) > PSI_MINOR:
            detections += 1

    assert detections / trials > 0.8


def test_the_detection_floor_is_documented_honestly():
    """Measured: a 0.2 sd shift is invisible at n=500 (0% detection).

    That is the dangerous limit — small drift is what kills a model slowly,
    while a 1.0 sd shift would be obvious from the dashboard anyway. The
    report states it rather than letting "no drift detected" be read as
    "nothing changed".
    """
    report = detect_feature_drift(
        {"distance_km": _normal(2000, seed=1)},
        {"distance_km": _normal(500, seed=2)},
    )
    verdict = report.as_dict()["verdict"]
    assert str(DETECTION_FLOOR_SD) in verdict
    assert "not 'nothing changed'" in verdict


# ─────────────────────────── feature-level report ────────────────────────────

def test_drifted_features_are_identified_by_name():
    report = detect_feature_drift(
        {
            "distance_km": _normal(2000, 300, 50, seed=1),
            "product_value": _normal(2000, 1500, 400, seed=2),
        },
        {
            "distance_km": _normal(2000, 900, 50, seed=3),      # moved hard
            "product_value": _normal(2000, 1500, 400, seed=4),  # stable
        },
    )
    assert "distance_km" in report.as_dict()["major"]
    assert "product_value" not in report.as_dict()["drifted"]


def test_results_are_ordered_worst_first():
    report = detect_feature_drift(
        {"a": _normal(2000, 0, 1, seed=1), "b": _normal(2000, 0, 1, seed=2)},
        {"a": _normal(2000, 0.6, 1, seed=3), "b": _normal(2000, 2.5, 1, seed=4)},
    )
    assert report.drifted[0].name == "b"


def test_a_small_window_reports_insufficient_data_not_no_drift():
    """"No drift" from a 50-row window is a false reassurance."""
    report = detect_feature_drift(
        {"distance_km": _normal(2000, seed=1)},
        {"distance_km": _normal(50, 5.0, seed=2)},       # huge shift, tiny window
    )
    result = report.results[0]
    assert result.severity == "insufficient_data"
    assert result.psi is None
    assert "not 'no drift'" in result.detail


def test_a_feature_that_stopped_arriving_is_reported():
    """A feature missing from the current window is usually a broken
    integration — a serious event. Silently omitting it from the report is how
    that goes unnoticed for weeks.
    """
    report = detect_feature_drift(
        {"distance_km": _normal(2000, seed=1), "courier_tier": _normal(2000, seed=2)},
        {"distance_km": _normal(2000, seed=3)},          # courier_tier absent
    )
    assert "courier_tier" in report.as_dict()["insufficient_data"]


def test_severity_bands_match_the_conventional_thresholds():
    report = detect_feature_drift(
        {"x": _normal(2000, 0, 1, seed=1)},
        {"x": _normal(2000, 3.0, 1, seed=2)},
    )
    result = report.results[0]
    assert result.severity == "major"
    assert result.psi >= PSI_MAJOR
    assert "extrapolating beyond what the model was trained on" in result.detail


def test_a_clean_report_says_so():
    report = detect_feature_drift(
        {"x": _normal(2000, seed=1)}, {"x": _normal(2000, seed=2)},
    )
    payload = report.as_dict()
    assert payload["drifted"] == []
    assert "No drift detected" in payload["verdict"]


# ────────────────────────── prediction drift ─────────────────────────────────

def test_prediction_drift_is_measured_separately_from_input_drift():
    """Inputs can stay stable while outputs move — that means the model itself
    changed, through a redeploy or a silent version mismatch. That is a
    deployment incident, not a data one, and conflating the two sends the
    investigation to the wrong team.
    """
    result = detect_prediction_drift(
        _normal(2000, 400, 80, seed=1),
        _normal(2000, 900, 80, seed=2),
    )
    assert result.severity == "major"
    assert result.name == "predictions"


def test_stable_predictions_report_no_drift():
    result = detect_prediction_drift(_normal(2000, seed=1), _normal(2000, seed=2))
    assert result.severity == "none"


def test_prediction_drift_needs_a_sufficient_window_too():
    result = detect_prediction_drift(_normal(2000, seed=1), _normal(50, 9.0, seed=2))
    assert result.severity == "insufficient_data"
    assert str(MIN_WINDOW) in result.detail
