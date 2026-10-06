"""PHASE 17 — the training harness.

WHAT THIS IS
------------
One function that trains any model in the family from its spec. Adding
Model J is a spec entry, not a new script.

WHY THE GATES LIVE HERE
-----------------------
Every guard is read from the spec, not accepted as an argument. A caller
cannot pass `min_rows=50` to get a model out, because there is no such
parameter. That is the difference between a guard rail and a comment asking
people to be careful.

METRIC SELECTION IS NOT A DETAIL
--------------------------------
Each spec names its own primary metric, and for the rare-event models it is
PR-AUC rather than accuracy or ROC-AUC. At a 5% fraud base rate, predicting
"never fraud" scores 95% accuracy. Reporting that number would be technically
true and completely misleading — which is the exact failure this project has
spent sixteen phases removing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.ml.model_family import ModelSpec, TaskType, get_spec
from app.services.dataset_builder import (
    DatasetSplit,
    InsufficientData,
    LeakageDetected,
    build_dataset,
    check_leakage,
)

__all__ = ["TrainingResult", "TrainingRefused", "prepare_training", "evaluate"]


class TrainingRefused(Exception):
    """Training did not proceed, with a reason a human can act on."""


@dataclass(frozen=True)
class TrainingResult:
    model_key: str
    metrics: dict[str, float]
    split: DatasetSplit
    n_features: int
    baseline_metrics: dict[str, float]

    def beats_baseline(self) -> bool:
        """Is this model better than the trivial alternative?

        A model that does not beat "always predict the majority class" or
        "always predict the mean" is not a model. Shipping one because the
        roadmap lists it is worse than shipping nothing, because it lends
        false authority to a coin flip.
        """
        primary = next(iter(self.metrics))
        # Lower is better for error metrics, higher for the rest.
        if primary in {"mae", "rmse", "mape"}:
            return self.metrics[primary] < self.baseline_metrics.get(primary, float("inf"))
        return self.metrics[primary] > self.baseline_metrics.get(primary, 0.0)


def prepare_training(
    spec_key: str,
    rows: list[dict[str, Any]],
    *,
    date_field: str = "created_at",
) -> DatasetSplit:
    """Validate and split data for one model, or refuse with a reason.

    Runs every gate before any model is fitted:
      1. spec-specific forbidden features
      2. global leakage check (Phase 15)
      3. this model's row floor
      4. temporal split with a held-out test period
    """
    spec: ModelSpec = get_spec(spec_key)

    forbidden_present = sorted(set(spec.features) & set(spec.forbidden_features))
    if forbidden_present:
        raise TrainingRefused(
            f"{spec.name}: {forbidden_present} are forbidden for this model "
            f"specifically. {spec.known_difficulty}"
        )

    try:
        check_leakage(spec.features, spec.target)
    except LeakageDetected as exc:
        raise TrainingRefused(f"{spec.name}: {exc}") from exc

    labelled = [r for r in rows if r.get(spec.target) is not None]
    if len(labelled) < spec.min_labelled_rows:
        raise TrainingRefused(
            f"{spec.name} needs {spec.min_labelled_rows:,} labelled rows for "
            f"{spec.target!r}; {len(labelled):,} available. "
            f"{spec.known_difficulty or ''} "
            f"Labels come from confirmed outcomes and cannot be manufactured."
        )

    try:
        return build_dataset(
            labelled,
            feature_names=spec.features,
            label_name=spec.target,
            date_field=date_field,
        )
    except (InsufficientData, LeakageDetected) as exc:
        raise TrainingRefused(f"{spec.name}: {exc}") from exc


# ─────────────────────────────── metrics ─────────────────────────────────────

def _mae(actual: list[float], predicted: list[float]) -> float:
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def _rmse(actual: list[float], predicted: list[float]) -> float:
    return (sum((a - p) ** 2 for a, p in zip(actual, predicted)) / len(actual)) ** 0.5


def _pr_auc(actual: list[int], scores: list[float]) -> float:
    """Average precision, computed tie-aware.

    PR-AUC, not ROC-AUC, for rare events. ROC-AUC is dominated by true
    negatives, of which a 5%-base-rate problem has an overwhelming number, so
    it flatters a model that never finds anything. Precision-recall ignores
    true negatives entirely and answers the question a merchant actually has:
    when this flags a return, how often is it right?

    TIES MATTER, and a naive implementation gets this wrong. Sorting by score
    alone makes the result depend on input order: with a constant-scoring
    classifier, if the one positive happens to sort first the metric reports
    1.0 -- a useless model scoring perfectly. Measured on the first version of
    this function: identical data returned 1.0, 0.125, 0.143 and 0.100
    depending only on row order.

    Tied scores are therefore collapsed into groups and precision is computed
    at each group boundary, which is order-independent. A constant classifier
    then correctly scores the base rate.
    """
    if not actual or len(actual) != len(scores):
        return 0.0

    positives = sum(actual)
    if positives == 0:
        return 0.0

    paired = sorted(zip(scores, actual), key=lambda x: -x[0])

    total = 0.0
    tp = 0
    seen = 0
    i = 0
    while i < len(paired):
        j = i
        while j < len(paired) and paired[j][0] == paired[i][0]:
            j += 1

        group_positives = sum(label for _s, label in paired[i:j])
        tp += group_positives
        seen = j

        if group_positives:
            # Precision at the end of the tie group, weighted by how many
            # positives it contributed. Every ordering inside the group is
            # equally plausible, so the boundary value is the fair summary.
            total += (tp / seen) * group_positives

        i = j

    return total / positives


def _baseline_regression(train_y: list[float], test_y: list[float]) -> dict[str, float]:
    """Always predict the training mean."""
    mean = sum(train_y) / len(train_y) if train_y else 0.0
    predicted = [mean] * len(test_y)
    return {"mae": _mae(test_y, predicted), "rmse": _rmse(test_y, predicted)}


def _baseline_classification(train_y: list[int], test_y: list[int]) -> dict[str, float]:
    """Always predict the base rate.

    Its PR-AUC equals the positive-class prevalence -- the number any real
    model must beat to have earned its place.
    """
    rate = sum(train_y) / len(train_y) if train_y else 0.0
    return {"pr_auc": sum(test_y) / len(test_y) if test_y else 0.0, "base_rate": rate}


def evaluate(
    spec_key: str,
    split: DatasetSplit,
    predict: Callable[[list[dict[str, Any]]], list[float]],
) -> TrainingResult:
    """Score a fitted model on the held-out test period, against a baseline.

    `predict` is injected rather than the harness owning the model, so this is
    testable without training anything and works for any library.

    The baseline is not optional. A metric without one is unreadable: MAE of
    ₹180 means nothing until you know that always-guess-the-mean scores ₹175.
    """
    spec = get_spec(spec_key)
    actual = [r[spec.target] for r in split.test]
    predicted = predict(split.test)

    if len(predicted) != len(actual):
        raise ValueError(
            f"predict() returned {len(predicted)} values for {len(actual)} rows"
        )

    train_y = [r[spec.target] for r in split.train]

    if spec.task == TaskType.REGRESSION:
        metrics = {
            "mae": _mae([float(a) for a in actual], [float(p) for p in predicted]),
            "rmse": _rmse([float(a) for a in actual], [float(p) for p in predicted]),
        }
        baseline = _baseline_regression([float(y) for y in train_y], [float(a) for a in actual])
    else:
        binary = [int(bool(a)) for a in actual]
        metrics = {
            "pr_auc": _pr_auc(binary, [float(p) for p in predicted]),
            "base_rate": sum(binary) / len(binary) if binary else 0.0,
        }
        baseline = _baseline_classification([int(bool(y)) for y in train_y], binary)

    # Primary metric first, so `next(iter(metrics))` in beats_baseline() picks
    # the one the spec nominated rather than whichever happens to be first.
    ordered = {spec.primary_metric: metrics[spec.primary_metric]}
    ordered.update({k: v for k, v in metrics.items() if k != spec.primary_metric})

    return TrainingResult(
        model_key=spec.key,
        metrics=ordered,
        split=split,
        n_features=len(spec.features),
        baseline_metrics=baseline,
    )
