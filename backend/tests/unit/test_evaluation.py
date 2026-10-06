"""PHASE 19 — segmented model evaluation.

The property under test: a model that is broken on one slice must not be able
to hide behind a healthy aggregate.
"""
from __future__ import annotations

import pytest

from app.ml.evaluation import (
    DEGRADATION_RATIO,
    MIN_SEGMENT_ROWS,
    classification_metrics,
    evaluate_by_segment,
    regression_metrics,
)


# ────────────────────────── regression metrics ───────────────────────────────

def test_perfect_predictions_score_zero_error():
    m = regression_metrics([100.0, 200.0, 300.0], [100.0, 200.0, 300.0])
    assert m["mae"] == 0.0
    assert m["rmse"] == 0.0
    assert m["r2"] == pytest.approx(1.0)


def test_mean_bias_distinguishes_systematic_from_noisy_error():
    """A model biased 20% low is a different problem from one that is noisy in
    both directions, and |error| cannot tell them apart."""
    biased = regression_metrics([100.0, 100.0, 100.0], [80.0, 80.0, 80.0])
    noisy = regression_metrics([100.0, 100.0, 100.0], [80.0, 120.0, 100.0])

    assert biased["mae"] == pytest.approx(20.0)
    assert biased["mean_bias"] == pytest.approx(20.0)      # consistently under
    assert noisy["mean_bias"] == pytest.approx(0.0)        # cancels out


def test_median_absolute_error_reveals_a_few_extreme_failures():
    """A large gap between MAE and median tells you the model has a failure
    mode rather than a general weakness — a different problem with a different
    fix."""
    actual = [100.0] * 20
    predicted = [100.0] * 19 + [5000.0]

    m = regression_metrics(actual, predicted)
    assert m["median_absolute_error"] == 0.0        # typical case is perfect
    assert m["mae"] > 200                            # mean is dragged


def test_r2_is_none_when_every_actual_is_identical():
    """Undefined, not 0.0 or 1.0. Either number would be a claim."""
    assert regression_metrics([50.0] * 10, [50.0] * 10)["r2"] is None


def test_mape_excludes_near_zero_actuals_and_says_so():
    """MAPE explodes near zero. Silently producing a percentage in the
    millions would be worse than excluding the rows."""
    m = regression_metrics([0.0, 100.0, 200.0], [10.0, 110.0, 210.0])
    assert m["mape_excluded_rows"] == 1
    assert m["mape"] == pytest.approx(0.075, abs=0.01)


def test_empty_input_returns_empty_not_a_crash():
    assert regression_metrics([], []) == {}


# ──────────────────────── classification metrics ─────────────────────────────

def test_confusion_matrix_is_reported():
    actual = [1, 1, 0, 0]
    proba = [0.9, 0.2, 0.8, 0.1]
    cm = classification_metrics(actual, proba)["confusion_matrix"]
    assert cm == {"true_positive": 1, "false_positive": 1,
                  "false_negative": 1, "true_negative": 1}


def test_accuracy_is_computed_but_not_first():
    """At a 5% base rate, predicting 'never' scores 95%. Technically correct,
    completely misleading — and putting it at the top of a report is how it
    ends up in a slide."""
    actual = [0] * 95 + [1] * 5
    proba = [0.0] * 100                       # predicts "never fraud"

    m = classification_metrics(actual, proba)
    assert m["accuracy"] == pytest.approx(0.95)
    assert list(m)[0] == "pr_auc"             # PR-AUC leads
    assert m["recall"] == 0.0                 # and finds nothing


def test_precision_is_none_when_nothing_is_flagged():
    """0/0 is undefined. Reporting 0.0 would say the model is wrong every time
    it flags something, when it never flagged anything."""
    m = classification_metrics([1, 0, 0], [0.1, 0.1, 0.1])
    assert m["precision"] is None
    assert m["recall"] == 0.0


# ─────────────────────── the core finding of this phase ──────────────────────

def _cost_rows():
    """A cost model: excellent on apparel (80% of volume), broken on
    electronics. Mirrors the simulation run during this phase."""
    rows = []
    for i in range(400):
        rows.append({"category": "apparel", "region": "west",
                     "actual": 400.0, "predicted": 405.0})
    for i in range(100):
        rows.append({"category": "electronics", "region": "north",
                     "actual": 2500.0, "predicted": 600.0})
    return rows


