"""PHASE 15 — the ML data pipeline.

WHAT EXISTS AND WHAT DOES NOT
-----------------------------
The feedback loop is already wired: `PredictionOutcome` records what actually
happened to a return, `/returns/{id}/outcome` writes to it, and
`count_labeled_outcomes()` answers "do we have labels yet". That is the hard
part and it was done well.

What is missing is the bridge — turning those recorded outcomes into a
training dataset. Today the only dataset is
`data/synthetic_returns_dataset.csv`: 5,000 generated rows containing
`approval_probability_true` and `fraud_risk_true`, which are the generator's
own parameters. A model trained against labels derived from those parameters
will score beautifully and know nothing.

THE TWO THINGS THIS MODULE ENFORCES
-----------------------------------
**Temporal splitting.** Returns are time-ordered and the world drifts. A
random split lets the model train on August and test on July, so it learns
patterns it could not have known at prediction time and reports an accuracy it
will never reproduce in production. The split here is always by date: train on
the past, validate on the future.

**A refusal gate.** If there are not enough labelled outcomes, this raises
instead of returning a small dataset. That is the entire point. A pipeline
that cheerfully produces a 40-row training set invites someone to train on it,
publish the metrics, and ship a model whose confidence interval is wider than
its predictions.

WHAT THIS DOES NOT DO
---------------------
It does not train anything. Phases 17–19 do that, and they cannot honestly
start until this module stops raising -- which requires real returns data from
a real merchant, not more code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

__all__ = [
    "DatasetError",
    "InsufficientData",
    "LeakageDetected",
    "DatasetSplit",
    "MINIMUM_LABELLED_ROWS",
    "LEAKY_FEATURES",
    "check_leakage",
    "temporal_split",
    "build_dataset",
]


class DatasetError(Exception):
    """Base class for dataset construction failures."""


class InsufficientData(DatasetError):
    """Not enough labelled outcomes to build a defensible training set."""


class LeakageDetected(DatasetError):
    """A feature carries information unavailable at prediction time."""


# Below this, the honest answer is "we cannot train yet".
#
# 1,000 is not a magic number and is deliberately not presented as one. It is
# roughly where a tree model over ~15 features stops fitting noise, and it is
# small enough that a mid-size merchant reaches it within a few months. It is
# a floor for having a conversation, not a guarantee of a good model -- the
# metrics still have to justify themselves in Phase 19.
MINIMUM_LABELLED_ROWS: Final[int] = 1_000

# Minimum rows in the held-out period. A test set of 30 rows produces an
# accuracy figure whose confidence interval spans most of the possible range,
# which is worse than no figure because it looks like measurement.
MINIMUM_TEST_ROWS: Final[int] = 200

# Fields that only exist *because* the outcome already happened. Including any
# of them means the model is reading the answer off the back of the paper.
#
# This is the failure that produces a suspiciously excellent model and is
# almost never caught by looking at metrics -- the metrics are what look good.
LEAKY_FEATURES: Final[frozenset[str]] = frozenset({
    # Outcome fields
    "actual_cost_minor", "actual_cost_inr",
    "actual_resale_price_minor", "actual_resale_price_inr",
    "actual_fraud_confirmed", "actual_damage_grade",
    "resolution", "refund_issued", "refund_amount",
    # Post-decision state
    "routing_decision", "final_status", "closed_at", "refunded_at",
    "inspection_notes", "inspection_result", "disposition",
    # The synthetic generator's own parameters. Their presence in a dataset
    # means it is generated, not observed.
    "approval_probability_true", "fraud_risk_true",
})


@dataclass(frozen=True)
class DatasetSplit:
    """A temporally-ordered train/validation/test split."""

    train: list[dict[str, Any]]
    validation: list[dict[str, Any]]
    test: list[dict[str, Any]]
    train_period: tuple[str, str]
    validation_period: tuple[str, str]
    test_period: tuple[str, str]
    feature_names: list[str]
    label_name: str

    def summary(self) -> dict[str, Any]:
        return {
            "rows": {
                "train": len(self.train),
                "validation": len(self.validation),
                "test": len(self.test),
            },
            "periods": {
                "train": self.train_period,
                "validation": self.validation_period,
                "test": self.test_period,
            },
            "features": self.feature_names,
            "label": self.label_name,
            "split_strategy": "temporal",
            "note": (
                "Split by date, not randomly. Returns are time-ordered and "
                "the world drifts; a random split lets the model learn from "
                "the future and report an accuracy it cannot reproduce."
            ),
        }


def check_leakage(feature_names: list[str], label_name: str) -> None:
    """Raise if any feature could not have been known at prediction time.

    Runs before every dataset build rather than as an optional lint step.
    Leakage is the single most expensive mistake in an ML pipeline: it
    produces a model that scores brilliantly in evaluation, ships, and then
    performs at chance -- and by then the metrics have been quoted to
    customers.
    """
    leaking = sorted(set(feature_names) & LEAKY_FEATURES)
    if leaking:
        raise LeakageDetected(
            f"These features are only known after the outcome, so a model "
            f"using them is reading the answer: {', '.join(leaking)}. "
            f"Remove them, or move the prediction point later in the "
            f"lifecycle so they genuinely precede it."
        )

    if label_name in feature_names:
        raise LeakageDetected(
            f"The label {label_name!r} is also listed as a feature."
        )

    # A feature named after the label usually is the label, lightly renamed.
    stem = label_name.replace("actual_", "").replace("_confirmed", "")
    suspicious = [
        f for f in feature_names
        if stem and stem in f and f != label_name
    ]
    if suspicious:
        raise LeakageDetected(
            f"These features share a name stem with the label {label_name!r} "
            f"and are probably restatements of it: {', '.join(sorted(suspicious))}. "
            f"If they are genuinely independent, rename them so the "
            f"distinction is visible to the next person."
        )


def _parse_date(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).replace("Z", "").replace(" ", "T", 1)
    return datetime.fromisoformat(text.split("+")[0])


def temporal_split(
    rows: list[dict[str, Any]],
    *,
    date_field: str = "created_at",
    train_fraction: float = 0.7,
    validation_fraction: float = 0.15,
) -> tuple[list, list, list]:
    """Split chronologically: oldest to train, newest to test.

    Splits on position within the sorted order rather than on a calendar date.
    Calendar splitting is more principled in theory and produces wildly uneven
    partitions in practice, because return volume is seasonal -- a festive
    month can hold more returns than the preceding quarter.
    """
    if not rows:
        return [], [], []

    ordered = sorted(rows, key=lambda r: _parse_date(r.get(date_field)))
    n = len(ordered)
    train_end = int(n * train_fraction)
    validation_end = train_end + int(n * validation_fraction)

    return ordered[:train_end], ordered[train_end:validation_end], ordered[validation_end:]


def _period(rows: list[dict[str, Any]], date_field: str) -> tuple[str, str]:
    if not rows:
        return ("", "")
    dates = [_parse_date(r.get(date_field)) for r in rows]
    return (min(dates).date().isoformat(), max(dates).date().isoformat())


def build_dataset(
    rows: list[dict[str, Any]],
    *,
    feature_names: list[str],
    label_name: str,
    date_field: str = "created_at",
) -> DatasetSplit:
    """Build a training dataset, or refuse and explain why.

    The refusal is the feature. Returning a 40-row training set invites
    someone to train on it, publish the metrics, and ship a model whose
    confidence interval is wider than its predictions.
    """
    check_leakage(feature_names, label_name)

    labelled = [r for r in rows if r.get(label_name) is not None]

    if len(labelled) < MINIMUM_LABELLED_ROWS:
        raise InsufficientData(
            f"Only {len(labelled)} labelled outcome(s) for {label_name!r}; "
            f"{MINIMUM_LABELLED_ROWS} is the floor for a defensible model. "
            f"Labels come from confirmed real outcomes via "
            f"/returns/{{id}}/outcome — they accumulate as returns are "
            f"resolved, and cannot be manufactured. Until then, treat the "
            f"rule-based scores as the product and say so."
        )

    train, validation, test = temporal_split(
        labelled, date_field=date_field,
    )

    if len(test) < MINIMUM_TEST_ROWS:
        raise InsufficientData(
            f"The held-out test period has only {len(test)} row(s); "
            f"{MINIMUM_TEST_ROWS} is the minimum for a meaningful metric. "
            f"An accuracy computed on fewer has a confidence interval wide "
            f"enough to be indistinguishable from guessing, which is worse "
            f"than no figure because it looks like measurement."
        )

    # Guard against the sort silently failing on unparseable dates.
    if train and test:
        latest_train = _parse_date(train[-1][date_field])
        earliest_test = _parse_date(test[0][date_field])
        if latest_train > earliest_test:
            raise LeakageDetected(
                "Training rows are dated after test rows. The temporal "
                "ordering failed, so the model would be trained on the "
                "future it is meant to predict."
            )

    return DatasetSplit(
        train=train,
        validation=validation,
        test=test,
        train_period=_period(train, date_field),
        validation_period=_period(validation, date_field),
        test_period=_period(test, date_field),
        feature_names=list(feature_names),
        label_name=label_name,
    )


def readiness_report(
    labelled_counts: dict[str, int],
) -> dict[str, Any]:
    """Can we train yet, per label? Surfaced so the answer is visible rather
    than discovered when someone tries."""
    labels = {
        label: {
            "labelled_rows": count,
            "required": MINIMUM_LABELLED_ROWS,
            "ready": count >= MINIMUM_LABELLED_ROWS,
            "shortfall": max(MINIMUM_LABELLED_ROWS - count, 0),
        }
        for label, count in labelled_counts.items()
    }
    return {
        "labels": labels,
        "any_ready": any(v["ready"] for v in labels.values()),
        "note": (
            "Labels accumulate only as real returns are resolved and their "
            "outcomes confirmed. This number cannot be raised by writing "
            "code."
        ),
    }
