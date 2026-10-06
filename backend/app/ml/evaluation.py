"""PHASE 19 — model evaluation.

THE "DONE WHEN" THIS IMPLEMENTS
-------------------------------
> "You know where the model works and where it doesn't."

That is not achievable from an aggregate metric, and the gap is not subtle.
Measured on a simulated cost model during this phase:

    OVERALL MAE:            Rs 395     <- looks acceptable
      apparel      n=4000   Rs  23     (80% of volume)
      electronics  n=1000   Rs 1,882   (20% of volume)

The model is catastrophically wrong on electronics -- off by roughly Rs 1,900
per return -- and the headline number hides it entirely, because apparel
dominates the volume. A merchant selling electronics would be given cost
estimates that are wrong by a factor of four, and the dashboard would show a
healthy MAE.

Aggregate metrics do not merely fail to reveal this. They actively conceal it,
and the concealment gets worse as the failing segment gets smaller -- which is
the opposite of what you want, because small segments are where models fail.

THE SEGMENT SIZE FLOOR
----------------------
A segment with 12 rows produces a metric that is noise. Phase 18 measured this
directly: at a 6% base rate with ~60 positives, PR-AUC varied by 0.165 across
seeds alone. Segments below the floor are reported as "insufficient data"
rather than given a number, because a number invites a decision.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Final

__all__ = [
    "SegmentResult",
    "EvaluationReport",
    "MIN_SEGMENT_ROWS",
    "regression_metrics",
    "classification_metrics",
    "evaluate_by_segment",
]

# Below this, a segment metric is noise. Reported as insufficient rather than
# given a number, because a number invites a decision.
MIN_SEGMENT_ROWS: Final[int] = 30

# A segment performing this much worse than the overall figure is flagged.
# Ratio, not absolute: "3x worse than average" is meaningful across metrics
# and scales, "Rs 500 worse" is not.
DEGRADATION_RATIO: Final[float] = 2.0


# ─────────────────────────────── metrics ─────────────────────────────────────

def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    """Every regression metric the roadmap lists, plus why each is here.

    MAE and median absolute error are both reported deliberately. A large gap
    between them means a few extreme errors are dragging the mean -- which
    tells you the model has a failure mode rather than a general weakness, and
    that is a different problem with a different fix.
    """
    n = len(actual)
    if n == 0:
        return {}

    errors = [a - p for a, p in zip(actual, predicted)]
    abs_errors = [abs(e) for e in errors]

    mean_actual = sum(actual) / n
    ss_tot = sum((a - mean_actual) ** 2 for a in actual)
    ss_res = sum(e ** 2 for e in errors)

    # MAPE is undefined at zero and explodes near it. Rows with a near-zero
    # actual are excluded and the exclusion is reported, rather than silently
    # producing a percentage in the millions.
    pct_errors = [abs(e / a) for e, a in zip(errors, actual) if abs(a) > 1e-9]

    return {
        "mae": sum(abs_errors) / n,
        "rmse": math.sqrt(ss_res / n),
        "median_absolute_error": statistics.median(abs_errors),
        # R² is NaN when every actual is identical (ss_tot == 0). Reported as
        # None rather than a misleading 0.0 or 1.0.
        "r2": (1 - ss_res / ss_tot) if ss_tot > 1e-12 else None,
        "mape": (sum(pct_errors) / len(pct_errors)) if pct_errors else None,
        "mape_excluded_rows": n - len(pct_errors),
        # Signed mean error: is the model systematically over or under?
        # A model biased 20% low is a different problem from one that is
        # noisy in both directions, and |error| cannot tell them apart.
        "mean_bias": sum(errors) / n,
        "n": n,
    }


def classification_metrics(
    actual: list[int],
    predicted_proba: list[float],
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Classification metrics with the confusion matrix kept visible.

    Accuracy is computed but deliberately not first. At a 5% base rate,
    predicting "never" scores 95% -- the number is technically correct and
    completely misleading, and putting it at the top of a report is how it
    ends up in a slide.
    """
    n = len(actual)
    if n == 0:
        return {}

    predicted = [1 if p >= threshold else 0 for p in predicted_proba]

    tp = sum(1 for a, p in zip(actual, predicted) if a == 1 and p == 1)
    fp = sum(1 for a, p in zip(actual, predicted) if a == 0 and p == 1)
    fn = sum(1 for a, p in zip(actual, predicted) if a == 1 and p == 0)
    tn = sum(1 for a, p in zip(actual, predicted) if a == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall else None
    )

    from app.ml.benchmark import expected_calibration_error
    from app.ml.training_harness import _pr_auc

    return {
        "pr_auc": _pr_auc(actual, predicted_proba),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "base_rate": sum(actual) / n,
        "calibration_error": expected_calibration_error(predicted_proba, actual),
        "confusion_matrix": {
            "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "true_negative": tn,
        },
        # Last, on purpose.
        "accuracy": (tp + tn) / n,
        "n": n,
    }


