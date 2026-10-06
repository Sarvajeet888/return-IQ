"""PHASE 17 — model family and training harness.

The harness is tested with an injected `predict` function rather than a real
model, so these verify the *guards* — which is the part that has to be right
before any model exists.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.ml import model_family as mf
from app.ml.model_family import MODEL_FAMILY, TaskType
from app.ml.training_harness import TrainingRefused, evaluate, prepare_training


# ───────────────────────── the family is coherent ────────────────────────────

def test_nine_models_are_specified():
    """The roadmap's Phase 17: do NOT use one giant model."""
    assert len(MODEL_FAMILY) == 9


def test_every_spec_validates():
    for spec in MODEL_FAMILY.values():
        spec.validate()


def test_no_target_appears_in_its_own_features():
    for spec in MODEL_FAMILY.values():
        assert spec.target not in spec.features, spec.key


def test_rare_event_models_use_pr_auc_not_accuracy():
    """At a 5% fraud base rate, predicting 'never fraud' scores 95% accuracy.

    Reporting that would be technically true and completely misleading —
    exactly the failure this project has spent sixteen phases removing.
    """
    for key in ("fraud", "damage", "resale", "customer_risk"):
        assert MODEL_FAMILY[key].primary_metric == "pr_auc"


def test_rare_event_models_demand_more_rows():
    """A 5% base rate means 1,000 rows yields ~50 positives — too few to fit
    anything stable."""
    assert MODEL_FAMILY["fraud"].min_labelled_rows > MODEL_FAMILY["cost"].min_labelled_rows


def test_no_spec_can_undercut_the_phase_15_floor():
    for spec in MODEL_FAMILY.values():
        assert spec.min_labelled_rows >= 1000, spec.key


def test_every_model_declares_its_known_difficulty():
    """Stated up front so nobody discovers it after training."""
    for spec in MODEL_FAMILY.values():
        assert spec.known_difficulty, f"{spec.key} has no stated difficulty"
        assert spec.purpose, f"{spec.key} has no stated purpose"


def test_damage_model_forbids_inspection_results():
    """Inspection is how damage is *determined*. Using it as a feature means
    predicting the inspection from the inspection."""
    spec = MODEL_FAMILY["damage"]
    assert "inspection_result" in spec.forbidden_features
    assert "inspection_result" not in spec.features


def test_recovery_model_may_use_damage_grade_and_damage_model_may_not():
    """The prediction points differ, so what counts as leakage differs.

    Recovery is decided AFTER inspection; damage is what inspection decides.
    """
    assert "actual_damage_grade" in MODEL_FAMILY["recovery"].features
    assert "actual_damage_grade" not in MODEL_FAMILY["damage"].features


def test_a_malformed_spec_is_rejected():
    bad = mf.ModelSpec(
        key="bad", name="Bad", task=TaskType.REGRESSION,
        target="x", features=["x"], primary_metric="mae",
        min_labelled_rows=1000,
    )
    with pytest.raises(ValueError, match="also a feature"):
        bad.validate()


def test_a_spec_cannot_lower_the_floor():
    bad = mf.ModelSpec(
        key="bad", name="Bad", task=TaskType.REGRESSION,
        target="y", features=["x"], primary_metric="mae",
        min_labelled_rows=50,
    )
    with pytest.raises(ValueError, match="contradicts the Phase 15 floor"):
        bad.validate()


# ──────────────────────────── readiness ──────────────────────────────────────

def test_family_status_reports_nothing_ready_today():
    """The measured position. Eight of nine have no target column at all."""
    status = mf.family_status({})
    assert status["ready_count"] == 0
    assert status["total"] == 9


def test_readiness_reports_the_shortfall():
    r = mf.readiness("fraud", 1200)
    assert r["ready"] is False
    assert r["shortfall"] == 5000 - 1200


def test_readiness_flips_at_the_threshold():
    assert mf.readiness("cost", 1000)["ready"] is True


def test_status_is_honest_about_the_constraint():
    assert "made ready by writing code" in mf.family_status({})["note"]


def test_unknown_model_is_refused_by_name():
    with pytest.raises(KeyError, match="Unknown model"):
        mf.get_spec("crystal_ball")


# ───────────────────── the harness refuses correctly ─────────────────────────

