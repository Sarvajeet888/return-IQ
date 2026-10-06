"""
Workflow Automation Engine (Phase 5.12)
Evaluates active workflow rules against a scored return and applies
auto-approve / auto-reject / escalate / assign actions.

Rules are evaluated in priority order (lower number = higher priority).
First matching rule wins and stops evaluation (short-circuit).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.core.money import Money
from app.db import store

logger = logging.getLogger(__name__)

# Default SLA window: 48 hours from creation
_DEFAULT_SLA_HOURS = 48


def _evaluate_condition(condition_key: str, condition_value, return_data: dict, pred_data: dict) -> bool:
    """
    Evaluate a single condition key against the return and prediction data.
    Returns True if the condition passes (matches), False otherwise.

    Supported condition keys:
      risk_score_lt / risk_score_gt
      fraud_score_lt / fraud_score_gt
      item_value_lt / item_value_gt
      routing_decision_eq
      reason_code_eq
      payment_mode_eq
      courier_eq
      category_eq
    """
    pred = pred_data or {}
    ret = return_data or {}

    mapping = {
        "risk_score_lt": lambda: float(pred.get("risk_score", 0)) < float(condition_value),
        "risk_score_gt": lambda: float(pred.get("risk_score", 0)) > float(condition_value),
        "fraud_score_lt": lambda: float(pred.get("fraud_score", 0)) < float(condition_value),
        "fraud_score_gt": lambda: float(pred.get("fraud_score", 0)) > float(condition_value),
        "item_value_lt": lambda: int(ret.get("item_value_minor") or 0) < Money.from_major(str(condition_value), ret.get("currency") or "INR").minor_units,
        "item_value_gt": lambda: int(ret.get("item_value_minor") or 0) > Money.from_major(str(condition_value), ret.get("currency") or "INR").minor_units,
        "routing_decision_eq": lambda: pred.get("routing_decision") == condition_value,
        "reason_code_eq": lambda: ret.get("return_reason_code") == condition_value,
        "payment_mode_eq": lambda: ret.get("payment_mode") == condition_value,
        "courier_eq": lambda: ret.get("courier") == condition_value,
        "category_eq": lambda: ret.get("item_category") == condition_value,
    }
    evaluator = mapping.get(condition_key)
    if evaluator is None:
        logger.warning("Unknown workflow condition key: %s", condition_key)
        return False
    try:
        return evaluator()
    except Exception as exc:
        logger.error("Condition evaluation error (%s=%s): %s", condition_key, condition_value, exc)
        return False


def _apply_action(rule: dict, return_id: str, org: dict, pred_data: dict) -> dict:
    """Apply the rule's action to the return and return a summary of what was done."""
    action = rule.get("action") or {}
    applied = {"rule_id": rule["id"], "rule_name": rule["name"], "actions_taken": []}

    # Status update
    if "status" in action:
        store.store_return({"id": return_id, "status": action["status"]})
        applied["actions_taken"].append(f"status -> {action['status']}")

    # Notification
    if action.get("notify"):
        severity = action.get("notify_severity", "info")
        routing = pred_data.get("routing_decision", "unknown")
        store.add_notification({
            "org_id": org["id"],
            "type": f"workflow_{rule['rule_type']}",
            "title": f"⚙️ Workflow: {rule['name']}",
            "message": f"Rule '{rule['name']}' applied to return {return_id} (decision: {routing})",
            "severity": severity,
        })
        applied["actions_taken"].append("notification_sent")

    # SLA setup
    if action.get("set_sla_hours"):
        sla_hours = int(action["set_sla_hours"])
        deadline = datetime.now(UTC) + timedelta(hours=sla_hours)
        existing_sla = store.get_sla_for_return(return_id, org["id"])
        if not existing_sla:
            store.create_sla_record({
                "return_request_id": return_id,
                "org_id": org["id"],
                "sla_deadline": deadline,
                "breached": False,
                "escalated": False,
                "created_at": datetime.now(UTC),
            })
        applied["actions_taken"].append(f"sla_set_{sla_hours}h")

    store.increment_rule_triggered(rule["id"])
    return applied


def apply_workflow_rules(
    return_id: str,
    return_data: dict,
    pred_data: dict,
    org: dict,
) -> list[dict]:
    """
    Run all active workflow rules for the org against this return/prediction.
    Returns list of applied rule summaries (may be empty if no rules match).

    Called immediately after a return is scored, so rules fire automatically
    without any user intervention.
    """
    rules = store.get_workflow_rules(org["id"])
    active_rules = [r for r in rules if r.get("is_active")]
    applied_rules = []

    for rule in active_rules:
        conditions = rule.get("conditions") or {}
        # All conditions must pass (AND logic)
        all_pass = all(
            _evaluate_condition(k, v, return_data, pred_data)
            for k, v in conditions.items()
        )
        if all_pass:
            result = _apply_action(rule, return_id, org, pred_data)
            applied_rules.append(result)
            # Short-circuit: first matching rule wins
            logger.info("Workflow rule '%s' applied to return %s", rule["name"], return_id)
            break

    # Default SLA if no rule set one
    existing_sla = store.get_sla_for_return(return_id, org["id"])
    if not existing_sla:
        deadline = datetime.now(UTC) + timedelta(hours=_DEFAULT_SLA_HOURS)
        store.create_sla_record({
            "return_request_id": return_id,
            "org_id": org["id"],
            "sla_deadline": deadline,
            "breached": False,
            "escalated": False,
            "created_at": datetime.now(UTC),
        })

    return applied_rules
