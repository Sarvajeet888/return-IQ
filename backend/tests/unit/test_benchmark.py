"""PHASE 18 — benchmark harness.

The harness is tested with injected `fit_predict` functions rather than real
models, so these verify the *selection logic* — which is the part that has to
be right before any benchmark is trusted.
"""
from __future__ import annotations

import pytest

from app.ml.benchmark import (
    NOISE_THRESHOLD,
    BenchmarkReport,
    CandidateResult,
    benchmark_candidate,
    compare,
    expected_calibration_error,
    select_winner,
)


def _candidate(name, scores, *, metric="pr_auc", infer_ms=1.0, train=0.1, ece=0.05):
    return CandidateResult(
        name=name, primary_metric=metric, scores=scores,
        train_seconds=[train] * len(scores), inference_ms_per_row=infer_ms,
        calibration_error=ece, explainability="medium",
    )


# ─────────────────────────────── calibration ─────────────────────────────────

def test_perfect_calibration_scores_zero():
    """A model saying 0.0 for outcomes that never happen and 1.0 for outcomes
    that always do is perfectly calibrated."""
    probs = [0.0] * 50 + [1.0] * 50
    outcomes = [0] * 50 + [1] * 50
    assert expected_calibration_error(probs, outcomes) == pytest.approx(0.0)


def test_overconfident_model_is_penalised():
    """The failure that matters for ReturnIQ.

    Phase 24 multiplies a probability by a cost to compute expected value. A
    model saying 0.9 when the truth is 0.1 makes the *economics* wrong by 9x,
    not just the score. It can rank perfectly and still be unusable.
    """
    probs = [0.9] * 100
    outcomes = [1] * 10 + [0] * 90       # actually 10%
    assert expected_calibration_error(probs, outcomes) == pytest.approx(0.8)


def test_empty_bins_are_skipped_not_counted_as_error():
    """Counting empty bins would reward a model for never predicting in a
    range, which is the opposite of what calibration measures."""
    probs = [0.05] * 100
    outcomes = [0] * 95 + [1] * 5
    assert expected_calibration_error(probs, outcomes) == pytest.approx(0.0, abs=0.01)


def test_mismatched_lengths_return_zero_rather_than_crash():
    assert expected_calibration_error([0.5], [1, 0]) == 0.0


# ─────────────────────────────── stability ───────────────────────────────────

def test_a_stable_candidate_is_recognised():
    assert _candidate("A", [0.700, 0.702, 0.699]).is_stable is True


def test_an_unstable_candidate_is_flagged():
    """If a model disagrees with itself more than it differs from a rival,
    its headline number is a lucky draw."""
    c = _candidate("A", [0.70, 0.55, 0.68])
    assert c.is_stable is False
    assert c.score_spread == pytest.approx(0.15)


def test_fewer_than_three_seeds_is_refused():
    """Below three seeds the spread is not a spread."""
    with pytest.raises(ValueError, match="minimum"):
        benchmark_candidate(
            "A", lambda seed: ([1.0], [1.0]), primary_metric="mae",
            score_fn=lambda a, p: 0.0, seeds=[1, 2],
            explainability="high", n_test_rows=1,
        )


# ────────────────────────── selection & refusal ──────────────────────────────

def test_a_clear_winner_is_selected():
    report = compare("fraud", [
        _candidate("XGBoost", [0.80, 0.801, 0.799]),
        _candidate("LogReg", [0.60, 0.601, 0.599]),
    ])
    result = select_winner(report)
    assert result["winner"] == "XGBoost"
    assert result["margin"] == pytest.approx(0.2, abs=0.01)


def test_candidates_within_noise_are_declared_tied():
    """THE point of this module.

    Declaring a winner on a 0.003 difference — smaller than seed-to-seed
    variance — is how a team ends up defending an arbitrary choice for two
    years, and how "we benchmarked it" becomes a claim that does not survive
    scrutiny.
    """
    report = compare("fraud", [
        _candidate("XGBoost", [0.800, 0.801, 0.799], infer_ms=12.0),
        _candidate("LightGBM", [0.798, 0.799, 0.797], infer_ms=3.0),
    ])
    result = select_winner(report)
    assert "within" in result["reason"]
    assert result["score_difference"] < NOISE_THRESHOLD
    # Tiebreak is inference cost, not the fractionally higher score.
    assert result["winner"] == "LightGBM"
    assert result["tied_with"] == ["XGBoost"]


