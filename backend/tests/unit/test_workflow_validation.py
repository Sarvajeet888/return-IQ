"""PHASE 32 — workflow rule validation.

The property under test: a rule that cannot do what the merchant expects is
refused at creation, not accepted and then silently inert.
"""
from __future__ import annotations

import pytest

from app.services.workflow_validation import (
    VALID_CONDITIONS,
    RuleValidationError,
    find_conflicts,
    validate_rule,
)


def _rule(**overrides):
    base = {
        "name": "Auto-approve low risk",
        "rule_type": "auto_approve",
        "conditions": {"risk_score_lt": 20, "item_value_lt": 500},
        "action": {"status": "approved"},
        "priority": 1,
        "is_active": True,
    }
    base.update(overrides)
    return base


# ────────────────── the silent-failure bug this phase fixes ──────────────────

def test_an_unknown_condition_is_refused():
    """THE bug.

    Verified against the running API before the fix: {"banana_split_eq":
    "yes"} returned 201 Created. The rule appeared in the merchant's list as
    active and never fired — the only trace a warning in a log nobody reads.

    Same failure as the Phase 6 role gates: a control wrong in the direction
    of "does nothing" is completely silent.
    """
    with pytest.raises(RuleValidationError, match="never fire"):
        validate_rule(_rule(conditions={"banana_split_eq": "yes"}))


def test_a_typo_suggests_the_intended_condition():
    """A merchant who typed fraud_score_gt_ should be told about
    fraud_score_gt, not handed eleven keys to search."""
    with pytest.raises(RuleValidationError, match="fraud_score_gt"):
        validate_rule(_rule(conditions={"fraud_score_gt_": 80}))


def test_a_plausible_invention_is_refused():
    """customer_risk_lt sounds exactly like something this system would
    support. It does not."""
    with pytest.raises(RuleValidationError, match="not a condition"):
        validate_rule(_rule(conditions={"customer_risk_lt": 10}))


def test_a_valid_rule_is_accepted():
    """The validator must not block legitimate rules, or merchants stop using
    automation entirely."""
    validate_rule(_rule())


def test_every_documented_condition_actually_validates():
    for key in VALID_CONDITIONS:
        value = 50 if "score" in key or "value" in key else "something"
        validate_rule(_rule(conditions={key: value}))


def test_the_validator_matches_the_evaluator():
    """If the two lists drift apart, a rule that validates will still silently
    fail — the exact bug this module exists to prevent."""
    import inspect

    from app.services import workflow_service

    source = inspect.getsource(workflow_service._evaluate_condition)
    for key in VALID_CONDITIONS:
        assert f'"{key}"' in source, (
            f"{key!r} is accepted by the validator but the evaluator cannot "
            f"handle it — rules using it would validate and never fire."
        )


# ────────────────────── the probability/percentage trap ──────────────────────

def test_a_probability_on_a_percentage_scale_is_refused():
    """A merchant thinking in probabilities writes fraud_score_gt: 0.8.

    It validates as "in range", saves happily, and then fires on essentially
    every return — because scores run 0-100.
    """
    with pytest.raises(RuleValidationError, match="probably meant 80"):
        validate_rule(_rule(conditions={"fraud_score_gt": 0.8}))


def test_an_out_of_range_score_is_refused():
    with pytest.raises(RuleValidationError, match="0 to 100"):
        validate_rule(_rule(conditions={"risk_score_gt": 150}))


def test_zero_is_still_a_valid_threshold():
    """0 is a legitimate boundary; only values strictly between 0 and 1 are
    the probability mistake."""
    validate_rule(_rule(conditions={"risk_score_gt": 0}))


def test_a_non_numeric_score_is_refused():
    with pytest.raises(RuleValidationError, match="needs a number"):
        validate_rule(_rule(conditions={"risk_score_lt": "low"}))


# ──────────────── rules cannot bypass the Phase 26 guarantee ─────────────────

def test_a_rule_cannot_auto_refund():
    """Phase 26 established that refunds are never automated regardless of
    confidence. A rule engine that could do it anyway would make that
    guarantee decorative."""
    with pytest.raises(RuleValidationError, match="always need a person"):
        validate_rule(_rule(rule_type="auto_approve", action={"status": "refunded"}))


