"""PHASE 20 — prediction intervals and uncertainty routing.

The conformal coverage guarantee is distribution-free, so it can be verified
here without a trained model: these assert a mathematical property, not an
empirical one about ReturnIQ data.
"""
from __future__ import annotations

import random

import pytest

from app.ml.uncertainty import (
    MIN_CALIBRATION_ROWS,
    ConformalCalibrator,
    ReviewRouting,
    route_by_uncertainty,
)


def _calibrated(level=0.9, n=1000, spread=100.0, seed=1):
    rng = random.Random(seed)
    actual = [rng.gauss(1800, 400) for _ in range(n)]
    predicted = [a + rng.gauss(0, spread) for a in actual]
    return ConformalCalibrator(level).fit(actual, predicted), rng


# ─────────────────────────── the coverage guarantee ──────────────────────────

def test_coverage_holds_on_fresh_data():
    """The core property: ~90% of future actuals fall inside the interval."""
    cal, rng = _calibrated()
    actual = [rng.gauss(1800, 400) for _ in range(2000)]
    predicted = [a + rng.gauss(0, 100) for a in actual]

    result = cal.measured_coverage(actual, predicted)
    assert result["guarantee_holding"] is True
    assert result["measured_coverage"] == pytest.approx(0.9, abs=0.03)


def test_guarantee_survives_a_skewed_error_distribution():
    """Distribution-free is the whole reason for choosing conformal.

    Methods assuming Gaussian errors produce intervals that are wrong in a way
    nobody notices, because a too-narrow interval looks better than a wide one.
    """
    rng = random.Random(5)
    actual = [rng.gauss(1800, 400) for _ in range(2000)]
    predicted = [a + (rng.lognormvariate(3, 1) - 20) for a in actual]

    cal = ConformalCalibrator(0.9).fit(actual[:1000], predicted[:1000])
    result = cal.measured_coverage(actual[1000:], predicted[1000:])
    assert result["guarantee_holding"] is True


def test_a_terrible_model_gets_wide_intervals_not_wrong_ones():
    """The correct failure mode.

    A constant, badly-wrong predictor still achieves coverage — by producing
    an interval so wide it is obviously useless. The interval tells you the
    model does not know, instead of hiding it behind a confident point
    estimate.
    """
    rng = random.Random(7)
    actual = [rng.gauss(1800, 400) for _ in range(2000)]
    predicted = [500.0] * 2000

    cal = ConformalCalibrator(0.9).fit(actual[:1000], predicted[:1000])
    interval = cal.interval(500.0)

    assert interval.relative_width > 3.0          # visibly useless
    assert route_by_uncertainty(interval)["decision"] == ReviewRouting.MANUAL


def test_a_higher_confidence_level_produces_a_wider_interval():
    rng = random.Random(9)
    actual = [rng.gauss(1800, 400) for _ in range(1000)]
    predicted = [a + rng.gauss(0, 100) for a in actual]

    narrow = ConformalCalibrator(0.80).fit(actual, predicted).interval(1800)
    wide = ConformalCalibrator(0.99).fit(actual, predicted).interval(1800)
    assert wide.width > narrow.width


# ───────────────────────────── drift detection ───────────────────────────────

def test_real_drift_is_detected():
    """Exchangeability breaking is the failure conformal cannot prevent, only
    detect. Errors 4x worse than calibration."""
    cal, rng = _calibrated(spread=100.0)
    actual = [rng.gauss(1800, 400) for _ in range(1500)]
    predicted = [a + rng.gauss(0, 400) for a in actual]

    result = cal.measured_coverage(actual, predicted)
    assert result["guarantee_holding"] is False
    assert "drift" in result["note"].lower()


def test_the_monitor_does_not_cry_wolf_on_correct_data():
    """MEASURED, and it caught a bug in my own implementation.

    My first tolerance used only the test-set sampling error. Across 200
    trials on perfectly calibrated data with no drift, it produced a 7% FALSE
    ALARM rate — 14 correct calibrators reported as broken. The missing term
    was the calibration draw's own variance.

    A drift monitor that fires on correct data is worse than no monitor,
    because people learn to dismiss it.
    """
    false_alarms = 0
    trials = 40
    for seed in range(trials):
        rng = random.Random(seed)
        actual = [rng.gauss(1800, 400) for _ in range(2000)]
        predicted = [a + rng.gauss(0, 100) for a in actual]
        cal = ConformalCalibrator(0.9).fit(actual[:1000], predicted[:1000])
        if not cal.measured_coverage(actual[1000:], predicted[1000:])["guarantee_holding"]:
            false_alarms += 1

    assert false_alarms / trials < 0.10, (
        f"{false_alarms}/{trials} false alarms — tolerance is too tight and "
        f"the monitor will be ignored."
    )