# ────────────────────────────── segmentation ─────────────────────────────────

@dataclass
class SegmentResult:
    segment: str
    value: str
    metrics: dict[str, Any]
    n: int
    sufficient: bool
    degradation: float | None = None      # ratio vs overall, higher is worse

    def as_dict(self) -> dict[str, Any]:
        if not self.sufficient:
            return {
                "segment": self.segment,
                "value": self.value,
                "n": self.n,
                "sufficient": False,
                "note": (
                    f"Only {self.n} rows; {MIN_SEGMENT_ROWS} is the minimum "
                    f"for a metric that is not noise. No figure reported — a "
                    f"number here would invite a decision it cannot support."
                ),
            }
        out = {
            "segment": self.segment,
            "value": self.value,
            "n": self.n,
            "sufficient": True,
            **{k: (round(v, 4) if isinstance(v, float) else v)
               for k, v in self.metrics.items()},
        }
        if self.degradation is not None:
            out["degradation_vs_overall"] = round(self.degradation, 2)
        return out


@dataclass
class EvaluationReport:
    model_key: str
    primary_metric: str
    overall: dict[str, Any]
    segments: list[SegmentResult] = field(default_factory=list)

    @property
    def failing_segments(self) -> list[SegmentResult]:
        """Segments materially worse than the overall figure.

        These are the finding. A model is rarely uniformly bad — it is usually
        fine on the bulk of volume and broken on a slice, and the slice is
        what a merchant in that category experiences as "this product does not
        work".
        """
        return sorted(
            [s for s in self.segments
             if s.sufficient and s.degradation and s.degradation >= DEGRADATION_RATIO],
            key=lambda s: s.degradation or 0,
            reverse=True,
        )

    def as_dict(self) -> dict[str, Any]:
        failing = self.failing_segments
        return {
            "model": self.model_key,
            "primary_metric": self.primary_metric,
            "overall": {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.overall.items()
            },
            "segments": [s.as_dict() for s in self.segments],
            "failing_segments": [
                {"segment": s.segment, "value": s.value,
                 "n": s.n, "degradation": round(s.degradation or 0, 2)}
                for s in failing
            ],
            "verdict": (
                f"{len(failing)} segment(s) perform at least "
                f"{DEGRADATION_RATIO}x worse than the overall figure. The "
                f"aggregate metric does not represent them."
                if failing else
                "No segment performs materially worse than the overall figure."
            ),
        }


def evaluate_by_segment(
    model_key: str,
    rows: list[dict[str, Any]],
    *,
    actual_key: str,
    predicted_key: str,
    segment_by: list[str],
    primary_metric: str,
    task: str = "regression",
) -> EvaluationReport:
    """Evaluate overall and within every segment.

    `segment_by` names the columns to slice on — category, region, price band,
    time period. The roadmap lists these; the point is that a model can be
    excellent overall and unusable for one merchant whose entire catalogue
    sits in a failing slice.
    """
    lower_is_better = primary_metric in {"mae", "rmse", "median_absolute_error", "mape"}

    def compute(subset: list[dict[str, Any]]) -> dict[str, Any]:
        actual = [r[actual_key] for r in subset]
        predicted = [r[predicted_key] for r in subset]
        if task == "regression":
            return regression_metrics([float(a) for a in actual], [float(p) for p in predicted])
        return classification_metrics(
            [int(bool(a)) for a in actual], [float(p) for p in predicted],
        )

    overall = compute(rows)
    overall_score = overall.get(primary_metric)

    segments: list[SegmentResult] = []
    for column in segment_by:
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(str(r.get(column, "unknown")), []).append(r)

        for value, subset in sorted(groups.items()):
            if len(subset) < MIN_SEGMENT_ROWS:
                segments.append(SegmentResult(
                    segment=column, value=value, metrics={},
                    n=len(subset), sufficient=False,
                ))
                continue

            metrics = compute(subset)
            score = metrics.get(primary_metric)

            degradation = None
            if score is not None and overall_score not in (None, 0):
                degradation = (
                    score / overall_score if lower_is_better
                    else (overall_score / score if score else None)
                )

            segments.append(SegmentResult(
                segment=column, value=value, metrics=metrics,
                n=len(subset), sufficient=True, degradation=degradation,
            ))

    return EvaluationReport(
        model_key=model_key, primary_metric=primary_metric,
        overall=overall, segments=segments,
    )