def test_the_tense_mismatch_does_not_create_a_gap():
    """My first version compared the action against HITL's action names —
    "refund" — while the lifecycle status is "refunded". The rule passed.

    A near-miss on a safety check is a safety check that does not fire.
    """
    for status in ("refund", "refunded", "reject", "rejected",
                   "dispose", "liquidate", "recycle"):
        with pytest.raises(RuleValidationError):
            validate_rule(_rule(rule_type="auto_approve", action={"status": status}))


def test_auto_approving_to_approved_is_allowed():
    """The gate must not block the one thing auto_approve is for."""
    validate_rule(_rule(rule_type="auto_approve", action={"status": "approved"}))


def test_escalation_to_a_dangerous_status_is_not_blocked():
    """Escalation sends it to a person — which is the safe direction, and
    blocking it would push merchants toward doing nothing instead."""
    validate_rule(_rule(rule_type="escalate", action={"status": "under_review"}))


# ─────────────────────────── structural checks ───────────────────────────────

def test_a_rule_with_no_conditions_is_refused():
    """It would match every return."""
    with pytest.raises(RuleValidationError, match="at least one condition"):
        validate_rule(_rule(conditions={}))


def test_an_unknown_rule_type_is_refused():
    with pytest.raises(RuleValidationError, match="not a rule type"):
        validate_rule(_rule(rule_type="auto_maybe"))


# ────────────────────────── conflicting rules ────────────────────────────────

def test_opposing_rules_on_identical_conditions_are_flagged():
    """Nothing stopped two active rules matching the same return with opposite
    actions. Priority silently decides — producing inconsistent decisions on
    similar returns, which reads as the system being erratic."""
    rules = [
        _rule(name="Approve small", rule_type="auto_approve"),
        _rule(name="Reject small", rule_type="auto_reject"),
    ]
    report = find_conflicts(rules)
    assert report.conflicts
    assert {report.conflicts[0].rule_a, report.conflicts[0].rule_b} == {
        "Approve small", "Reject small",
    }


def test_equal_priority_conflicts_are_called_arbitrary():
    rules = [
        _rule(name="A", rule_type="auto_approve", priority=0),
        _rule(name="B", rule_type="auto_reject", priority=0),
    ]
    assert "arbitrary" in find_conflicts(rules).conflicts[0].detail


def test_different_priorities_name_the_winner():
    rules = [
        _rule(name="A", rule_type="auto_approve", priority=5),
        _rule(name="B", rule_type="auto_reject", priority=1),
    ]
    assert "A" in find_conflicts(rules).conflicts[0].detail


def test_inactive_rules_do_not_conflict():
    """A disabled rule cannot fire, so it cannot contradict anything."""
    rules = [
        _rule(name="A", rule_type="auto_approve"),
        _rule(name="B", rule_type="auto_reject", is_active=False),
    ]
    assert find_conflicts(rules).conflicts == []


def test_rules_with_different_conditions_are_not_flagged():
    """Deliberately conservative. Deciding whether fraud_score_gt: 60 overlaps
    risk_score_lt: 30 needs the joint distribution of those scores, which
    nobody has — and a conflict warning nobody trusts is worse than none."""
    rules = [
        _rule(name="A", rule_type="auto_approve", conditions={"risk_score_lt": 20}),
        _rule(name="B", rule_type="auto_reject", conditions={"fraud_score_gt": 90}),
    ]
    assert find_conflicts(rules).conflicts == []


def test_same_direction_rules_are_not_conflicts():
    rules = [
        _rule(name="A", rule_type="auto_approve"),
        _rule(name="B", rule_type="auto_approve"),
    ]
    assert find_conflicts(rules).conflicts == []


def test_a_clean_rule_set_says_so():
    report = find_conflicts([_rule(name="A")])
    assert report.conflicts == []
    assert report.as_dict()["count"] == 0
    assert "No two active rules" in report.as_dict()["note"]


def test_the_conflict_note_explains_the_consequence():
    rules = [
        _rule(name="A", rule_type="auto_approve"),
        _rule(name="B", rule_type="auto_reject"),
    ]
    note = find_conflicts(rules).as_dict()["note"]
    assert "priority silently decides" in note.lower()
