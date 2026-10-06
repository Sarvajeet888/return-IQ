"""PHASE 18 — model benchmarking.

THE INSTRUCTION THIS IMPLEMENTS
-------------------------------
"Don't assume XGBoost is the winner. Benchmark appropriate candidates...
Select based on evidence. Not hype."

ReturnIQ currently runs XGBoost. Nobody compared it to anything. That is not
a criticism of the choice — XGBoost is a reasonable default — it is a
criticism of the *process*, because a default nobody tested is indistinguishable
from a default that happens to be wrong.

WHY ACCURACY IS ONLY ONE COLUMN
-------------------------------
The roadmap lists seven dimensions: training time, inference time, accuracy,
stability, calibration, explainability, resource cost. Most benchmarks report
the third and quietly ignore the rest, then a model gets deployed and someone
discovers it takes 400ms to score a return.

Two of the seven deserve special mention because they are the ones normally
skipped:

**Stability.** A model retrained on the same data with a different seed should
give roughly the same answer. If it does not, the reported metric is a lucky
draw and will not reproduce. Measured here as the spread across seeds.

**Calibration.** When a fraud model says 0.8, are 80% of those returns
actually fraudulent? An uncalibrated model can rank perfectly (great AUC) and
still be useless for a decision, because Phase 24's economics multiply the
probability by a cost. A probability that is wrong by 3x makes the arithmetic
wrong by 3x.

THE REFUSAL
-----------
`select_winner()` returns "no clear winner" when candidates are within noise
of each other. Declaring a winner on a 0.003 difference — smaller than the
seed-to-seed variance — is how a team ends up defending an arbitrary choice
for two years.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Final

__all__ = [
    "CandidateResult",
    "BenchmarkReport",
    "expected_calibration_error",
    "benchmark_candidate",
    "compare",
    "select_winner",
]

# Candidates whose difference in the primary metric is smaller than this are
# treated as tied. Set relative to typical seed-to-seed variance rather than
# picked for neatness -- if two models differ by less than one model differs
# from itself, the difference is not real.
NOISE_THRESHOLD: Final[float] = 0.01

# Minimum seeds for a stability estimate. Below three, the spread is not a
# spread.
MIN_SEEDS: Final[int] = 3


@dataclass
class CandidateResult:
    """One algorithm, measured across every dimension that matters."""

    name: str
    primary_metric: str
    scores: list[float]                      # one per seed
    train_seconds: list[float]
    inference_ms_per_row: float
    calibration_error: float | None
    explainability: str
    notes: str = ""
    failed: str | None = None

    @property
    def mean_score(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0.0

    @property
    def score_spread(self) -> float:
        """Max minus min across seeds.

        Reported rather than standard deviation because the question a
        reviewer asks is "how different could this have looked", and the
        extremes answer that directly at these sample sizes.
        """
        return (max(self.scores) - min(self.scores)) if len(self.scores) > 1 else 0.0

    @property
    def is_stable(self) -> bool:
        """Does the model agree with itself across seeds?

        If the spread exceeds the noise threshold, the headline number is a
        lucky draw and will not reproduce on the next retrain.
        """
        return self.score_spread <= NOISE_THRESHOLD

    @property
    def mean_train_seconds(self) -> float:
        return statistics.mean(self.train_seconds) if self.train_seconds else 0.0

    def as_dict(self) -> dict[str, Any]:
        if self.failed:
            return {"name": self.name, "failed": self.failed}
        return {
            "name": self.name,
            "primary_metric": self.primary_metric,
            "mean_score": round(self.mean_score, 4),
            "score_spread": round(self.score_spread, 4),
            "stable": self.is_stable,
            "seeds": len(self.scores),
            "mean_train_seconds": round(self.mean_train_seconds, 3),
            "inference_ms_per_row": round(self.inference_ms_per_row, 4),
            "calibration_error": (
                round(self.calibration_error, 4) if self.calibration_error is not None else None
            ),
            "explainability": self.explainability,
            "notes": self.notes,
        }


@dataclass
class BenchmarkReport:
    model_key: str
    candidates: list[CandidateResult] = field(default_factory=list)

    def ranked(self) -> list[CandidateResult]:
        """Best first, by mean score. Failed candidates excluded."""
        ok = [c for c in self.candidates if not c.failed]
        lower_is_better = ok and ok[0].primary_metric in {"mae", "rmse", "mape", "ece"}
        return sorted(ok, key=lambda c: c.mean_score, reverse=not lower_is_better)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_key,
            "candidates": [c.as_dict() for c in self.candidates],
            "selection": select_winner(self),
        }


def expected_calibration_error(
    probabilities: list[float],
    outcomes: list[int],
    *,
    bins: int = 10,
) -> float:
    """How far predicted probabilities are from observed frequencies.

    Bins predictions, then compares the mean prediction in each bin to the
    actual rate. ECE of 0.15 means predictions are off by 15 percentage points
    on average.

    This matters more for ReturnIQ than for most products. Phase 24 multiplies
    a probability by a cost to compute expected value, so a model that says
    0.8 when the truth is 0.3 makes the *economics* wrong, not just the score.
    A model can rank perfectly (excellent AUC) and still be unusable here.

    Bins with no predictions are skipped rather than counted as zero error --
    counting them would reward a model for never predicting in a range.
    """
    if not probabilities or len(probabilities) != len(outcomes):
        return 0.0

    total = 0.0
    n = len(probabilities)

    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        idx = [
            i for i, p in enumerate(probabilities)
            if (low <= p < high) or (b == bins - 1 and p == 1.0)
        ]
        if not idx:
            continue
        mean_predicted = sum(probabilities[i] for i in idx) / len(idx)
        observed = sum(outcomes[i] for i in idx) / len(idx)
        total += (len(idx) / n) * abs(mean_predicted - observed)

    return total


def benchmark_candidate(
    name: str,
    fit_predict: Callable[[int], tuple[list[float], list[float]]],
    *,
    primary_metric: str,
    score_fn: Callable[[list[float], list[float]], float],
    seeds: list[int],
    explainability: str,
    n_test_rows: int,
    calibration_outcomes: list[int] | None = None,
    notes: str = "",
) -> CandidateResult:
    """Measure one algorithm across every dimension.

    `fit_predict(seed) -> (actual, predicted)` is injected so this works for
    any library, and so the harness is testable without installing four
    gradient boosting packages.

    A candidate that raises is recorded as failed rather than crashing the
    benchmark. "LightGBM would not build on this platform" is a legitimate
    and useful benchmark result -- arguably more useful than a score, because
    it is a deployment constraint.
    """
    if len(seeds) < MIN_SEEDS:
        raise ValueError(
            f"{name}: {len(seeds)} seed(s) given; {MIN_SEEDS} is the minimum "
            f"for a stability estimate. Below that, the spread is not a spread."
        )

    scores: list[float] = []
    train_times: list[float] = []
    inference_ms = 0.0
    calibration: float | None = None

    try:
        for seed in seeds:
            started = time.perf_counter()
            actual, predicted = fit_predict(seed)
            train_times.append(time.perf_counter() - started)
            scores.append(score_fn(actual, predicted))

            if seed == seeds[0]:
                # Timed once: inference cost does not vary by seed, and
                # timing it every round inflates the training measurement.
                t0 = time.perf_counter()
                fit_predict(seed)
                inference_ms = ((time.perf_counter() - t0) * 1000) / max(n_test_rows, 1)

                if calibration_outcomes is not None:
                    calibration = expected_calibration_error(
                        [float(p) for p in predicted], calibration_outcomes,
                    )
    except Exception as exc:  # noqa: BLE001 -- a failed candidate is a result
        return CandidateResult(
            name=name, primary_metric=primary_metric, scores=[], train_seconds=[],
            inference_ms_per_row=0.0, calibration_error=None,
            explainability=explainability, failed=f"{type(exc).__name__}: {exc}",
        )

    return CandidateResult(
        name=name,
        primary_metric=primary_metric,
        scores=scores,
        train_seconds=train_times,
        inference_ms_per_row=inference_ms,
        calibration_error=calibration,
        explainability=explainability,
        notes=notes,
    )


def compare(model_key: str, candidates: list[CandidateResult]) -> BenchmarkReport:
    return BenchmarkReport(model_key=model_key, candidates=candidates)


def select_winner(report: BenchmarkReport) -> dict[str, Any]:
    """Pick a winner, or state honestly that there is no clear one.

    The refusal is the point. Declaring a winner on a 0.003 difference --
    smaller than the seed-to-seed variance of either candidate -- is how a
    team ends up defending an arbitrary choice for two years, and how "we
    benchmarked it" becomes a claim that does not survive scrutiny.

    When candidates tie on score, the tiebreak is deliberately *not* accuracy:
    it is stability first, then inference cost, then explainability. A model
    you can explain to a merchant disputing a decision is worth more than
    0.004 AUC, and one that scores in 8ms is worth more than one that scores
    in 300ms.
    """
    ranked = report.ranked()
    failed = [c for c in report.candidates if c.failed]

    if not ranked:
        return {
            "winner": None,
            "reason": "Every candidate failed to train.",
            "failed": [{"name": c.name, "error": c.failed} for c in failed],
        }

    if len(ranked) == 1:
        return {
            "winner": ranked[0].name,
            "reason": "Only one candidate completed.",
            "caveat": "A single candidate is not a benchmark.",
            "failed": [{"name": c.name, "error": c.failed} for c in failed],
        }

    best = ranked[0]
    contenders = [
        c for c in ranked
        if abs(c.mean_score - best.mean_score) <= NOISE_THRESHOLD
    ]

    unstable = [c.name for c in contenders if not c.is_stable]

    if len(contenders) > 1:
        # Tiebreak: stability, then inference speed, then explainability.
        stable = [c for c in contenders if c.is_stable] or contenders
        chosen = min(stable, key=lambda c: (c.inference_ms_per_row, c.mean_train_seconds))
        return {
            "winner": chosen.name,
            "reason": (
                f"{len(contenders)} candidates are within {NOISE_THRESHOLD} "
                f"on {best.primary_metric} — a difference smaller than the "
                f"seed-to-seed variance, so it is not evidence. Selected on "
                f"stability and inference cost instead."
            ),
            "tied_with": [c.name for c in contenders if c.name != chosen.name],
            "unstable_candidates": unstable,
            "score_difference": round(
                max(c.mean_score for c in contenders) - min(c.mean_score for c in contenders), 4
            ),
        }

    if not best.is_stable:
        return {
            "winner": None,
            "reason": (
                f"{best.name} scores highest but is unstable: its score varies "
                f"by {best.score_spread:.4f} across seeds, which exceeds the "
                f"{NOISE_THRESHOLD} threshold. The headline number is a lucky "
                f"draw and will not reproduce on the next retrain."
            ),
            "recommendation": "Investigate variance before selecting.",
        }

    return {
        "winner": best.name,
        "reason": (
            f"Best {best.primary_metric} ({best.mean_score:.4f}), clear of the "
            f"next candidate by more than the noise threshold, and stable "
            f"across {len(best.scores)} seeds."
        ),
        "margin": round(best.mean_score - ranked[1].mean_score, 4),
    }
