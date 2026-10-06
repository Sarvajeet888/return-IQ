"""PHASE 32 — workflow rule validation.

THE BUG THIS FIXES
------------------
`WorkflowRuleCreate.conditions` is typed `dict[str, Any]` with no validation.
`_evaluate_condition` logs a warning for an unknown key and returns False.

Verified against the running API — every one of these returned **201 Created**:

    {"fraud_score_gt_": 80}        typo
    {"customer_risk_lt": 10}       plausible invention
    {"fraud_probability_gt": 0.8}  wrong field name
    {"banana_split_eq": "yes"}     nonsense

A merchant configures a fraud rule, sees it saved, sees it listed as active,
and **it never fires.** The only trace is a warning line in a log nobody reads,
emitted once per evaluated return.

This is the same failure as the Phase 6 role gates: **a control that is wrong
in the direction of "does nothing" is completely silent.** Wrong the other way
gives you a visible incident; wrong this way gives you a merchant who believes
they have fraud protection and does not.

THE SECOND PROBLEM: RULES THAT CONTRADICT
-----------------------------------------
Nothing stops two active rules matching the same return with opposite actions
— one auto-approving, one auto-rejecting. Priority decides, so the outcome
depends on a number the merchant probably set to 0 for both.

That is not a bug that announces itself either. It produces inconsistent
decisions on similar returns, which reads as the model being erratic.

THE THIRD PROBLEM: RULES THAT BYPASS PHASE 26
---------------------------------------------
An `auto_approve` rule that issues a refund would route around the
human-in-the-loop gate entirely. Phase 26 established that refunds and
irreversible actions are never automated regardless of confidence; a rule
engine that can do it anyway makes that guarantee decorative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.core.lifecycle import ReturnStatus
from app.services.hitl import NEVER_AUTOMATABLE

__all__ = [
    "VALID_CONDITIONS",
    "RuleValidationError",
    "validate_rule",
    "find_conflicts",
]


class RuleValidationError(ValueError):
    """A rule that cannot be saved, with a reason the merchant can act on."""


# Every condition key the engine can actually evaluate. Kept beside the
# evaluator's mapping deliberately: if the two drift apart, a rule that
# validates will still silently fail, which is the bug this module exists to
# prevent. `test_validator_matches_the_evaluator` asserts they stay in sync.
VALID_CONDITIONS: Final[dict[str, str]] = {
    "risk_score_lt": "Risk score below a value (0-100)",
    "risk_score_gt": "Risk score above a value (0-100)",
    "fraud_score_lt": "Fraud score below a value (0-100)",
    "fraud_score_gt": "Fraud score above a value (0-100)",
    "item_value_lt": "Item value below an amount",
    "item_value_gt": "Item value above an amount",
    "routing_decision_eq": "Routing decision equals a value",
    "reason_code_eq": "Return reason equals a value",
    "payment_mode_eq": "Payment mode equals a value",
    "courier_eq": "Courier equals a value",
    "category_eq": "Product category equals a value",
}

# Conditions whose value must be a number in 0-100. A fraud rule written as
# `fraud_score_gt: 0.8` is a merchant thinking in probabilities against an
# engine thinking in percentages -- it validates, saves, and fires on almost
# every return.
_PERCENT_CONDITIONS: Final[frozenset[str]] = frozenset({
    "risk_score_lt", "risk_score_gt", "fraud_score_lt", "fraud_score_gt",
})

_NUMERIC_CONDITIONS: Final[frozenset[str]] = _PERCENT_CONDITIONS | {
    "item_value_lt", "item_value_gt",
}

VALID_RULE_TYPES: Final[frozenset[str]] = frozenset({
    "auto_approve", "auto_reject", "escalate", "assign",
})


def _suggest(unknown: str) -> str:
    """Nearest known condition, by shared prefix.

    A merchant who typed `fraud_score_gt_` should be told about
    `fraud_score_gt`, not handed a list of eleven keys to search.
    """
    best, best_len = None, 0
    for known in VALID_CONDITIONS:
        shared = 0
        for a, b in zip(unknown, known):
            if a != b:
                break
            shared += 1
        if shared > best_len and shared >= 4:
            best, best_len = known, shared
    return f" Did you mean {best!r}?" if best else ""


def validate_rule(rule: dict[str, Any]) -> None:
    """Raise if this rule cannot do what the merchant expects.

    Every failure names the specific problem. "Invalid rule" sends someone to
    read source they do not have access to.
    """
    rule_type = str(rule.get("rule_type", "")).strip().lower()
    if rule_type not in VALID_RULE_TYPES:
        raise RuleValidationError(
            f"{rule_type!r} is not a rule type. "
            f"Valid: {', '.join(sorted(VALID_RULE_TYPES))}."
        )

    conditions = rule.get("conditions") or {}
    if not isinstance(conditions, dict) or not conditions:
        raise RuleValidationError(
            "A rule needs at least one condition. A rule with none would match "
            "every return."
        )

    for key, value in conditions.items():
        if key not in VALID_CONDITIONS:
            raise RuleValidationError(
                f"{key!r} is not a condition this system can evaluate, so a "
                f"rule using it would never fire.{_suggest(key)} "
                f"Available: {', '.join(sorted(VALID_CONDITIONS))}."
            )

        if key in _NUMERIC_CONDITIONS:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                raise RuleValidationError(
                    f"{key!r} needs a number, not {value!r}."
                ) from None

            if key in _PERCENT_CONDITIONS:
                if not 0 <= numeric <= 100:
                    raise RuleValidationError(
                        f"{key!r} is a score from 0 to 100, but this rule uses "
                        f"{numeric}."
                    )
                # A value below 1 on a 0-100 scale is almost always a merchant
                # thinking in probabilities. It validates as "in range", saves
                # happily, and then a `_gt: 0.8` rule fires on essentially
                # every return while a `_lt: 0.8` rule fires on none.
                #
                # Refused rather than warned: the failure is silent either way,
                # and 0.8 is not a threshold anyone means on a percentage
                # scale.
                if 0 < numeric < 1:
                    raise RuleValidationError(
                        f"{key!r} is a percentage from 0 to 100, but this rule "
                        f"uses {numeric}. Written as a probability, "
                        f"{key.endswith('_gt') and 'this fires on almost every '
                        'return' or 'this fires on almost no returns'}. "
                        f"You probably meant {numeric * 100:.0f}."
                    )

    # ── The Phase 26 guarantee, enforced here too ───────────────────────────
    action = rule.get("action") or {}
    action_status = str(action.get("status", "")).strip().lower()

    # Match against the lifecycle's own vocabulary rather than the HITL action
    # names. The two differ by tense -- HITL says "refund", the lifecycle
    # status is "refunded" -- and my first version compared them directly, so
    # a rule auto-approving to status "refunded" passed the check.
    #
    # A near-miss on a safety check is a safety check that does not fire.
    dangerous_statuses = {
        ReturnStatus.REFUNDED, ReturnStatus.REJECTED,
    } | {s for s in NEVER_AUTOMATABLE}
    # Also catch the tense mismatch in either direction.
    dangerous_statuses |= {s + "ed" for s in NEVER_AUTOMATABLE}
    dangerous_statuses |= {s.rstrip("d").rstrip("e") for s in NEVER_AUTOMATABLE}

    if rule_type == "auto_approve" and action_status in dangerous_statuses:
        raise RuleValidationError(
            f"A rule cannot automatically {action_status!r}. Actions that move "
            f"money outward or cannot be undone always need a person, however "
            f"confident the scores are — a rule engine that could do it anyway "
            f"would make that guarantee decorative."
        )


@dataclass
class RuleConflict:
    rule_a: str
    rule_b: str
    overlap: dict[str, Any]
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_a": self.rule_a,
            "rule_b": self.rule_b,
            "shared_conditions": self.overlap,
            "detail": self.detail,
        }


# Rule types whose outcomes cannot both be right for the same return.
_OPPOSING: Final[set[frozenset[str]]] = {
    frozenset({"auto_approve", "auto_reject"}),
    frozenset({"auto_approve", "escalate"}),
}


@dataclass
class ConflictReport:
    conflicts: list[RuleConflict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "conflicts": [c.as_dict() for c in self.conflicts],
            "count": len(self.conflicts),
            "note": (
                "Conflicting rules do not error — priority silently decides. "
                "That produces inconsistent decisions on similar returns, "
                "which reads as the system being erratic rather than as a "
                "configuration problem."
                if self.conflicts else
                "No two active rules can match the same return with opposing "
                "outcomes."
            ),
        }


def find_conflicts(rules: list[dict[str, Any]]) -> ConflictReport:
    """Find active rules that could both match with opposing outcomes.

    Detects *identical* condition sets rather than attempting general overlap.
    Deciding whether `fraud_score_gt: 60` overlaps `risk_score_lt: 30` requires
    knowing the joint distribution of those scores, which nobody has. An
    approximate answer here would either miss real conflicts or cry wolf on
    rules that never co-fire -- and a conflict warning nobody trusts is worse
    than none.

    Identical conditions are the common case in practice: a merchant
    duplicates a rule to change its action and forgets to disable the
    original.
    """
    active = [r for r in rules if r.get("is_active", True)]
    conflicts: list[RuleConflict] = []

    for i, a in enumerate(active):
        for b in active[i + 1:]:
            types = frozenset({
                str(a.get("rule_type", "")).lower(),
                str(b.get("rule_type", "")).lower(),
            })
            if types not in _OPPOSING:
                continue

            cond_a = a.get("conditions") or {}
            cond_b = b.get("conditions") or {}
            if cond_a != cond_b:
                continue

            same_priority = a.get("priority", 0) == b.get("priority", 0)
            conflicts.append(RuleConflict(
                rule_a=str(a.get("name", a.get("id", "?"))),
                rule_b=str(b.get("name", b.get("id", "?"))),
                overlap=cond_a,
                detail=(
                    f"Both match exactly the same returns but "
                    f"{a.get('rule_type')} and {b.get('rule_type')} pull in "
                    f"opposite directions."
                    + (
                        " They also share a priority, so which one wins is "
                        "effectively arbitrary."
                        if same_priority else
                        f" Priority decides: "
                        f"{a.get('name') if a.get('priority', 0) > b.get('priority', 0) else b.get('name')} "
                        f"wins."
                    )
                ),
            ))

    return ConflictReport(conflicts=conflicts)