def _rows(n: int, target: str, *, value=1.0):
    base = datetime.now(UTC) - timedelta(days=500)
    return [
        {
            "created_at": (base + timedelta(hours=i * 6)).isoformat(),
            target: value if i % 3 else 0.0,
            **{f: 1.0 for f in MODEL_FAMILY["cost"].features},
        }
        for i in range(n)
    ]


def test_harness_refuses_below_the_row_floor():
    with pytest.raises(TrainingRefused, match="needs 1,000 labelled rows"):
        prepare_training("cost", _rows(50, "actual_cost_minor"))


def test_refusal_says_labels_cannot_be_manufactured():
    with pytest.raises(TrainingRefused) as exc:
        prepare_training("cost", _rows(50, "actual_cost_minor"))
    assert "cannot be manufactured" in str(exc.value)


def test_refusal_carries_the_known_difficulty():
    """The person hitting the refusal is the person who most needs to know the
    model's caveat."""
    with pytest.raises(TrainingRefused) as exc:
        prepare_training("fraud", _rows(50, "actual_fraud_confirmed"))
    assert "0.556" in str(exc.value) or "oracle" in str(exc.value)


def test_harness_gates_cannot_be_bypassed_by_the_caller():
    """Every guard is read from the spec, not accepted as an argument.

    There is no `min_rows=` parameter to pass, which is the difference between
    a guard rail and a comment asking people to be careful.
    """
    import inspect
    params = set(inspect.signature(prepare_training).parameters)
    assert "min_rows" not in params
    assert "skip_leakage_check" not in params
    assert "force" not in params


def test_harness_builds_when_data_suffices():
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    assert len(split.train) == 1400
    assert split.label_name == "actual_cost_minor"


# ──────────────────────── evaluation against a baseline ──────────────────────

def test_a_model_no_better_than_the_mean_does_not_beat_baseline():
    """A model that cannot beat 'always guess the mean' is not a model.

    Shipping one because the roadmap lists it is worse than shipping nothing,
    because it lends false authority to a coin flip.
    """
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    mean = sum(r["actual_cost_minor"] for r in split.train) / len(split.train)

    result = evaluate("cost", split, predict=lambda rows: [mean] * len(rows))
    assert result.beats_baseline() is False


def test_a_perfect_model_beats_baseline():
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    result = evaluate(
        "cost", split,
        predict=lambda rows: [r["actual_cost_minor"] for r in rows],
    )
    assert result.metrics["mae"] == 0.0
    assert result.beats_baseline() is True


def test_baseline_is_always_reported():
    """MAE of Rs 180 means nothing until you know always-guess-the-mean
    scores Rs 175."""
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    result = evaluate("cost", split, predict=lambda rows: [0.0] * len(rows))
    assert "mae" in result.baseline_metrics


def test_primary_metric_is_first_in_the_result():
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    result = evaluate("cost", split, predict=lambda rows: [0.0] * len(rows))
    assert next(iter(result.metrics)) == MODEL_FAMILY["cost"].primary_metric


def test_prediction_count_mismatch_is_caught():
    split = prepare_training("cost", _rows(2000, "actual_cost_minor"))
    with pytest.raises(ValueError, match="returned"):
        evaluate("cost", split, predict=lambda rows: [0.0])


def test_pr_auc_of_a_useless_classifier_equals_the_base_rate():
    """The number a real fraud model must beat to have earned its place."""
    from app.ml.training_harness import _pr_auc

    labels = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]      # 10% base rate
    assert _pr_auc(labels, [0.5] * 10) == pytest.approx(0.1)


def test_pr_auc_is_independent_of_row_order():
    """The bug this test found in my first implementation.

    A naive sort makes tied scores order-dependent: the same constant-scoring
    classifier returned 1.0, 0.125, 0.143 and 0.100 on identical data,
    depending only on how the rows arrived. A metric that varies with input
    order is not a metric.
    """
    import random

    from app.ml.training_harness import _pr_auc

    labels = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    scores = [0.5] * 10

    results = set()
    for seed in range(10):
        idx = list(range(10))
        random.Random(seed).shuffle(idx)
        results.add(round(_pr_auc([labels[i] for i in idx], scores), 6))

    assert len(results) == 1, f"order-dependent: {results}"
    assert results.pop() == pytest.approx(0.1)


def test_pr_auc_rewards_ranking_positives_first():
    from app.ml.training_harness import _pr_auc

    labels = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    perfect = [0.9, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    assert _pr_auc(labels, perfect) == pytest.approx(1.0)