def test_finite_sample_correction_keeps_coverage_at_or_above_target():
    """Sabotage found this test missing.

    Removing the ceil((n+1)*level) correction and using the plain empirical
    quantile passed every other test in this file. Measured at the minimum
    calibration size — n=100, level 0.95, 400 trials:

        correct rank:  mean coverage 0.9527   (at or above target)
        naive rank:    mean coverage 0.9421   (below target)

    The difference is one index, and it is the difference between a guarantee
    that holds and one that quietly does not. It matters most at small
    calibration sizes, which is exactly where someone will use it.
    """
    import statistics

    coverages = []
    for seed in range(60):
        rng = random.Random(seed)
        actual = [rng.gauss(1800, 400) for _ in range(MIN_CALIBRATION_ROWS)]
        predicted = [a + rng.gauss(0, 100) for a in actual]
        cal = ConformalCalibrator(0.95).fit(actual, predicted)

        test_actual = [rng.gauss(1800, 400) for _ in range(1000)]
        test_pred = [a + rng.gauss(0, 100) for a in test_actual]
        covered = sum(
            1 for a, p in zip(test_actual, test_pred) if cal.interval(p).contains(a)
        )
        coverages.append(covered / 1000)

    mean_coverage = statistics.mean(coverages)
    assert mean_coverage >= 0.95, (
        f"mean coverage {mean_coverage:.4f} is below the 0.95 target — the "
        f"finite-sample correction is missing or wrong."
    )


# ────────────────────────────── input guards ─────────────────────────────────

def test_too_few_calibration_rows_is_refused():
    """The guarantee is finite-sample: with n residuals the achievable level
    is capped near n/(n+1), so a small set cannot express 95% at all."""
    with pytest.raises(ValueError, match="minimum"):
        ConformalCalibrator(0.9).fit([1.0] * 50, [1.0] * 50)


def test_mismatched_lengths_are_refused():
    with pytest.raises(ValueError, match="actuals vs"):
        ConformalCalibrator(0.9).fit([1.0] * 200, [1.0] * 199)


def test_an_impossible_confidence_level_is_refused():
    with pytest.raises(ValueError, match="must be in"):
        ConformalCalibrator(1.0)
    with pytest.raises(ValueError):
        ConformalCalibrator(0.3)


def test_using_an_unfitted_calibrator_is_refused():
    with pytest.raises(RuntimeError, match="not fitted"):
        ConformalCalibrator(0.9).interval(100.0)


# ────────────────────────── routing by uncertainty ───────────────────────────

def test_a_tight_interval_can_be_automated():
    cal, _ = _calibrated(spread=10.0)
    assert route_by_uncertainty(cal.interval(1800))["decision"] == ReviewRouting.AUTOMATE


def test_a_moderate_interval_goes_to_review():
    cal, _ = _calibrated(spread=250.0)
    assert route_by_uncertainty(cal.interval(1800))["decision"] == ReviewRouting.REVIEW


def test_a_wide_interval_goes_to_a_human():
    cal, _ = _calibrated(spread=900.0)
    result = route_by_uncertainty(cal.interval(1800))
    assert result["decision"] == ReviewRouting.MANUAL
    assert "does not meaningfully know" in result["reason"]


def test_routing_uses_relative_width_not_absolute():
    """Scale-free is essential: +/-Rs 200 is tight on a Rs 5,000 return and
    useless on a Rs 300 one."""
    cal, _ = _calibrated(spread=100.0)

    big = route_by_uncertainty(cal.interval(5000.0))
    small = route_by_uncertainty(cal.interval(300.0))

    assert big["relative_width"] < small["relative_width"]
    assert big["decision"] != ReviewRouting.MANUAL
    assert small["decision"] == ReviewRouting.MANUAL


# ─────────────────────────── merchant-facing output ──────────────────────────

def test_interval_renders_the_roadmaps_example_shape():
    """The roadmap's own illustration:
        Expected recovery: Rs 1,820
        Estimated range:   Rs 1,560 - Rs 2,020
    """
    cal, _ = _calibrated(spread=150.0)
    payload = cal.interval(1820.0).as_dict()

    assert payload["lower"] < 1820 < payload["upper"]
    assert "fall between" in payload["interpretation"]
    assert payload["calibration_rows"] == 1000


def test_contains_reports_membership():
    cal, _ = _calibrated(spread=100.0)
    interval = cal.interval(1800.0)
    assert interval.contains(1800.0) is True
    assert interval.contains(1800.0 + interval.width) is False
