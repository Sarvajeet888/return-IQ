"""PHASE 15 — ML data pipeline.

Two properties matter here, and both are about refusing to produce something
misleading: no leakage, and no dataset when there is not enough real data.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services import dataset_builder as db
from app.services.dataset_builder import (
    InsufficientData,
    LeakageDetected,
    MINIMUM_LABELLED_ROWS,
)

FEATURES = [
    "product_value", "actual_weight", "distance_km", "courier",
    "category", "payment_mode", "return_reason", "customer_return_rate",
]
LABEL = "actual_fraud_confirmed"


def _rows(n: int, *, labelled: bool = True, start_days_ago: int = 400):
    base = datetime.now(UTC) - timedelta(days=start_days_ago)
    return [
        {
            "id": f"r{i}",
            "created_at": (base + timedelta(hours=i * 6)).isoformat(),
            "product_value": 1000 + i,
            "actual_weight": 0.5,
            "distance_km": 300,
            "courier": "Delhivery",
            "category": "apparel",
            "payment_mode": "COD",
            "return_reason": "damaged",
            "customer_return_rate": 0.2,
            LABEL: (i % 5 == 0) if labelled else None,
        }
        for i in range(n)
    ]


# ─────────────────────────────── leakage ─────────────────────────────────────

def test_outcome_fields_are_rejected_as_features():
    """The expensive mistake.

    A model given `actual_cost_minor` scores brilliantly in evaluation, ships,
    and performs at chance — and by then the metrics have been quoted to
    customers.
    """
    with pytest.raises(LeakageDetected, match="reading the answer"):
        db.check_leakage(FEATURES + ["actual_cost_minor"], LABEL)


def test_post_decision_state_is_rejected():
    """`routing_decision` is the system's own output. Training on it teaches
    the model to predict what it already decided."""
    with pytest.raises(LeakageDetected):
        db.check_leakage(FEATURES + ["routing_decision"], LABEL)


def test_the_synthetic_generators_own_parameters_are_rejected():
    """`fraud_risk_true` and `approval_probability_true` are in
    data/synthetic_returns_dataset.csv. Their presence in a dataset is
    itself the evidence that it was generated rather than observed.
    """
    with pytest.raises(LeakageDetected):
        db.check_leakage(FEATURES + ["fraud_risk_true"], LABEL)


def test_the_label_cannot_also_be_a_feature():
    # Caught by the LEAKY_FEATURES check first, since actual_fraud_confirmed
    # is itself an outcome field — two guards covering the same mistake, which
    # is fine. My first version asserted the message from the *second* guard.
    with pytest.raises(LeakageDetected):
        db.check_leakage(FEATURES + [LABEL], LABEL)

    # A label outside LEAKY_FEATURES exercises the dedicated check.
    with pytest.raises(LeakageDetected, match="also listed as a feature"):
        db.check_leakage(["a", "b", "net_recovery"], "net_recovery")


def test_a_renamed_label_is_caught():
    """A feature named after the label usually is the label, lightly renamed —
    the kind of thing that survives review because it looks like a different
    column."""
    with pytest.raises(LeakageDetected, match="name stem"):
        db.check_leakage(FEATURES + ["fraud_score_final"], "actual_fraud_confirmed")


def test_clean_features_pass():
    db.check_leakage(FEATURES, LABEL)      # must not raise


# ──────────────────────────── temporal ordering ──────────────────────────────

def test_split_is_chronological_not_random():
    """A random split lets the model train on August and test on July, so it
    learns patterns unavailable at prediction time."""
    # Shuffled input. My first version passed already-sorted rows, so it
    # survived a sabotage that removed the sort entirely — the data happened
    # to arrive in order. Confirmed by sabotage; fixed here.
    import random

    rows = _rows(1000)
    random.Random(42).shuffle(rows)
    train, validation, test = db.temporal_split(rows)

    latest_train = max(db._parse_date(r["created_at"]) for r in train)
    earliest_val = min(db._parse_date(r["created_at"]) for r in validation)
    latest_val = max(db._parse_date(r["created_at"]) for r in validation)
    earliest_test = min(db._parse_date(r["created_at"]) for r in test)

    assert latest_train <= earliest_val
    assert latest_val <= earliest_test


def test_split_proportions_are_roughly_as_requested():
    train, validation, test = db.temporal_split(_rows(1000))
    assert len(train) == 700
    assert len(validation) == 150
    assert len(test) == 150


def test_split_handles_unsorted_input():
    rows = _rows(1000)
    rows.reverse()
    train, _, test = db.temporal_split(rows)
    assert db._parse_date(train[-1]["created_at"]) <= db._parse_date(test[0]["created_at"])


def test_empty_input_splits_to_empty():
    assert db.temporal_split([]) == ([], [], [])


# ─────────────────────────── the refusal gate ────────────────────────────────

def test_refuses_to_build_from_too_few_labels():
    """THE point of this module.

    Returning a 40-row training set invites someone to train on it, publish
    the metrics, and ship a model whose confidence interval is wider than its
    predictions.
    """
    with pytest.raises(InsufficientData, match="floor for a defensible model"):
        db.build_dataset(_rows(40), feature_names=FEATURES, label_name=LABEL)


def test_refusal_explains_that_labels_cannot_be_manufactured():
    with pytest.raises(InsufficientData) as exc:
        db.build_dataset(_rows(40), feature_names=FEATURES, label_name=LABEL)
    assert "cannot be manufactured" in str(exc.value)


def test_unlabelled_rows_do_not_count_toward_the_threshold():
    """5,000 rows with no confirmed outcomes is still zero labels."""
    rows = _rows(5000, labelled=False)
    with pytest.raises(InsufficientData):
        db.build_dataset(rows, feature_names=FEATURES, label_name=LABEL)


def test_refuses_when_the_test_period_is_too_small():
    """An accuracy computed on 30 rows has a confidence interval wide enough
    to be indistinguishable from guessing — worse than no figure, because it
    looks like measurement."""
    # 1,010 rows clears the label floor but leaves only ~152 in the held-out
    # period, below MINIMUM_TEST_ROWS. Asserted directly rather than behind a
    # conditional — a conditional would silently stop exercising this path if
    # either constant changed, and the test would keep passing.
    rows = _rows(MINIMUM_LABELLED_ROWS + 10)
    assert len(rows) >= MINIMUM_LABELLED_ROWS
    _, _, projected_test = db.temporal_split(rows)
    assert len(projected_test) < db.MINIMUM_TEST_ROWS, "fixture no longer exercises this path"

    with pytest.raises(InsufficientData, match="held-out test period"):
        db.build_dataset(rows, feature_names=FEATURES, label_name=LABEL)


def test_builds_successfully_with_enough_data():
    """The success path exists — it just needs real data."""
    split = db.build_dataset(_rows(2000), feature_names=FEATURES, label_name=LABEL)
    assert len(split.train) == 1400
    assert len(split.test) >= db.MINIMUM_TEST_ROWS
    assert split.label_name == LABEL


def test_built_dataset_reports_its_periods():
    split = db.build_dataset(_rows(2000), feature_names=FEATURES, label_name=LABEL)
    summary = split.summary()
    assert summary["split_strategy"] == "temporal"
    assert summary["periods"]["train"][1] <= summary["periods"]["test"][0]


def test_leakage_is_checked_before_the_row_count():
    """Order matters: a leaky feature set is wrong regardless of volume, and
    reporting 'not enough data' first would send someone off collecting more
    of the wrong thing."""
    with pytest.raises(LeakageDetected):
        db.build_dataset(
            _rows(10),
            feature_names=FEATURES + ["actual_fraud_confirmed"],
            label_name=LABEL,
        )


# ───────────────────────────── readiness ─────────────────────────────────────

def test_readiness_report_states_the_shortfall():
    report = db.readiness_report({"actual_fraud_confirmed": 120})
    entry = report["labels"]["actual_fraud_confirmed"]
    assert entry["ready"] is False
    assert entry["shortfall"] == MINIMUM_LABELLED_ROWS - 120
    assert report["any_ready"] is False


def test_readiness_report_is_honest_about_the_constraint():
    report = db.readiness_report({"actual_fraud_confirmed": 0})
    assert "cannot be raised by writing code" in report["note"]


def test_readiness_flips_when_the_threshold_is_met():
    report = db.readiness_report({"actual_fraud_confirmed": MINIMUM_LABELLED_ROWS})
    assert report["any_ready"] is True