def test_an_unstable_leader_wins_nothing():
    """Highest score, but it will not reproduce."""
    report = compare("fraud", [
        _candidate("XGBoost", [0.85, 0.60, 0.79]),
        _candidate("LogReg", [0.50, 0.501, 0.499]),
    ])
    result = select_winner(report)
    assert result["winner"] is None
    assert "lucky draw" in result["reason"]


def test_a_single_candidate_is_not_a_benchmark():
    report = compare("fraud", [_candidate("XGBoost", [0.8, 0.8, 0.8])])
    result = select_winner(report)
    assert result["winner"] == "XGBoost"
    assert "not a benchmark" in result["caveat"]


def test_all_candidates_failing_is_reported_honestly():
    failed = CandidateResult(
        name="CatBoost", primary_metric="pr_auc", scores=[], train_seconds=[],
        inference_ms_per_row=0.0, calibration_error=None,
        explainability="medium", failed="ImportError: no module named catboost",
    )
    result = select_winner(compare("fraud", [failed]))
    assert result["winner"] is None
    assert "Every candidate failed" in result["reason"]


def test_a_failed_candidate_does_not_crash_the_benchmark():
    """"LightGBM would not build on this platform" is a legitimate benchmark
    result — arguably more useful than a score, because it is a deployment
    constraint."""
    def explodes(seed):
        raise ImportError("no module named lightgbm")

    result = benchmark_candidate(
        "LightGBM", explodes, primary_metric="pr_auc",
        score_fn=lambda a, p: 0.0, seeds=[1, 2, 3],
        explainability="medium", n_test_rows=100,
    )
    assert result.failed is not None
    assert "lightgbm" in result.failed


# ────────────────────────────── ranking ──────────────────────────────────────

def test_error_metrics_rank_lower_as_better():
    report = compare("cost", [
        _candidate("A", [180.0, 181.0, 179.0], metric="mae"),
        _candidate("B", [120.0, 121.0, 119.0], metric="mae"),
    ])
    assert report.ranked()[0].name == "B"


def test_score_metrics_rank_higher_as_better():
    report = compare("fraud", [
        _candidate("A", [0.60, 0.60, 0.60]),
        _candidate("B", [0.80, 0.80, 0.80]),
    ])
    assert report.ranked()[0].name == "B"


def test_failed_candidates_are_excluded_from_ranking():
    failed = CandidateResult(
        name="Broken", primary_metric="pr_auc", scores=[], train_seconds=[],
        inference_ms_per_row=0.0, calibration_error=None,
        explainability="low", failed="boom",
    )
    report = compare("fraud", [failed, _candidate("Good", [0.7, 0.7, 0.7])])
    assert [c.name for c in report.ranked()] == ["Good"]


# ───────────────── the empirical finding this phase produced ─────────────────

def test_rare_events_need_more_rows_because_the_metric_is_unstable():
    """Measured during this phase, and the reason Phase 17 sets fraud's floor
    at 5,000 rather than 1,000.

    Identical model and data, only the split seed varying:

        6% base rate  (~60 positives in test):  spread 0.165
        35% base rate (~350 positives):         spread 0.009

    Fewer positives means each one moves the metric more. This is the
    statistical reality of rare-event evaluation, not a bug — and it is why a
    fraud model reporting "PR-AUC 0.75" on a small test set is reporting a
    coin flip.
    """
    from app.ml.model_family import MODEL_FAMILY

    assert MODEL_FAMILY["fraud"].min_labelled_rows >= 5_000
    assert MODEL_FAMILY["customer_risk"].min_labelled_rows >= 5_000

    # And the harness would refuse to crown a leader with that spread.
    unstable = _candidate("XGBoost", [0.747, 0.637, 0.584])
    assert unstable.is_stable is False
    assert select_winner(compare("fraud", [
        unstable, _candidate("LogReg", [0.16, 0.161, 0.159]),
    ]))["winner"] is None
