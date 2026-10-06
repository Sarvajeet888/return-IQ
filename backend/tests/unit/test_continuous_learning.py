"""PHASE 29 — continuous learning.

Two properties: nothing reaches production without a person, and the loop
refuses to train on data its own decisions produced.
"""
from __future__ import annotations

import pytest

from app.ml.continuous_learning import (
    MAX_MODEL_AGE_DAYS,
    MAX_SELF_DETERMINED_RATIO,
    MIN_NEW_LABELS,
    CandidateResult,
    approve_candidate,
    check_feedback_contamination,
    should_retrain,
)


def _candidate(**overrides):
    base = dict(
        model_key="fraud",
        version="v1.3.0",
        passed_gates=True,
        gate_report={"allowed": True},
        champion_version="v1.2.0",
        beats_champion=True,
    )
    base.update(overrides)
    return CandidateResult(**base)


def _rows(n, automated=0):
    return (
        [{"outcome_source": "automated"} for _ in range(automated)]
        + [{"outcome_source": "inspection"} for _ in range(n - automated)]
    )


# ────────────────── nothing deploys without a person ─────────────────────────

def test_a_candidate_is_not_deployable_until_approved():
    """The roadmap's own constraint: do not blindly retrain and automatically
    deploy. Made structural — there is no code path from "trained" to "live"."""
    candidate = _candidate()
    assert candidate.is_deployable is False
    assert candidate.as_dict()["status"] == "awaiting_approval"


def test_approval_makes_it_deployable():
    candidate = approve_candidate(
        _candidate(),
        approved_by="om@kalman.example",
        note="Reviewed segment metrics and calibration; electronics improved.",
    )
    assert candidate.is_deployable is True
    assert candidate.approved_at is not None


def test_the_candidate_object_has_no_deploy_method():
    """Structural, not procedural. A `deploy()` here would eventually be
    called by a scheduler."""
    assert not hasattr(_candidate(), "deploy")


def test_approval_requires_a_named_person():
    with pytest.raises(ValueError, match="named person"):
        approve_candidate(_candidate(), approved_by="", note="x" * 30)


def test_approval_requires_a_real_review_note():
    """"looks good" is not a review."""
    with pytest.raises(ValueError, match="at least 20 characters"):
        approve_candidate(
            _candidate(), approved_by="om@kalman.example", note="looks good",
        )


# ──────────────── approval is not an override mechanism ──────────────────────

def test_a_candidate_that_failed_its_gates_cannot_be_approved():
    """Distinct from Phase 28's override.

    There, a person consciously waives a specific failing check with a written
    reason. Here, approval is a rubber stamp at the end of a pipeline — the
    point where least attention is being paid, and therefore the wrong place
    to allow a bypass.
    """
    with pytest.raises(ValueError, match="Phase 28 override"):
        approve_candidate(
            _candidate(passed_gates=False),
            approved_by="om@kalman.example",
            note="We are in a hurry and it seemed fine when I looked at it.",
        )


def test_a_candidate_that_loses_to_the_champion_cannot_be_approved():
    """Deploying it trades a known model for a worse one."""
    with pytest.raises(ValueError, match="does not beat"):
        approve_candidate(
            _candidate(beats_champion=False),
            approved_by="om@kalman.example",
            note="It is newer so presumably it is better than the old one.",
        )


def test_status_distinguishes_why_a_candidate_is_not_deployable():
    """"Not deployable" covers three different situations needing three
    different actions."""
    assert _candidate(passed_gates=False).as_dict()["status"] == "blocked_by_gates"
    assert _candidate(beats_champion=False).as_dict()["status"] == "does_not_beat_champion"
    assert _candidate().as_dict()["status"] == "awaiting_approval"


# ─────────────────────── the feedback trap ───────────────────────────────────

def test_self_determined_labels_are_detected():
    """THE subtle failure of a continuous learning loop.

    If low-risk returns are auto-approved and never inspected, no outcome is
    recorded for them. The training set becomes only the returns a human
    looked at — the hard ones. The model learns that returns look harder than
    they are, flags more, and the next training set is harder still.

    Every metric stays healthy, because they are all computed on the same
    skewed population.
    """
    result = check_feedback_contamination(_rows(1000, automated=600))
    assert result["contaminated"] is True
    assert result["ratio"] == 0.6
    assert "learning to predict itself" in result["detail"]


def test_independently_observed_labels_are_clean():
    result = check_feedback_contamination(_rows(1000, automated=100))
    assert result["contaminated"] is False
    assert result["ratio"] == 0.1


def test_the_contamination_threshold_is_enforced():
    just_under = check_feedback_contamination(
        _rows(1000, automated=int(1000 * MAX_SELF_DETERMINED_RATIO) - 10)
    )
    just_over = check_feedback_contamination(
        _rows(1000, automated=int(1000 * MAX_SELF_DETERMINED_RATIO) + 10)
    )
    assert just_under["contaminated"] is False
    assert just_over["contaminated"] is True


def test_empty_training_data_is_not_reported_as_contaminated():
    result = check_feedback_contamination([])
    assert result["contaminated"] is False
    assert result["total_rows"] == 0


def test_contamination_blocks_retraining():
    trigger = should_retrain(
        new_labels_since_training=5_000,
        model_age_days=200,
        training_rows=_rows(1000, automated=700),
    )
    assert trigger.should_retrain is False
    assert any("learning to predict itself" in b for b in trigger.blockers)


# ────────────────────────── retraining triggers ──────────────────────────────

def test_enough_new_labels_triggers_retraining():
    trigger = should_retrain(
        new_labels_since_training=MIN_NEW_LABELS, model_age_days=10,
    )
    assert trigger.should_retrain is True


def test_too_few_new_labels_blocks_retraining():
    """Retraining on 50 new rows changes the model unpredictably while adding
    almost no information — churn without learning."""
    trigger = should_retrain(new_labels_since_training=50, model_age_days=10)
    assert trigger.should_retrain is False
    assert any("churn without learning" in b for b in trigger.blockers)


def test_an_old_model_is_a_reason_even_without_new_data():
    """Return patterns shift seasonally. A model trained last Diwali is
    describing a different world by March."""
    trigger = should_retrain(
        new_labels_since_training=MIN_NEW_LABELS,
        model_age_days=MAX_MODEL_AGE_DAYS + 1,
    )
    assert any("days old" in r for r in trigger.reasons)


def test_drift_is_a_reason_to_retrain():
    trigger = should_retrain(
        new_labels_since_training=MIN_NEW_LABELS,
        model_age_days=10,
        drift_detected=True,
        major_drift_features=["distance_km", "courier"],
    )
    assert any("distance_km" in r for r in trigger.reasons)


def test_reasons_and_blockers_are_reported_separately():
    """A model can be simultaneously overdue for retraining and unsafe to
    retrain. Collapsing that into one boolean hides exactly the situation that
    most needs a person to look at it.
    """
    trigger = should_retrain(
        new_labels_since_training=50,          # blocker
        model_age_days=MAX_MODEL_AGE_DAYS + 1,  # reason
        drift_detected=True,
        major_drift_features=["distance_km"],   # reason
    )
    assert trigger.reasons
    assert trigger.blockers
    assert trigger.should_retrain is False


def test_the_trigger_states_it_is_not_a_deployment_decision():
    payload = should_retrain(
        new_labels_since_training=MIN_NEW_LABELS, model_age_days=10,
    ).as_dict()
    assert "never a decision to deploy" in payload["note"]
