"""
Unit tests for the workflow automation engine (Phase 9.2).

The workflow engine decides whether returns get auto-approved, auto-rejected,
or escalated. A bug here silently mis-routes real money, so the condition
evaluator is tested exhaustively including the failure modes.
"""
from __future__ import annotations
import pytest

from app.services.workflow_service import _evaluate_condition


# ── Numeric comparisons ───────────────────────────────────────────────────────

@pytest.mark.parametrize("key,threshold,pred,expected", [
    ("risk_score_lt", 30, {"risk_score": 20.0}, True),
    ("risk_score_lt", 30, {"risk_score": 30.0}, False),   # boundary: not strictly less
    ("risk_score_lt", 30, {"risk_score": 50.0}, False),
    ("risk_score_gt", 70, {"risk_score": 85.0}, True),
    ("risk_score_gt", 70, {"risk_score": 70.0}, False),   # boundary: not strictly greater
    ("fraud_score_gt", 50, {"fraud_score": 99.9}, True),
    ("fraud_score_lt", 50, {"fraud_score": 0.0}, True),
])
def test_prediction_numeric_conditions(key, threshold, pred, expected):
    assert _evaluate_condition(key, threshold, {}, pred) is expected


@pytest.mark.parametrize("key,threshold,ret,expected", [
    ("item_value_lt", 500, {"item_value_minor": 49999, "currency": "INR"}, True),
    ("item_value_lt", 500, {"item_value_minor": 50000, "currency": "INR"}, False),
    ("item_value_gt", 20000, {"item_value_minor": 4500000, "currency": "INR"}, True),
    ("item_value_gt", 20000, {"item_value_minor": 10000, "currency": "INR"}, False),
])
def test_return_numeric_conditions(key, threshold, ret, expected):
    assert _evaluate_condition(key, threshold, ret, {}) is expected


# ── String equality ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,value,ret,pred,expected", [
    ("payment_mode_eq", "COD", {"payment_mode": "COD"}, {}, True),
    ("payment_mode_eq", "COD", {"payment_mode": "Prepaid"}, {}, False),
    ("courier_eq", "BlueDart", {"courier": "BlueDart"}, {}, True),
    ("category_eq", "Electronics", {"item_category": "Electronics"}, {}, True),
    ("reason_code_eq", "defective", {"return_reason_code": "defective"}, {}, True),
    ("routing_decision_eq", "reject", {}, {"routing_decision": "reject"}, True),
    ("routing_decision_eq", "accept", {}, {"routing_decision": "reject"}, False),
])
def test_string_equality_conditions(key, value, ret, pred, expected):
    assert _evaluate_condition(key, value, ret, pred) is expected


# ── Failure modes: these must NEVER raise, only return False ─────────────────

def test_unknown_condition_key_returns_false_not_raises():
    """
    An unknown key means a rule was authored against a field that doesn't
    exist. Returning False (rule doesn't match) is correct - raising would
    take down the entire scoring endpoint for one malformed rule.
    """
    assert _evaluate_condition("nonexistent_field_xyz", 42, {}, {}) is False


def test_missing_field_defaults_to_zero_not_crash():
    """A prediction dict missing risk_score shouldn't crash the evaluator."""
    assert _evaluate_condition("risk_score_lt", 30, {}, {}) is True    # 0 < 30
    assert _evaluate_condition("risk_score_gt", 30, {}, {}) is False   # 0 > 30 is False


def test_non_numeric_value_returns_false_not_raises():
    """A rule with a string threshold on a numeric field must not crash."""
    result = _evaluate_condition("risk_score_lt", "not-a-number", {}, {"risk_score": 10})
    assert result is False


def test_none_dicts_handled():
    """Defensive: None instead of dict must not raise."""
    assert _evaluate_condition("risk_score_lt", 30, None, None) is True


def test_string_numeric_coerced():
    """Conditions stored as JSON may come back as strings - must still compare."""
    assert _evaluate_condition("risk_score_lt", "30", {}, {"risk_score": 20}) is True


# ── Realistic rule scenarios (AND logic across multiple conditions) ──────────

def _all_conditions_pass(conditions: dict, ret: dict, pred: dict) -> bool:
    """Mirrors the AND logic in apply_workflow_rules()."""
    return all(_evaluate_condition(k, v, ret, pred) for k, v in conditions.items())


def test_auto_approve_low_risk_scenario():
    """Rule: auto-approve if risk < 20 AND value < 500."""
    conditions = {"risk_score_lt": 20, "item_value_lt": 500}

    # Both pass -> rule fires
    assert _all_conditions_pass(conditions, {"item_value_minor": 30000, "currency": "INR"}, {"risk_score": 10}) is True

    # Risk too high -> rule does NOT fire
    assert _all_conditions_pass(conditions, {"item_value_minor": 30000, "currency": "INR"}, {"risk_score": 50}) is False

    # Value too high -> rule does NOT fire (this is the expensive mistake to avoid)
    assert _all_conditions_pass(conditions, {"item_value_minor": 4000000, "currency": "INR"}, {"risk_score": 10}) is False


def test_auto_reject_high_fraud_scenario():
    conditions = {"fraud_score_gt": 85}
    assert _all_conditions_pass(conditions, {}, {"fraud_score": 92}) is True
    assert _all_conditions_pass(conditions, {}, {"fraud_score": 85}) is False


def test_escalate_high_value_cod_scenario():
    """High-value COD returns are the classic fraud vector - must escalate."""
    conditions = {"item_value_gt": 20000, "payment_mode_eq": "COD"}

    assert _all_conditions_pass(
        conditions, {"item_value_minor": 4500000, "currency": "INR", "payment_mode": "COD"}, {}
    ) is True

    # Prepaid high value -> different (lower) risk profile, rule shouldn't fire
    assert _all_conditions_pass(
        conditions, {"item_value_minor": 4500000, "currency": "INR", "payment_mode": "Prepaid"}, {}
    ) is False


def test_empty_conditions_matches_everything():
    """
    A rule with no conditions matches every return. This is intentional
    (it's how you write a catch-all rule) but worth pinning down so nobody
    "fixes" it later without realising.
    """
    assert _all_conditions_pass({}, {}, {}) is True