def test_a_broken_segment_cannot_hide_behind_a_healthy_aggregate():
    """THE test for this phase.

    Measured on a simulation during this work:
        OVERALL MAE          Rs   395   <- looks acceptable
          apparel   n=4000   Rs    23
          electronics n=1000 Rs 1,882   <- catastrophic

    A merchant selling electronics would get cost estimates wrong by 4x while
    the dashboard showed a healthy MAE.
    """
    report = evaluate_by_segment(
        "cost", _cost_rows(),
        actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )

    electronics = next(
        s for s in report.segments if s.value == "electronics"
    )
    apparel = next(s for s in report.segments if s.value == "apparel")

    assert apparel.metrics["mae"] == pytest.approx(5.0)
    assert electronics.metrics["mae"] == pytest.approx(1900.0)

    # And it is surfaced, not merely computable.
    assert electronics in report.failing_segments
    assert apparel not in report.failing_segments


def test_verdict_states_the_aggregate_is_unrepresentative():
    report = evaluate_by_segment(
        "cost", _cost_rows(),
        actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    assert "does not represent them" in report.as_dict()["verdict"]


def test_failing_segments_are_ordered_worst_first():
    rows = _cost_rows() + [
        {"category": "furniture", "region": "south", "actual": 1000.0, "predicted": 1400.0}
        for _ in range(50)
    ]
    report = evaluate_by_segment(
        "cost", rows, actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    failing = report.failing_segments
    assert failing[0].value == "electronics"      # worst first


def test_a_uniformly_good_model_flags_nothing():
    rows = [
        {"category": c, "actual": 100.0, "predicted": 102.0}
        for c in ("apparel", "electronics") for _ in range(100)
    ]
    report = evaluate_by_segment(
        "cost", rows, actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    assert report.failing_segments == []
    assert "No segment" in report.as_dict()["verdict"]


# ───────────────────────── the segment size floor ────────────────────────────

def test_a_tiny_segment_gets_no_number():
    """Phase 18 measured this directly: at ~60 positives, PR-AUC varied by
    0.165 across seeds alone. A number here would invite a decision it cannot
    support."""
    rows = _cost_rows() + [
        {"category": "rare_item", "actual": 100.0, "predicted": 900.0}
        for _ in range(5)
    ]
    report = evaluate_by_segment(
        "cost", rows, actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )

    rare = next(s for s in report.segments if s.value == "rare_item")
    assert rare.sufficient is False
    assert "mae" not in rare.as_dict()
    assert str(MIN_SEGMENT_ROWS) in rare.as_dict()["note"]


def test_an_insufficient_segment_is_never_flagged_as_failing():
    """It might be the worst segment. We do not know, and saying so is the
    honest position."""
    rows = _cost_rows() + [
        {"category": "rare_item", "actual": 100.0, "predicted": 9000.0}
        for _ in range(5)
    ]
    report = evaluate_by_segment(
        "cost", rows, actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    assert "rare_item" not in {s.value for s in report.failing_segments}


# ──────────────────────────── multi-dimension ────────────────────────────────

def test_multiple_segment_dimensions_are_evaluated():
    """The roadmap lists category, geography, customer segment, price range
    and time period. A model can be fine per-category and broken per-region."""
    report = evaluate_by_segment(
        "cost", _cost_rows(),
        actual_key="actual", predicted_key="predicted",
        segment_by=["category", "region"], primary_metric="mae",
    )
    dimensions = {s.segment for s in report.segments}
    assert dimensions == {"category", "region"}


def test_missing_segment_value_becomes_unknown_not_a_crash():
    rows = [{"actual": 100.0, "predicted": 101.0} for _ in range(50)]
    report = evaluate_by_segment(
        "cost", rows, actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    assert report.segments[0].value == "unknown"


def test_degradation_ratio_is_relative_not_absolute():
    """"3x worse than average" is meaningful across metrics and scales;
    "Rs 500 worse" is not."""
    report = evaluate_by_segment(
        "cost", _cost_rows(),
        actual_key="actual", predicted_key="predicted",
        segment_by=["category"], primary_metric="mae",
    )
    electronics = next(s for s in report.segments if s.value == "electronics")
    assert electronics.degradation is not None
    assert electronics.degradation > DEGRADATION_RATIO
