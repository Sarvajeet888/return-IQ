"""PHASE 26 — human-in-the-loop.

TWO JOBS
--------
**1. Decide what a person must look at.** Confidence signals now exist in
several places — Phase 14's provenance bands, Phase 20's interval width,
Phase 23's contradiction findings, Phase 24's overlap flag. Each is computed
independently, and none of them currently *decides* anything. This module
combines them into one gate.

**2. Capture disagreement.** When a person overrides the system, that is not
an inconvenience to be minimised. It is a human-labelled example of the exact
decision the models cannot yet make — recorded with what the system
recommended, what the person chose instead, and why.

**Overrides are the only training data ReturnIQ can generate without waiting
for outcomes.** An outcome label takes weeks: the item ships back, gets
inspected, gets resold, and the money lands. An override is available the
moment a warehouse manager disagrees. It is weaker evidence — a person's
judgement, not a measured result — but it arrives immediately and it comes
from someone who can see the item.

THE AUTOMATION DEFAULT
----------------------
Nothing is automated unless an organization explicitly opts in, per action,
with a recorded reason. That is deliberate and it is not timidity: the models
are trained on synthetic data (see PHASE_17_FEASIBILITY.md), Phase 20 measured
the intervals as wide, and Phase 24 reports low confidence on most returns.

A system in that state that silently auto-approves refunds is not an
efficiency feature. It is an unattended process spending a merchant's money on
the strength of numbers nobody has validated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "RouteDecision",
    "RoutingInputs",
    "Override",
    "route_return",
    "AUTOMATABLE_ACTIONS",
]


class RouteDecision:
    AUTOMATE: Final = "automate"
    REVIEW: Final = "review"          # a person confirms; system pre-fills
    MANUAL: Final = "manual"          # a person decides; system advises only


# Actions an organization may opt into automating. Deliberately excludes
# anything that moves money outward or is irreversible: a wrongly auto-issued
# refund cannot be recalled, and a wrongly scrapped item cannot be recovered.
# Those stay with a person regardless of confidence.
AUTOMATABLE_ACTIONS: Final[frozenset[str]] = frozenset({
    "restock",
    "route_to_inspection",
    "schedule_pickup",
})

NEVER_AUTOMATABLE: Final[frozenset[str]] = frozenset({
    "refund",        # money leaves; not recallable
    "dispose",       # irreversible
    "recycle",       # irreversible
    "liquidate",     # sold below value, not recallable
    "reject",        # a customer-facing denial
})


@dataclass(frozen=True)
class RoutingInputs:
    """Every confidence signal the system has about one return."""

    action: str
    # Phase 14 — provenance band: high | moderate | low | unknown
    intelligence_confidence: str = "unknown"
    # Phase 24 — did the top options' ranges overlap?
    decision_confidence: str = "low"
    # Phase 20 — interval width relative to the prediction
    relative_interval_width: float | None = None
    # Phase 23 — cross-signal contradictions
    strong_findings: int = 0
    total_findings: int = 0
    # Organization opt-in
    org_automation_enabled: bool = False
    org_automated_actions: frozenset[str] = frozenset()
    # Value at stake, in minor units. High-value returns get a person even
    # when every signal is clean.
    value_minor: int = 0
    auto_approve_ceiling_minor: int = 100_000      # Rs 1,000


@dataclass
class Override:
    """A person disagreeing with the system.

    `reason` is mandatory and free text. A dropdown would produce cleaner data
    and worse data: the useful overrides are the ones where the person saw
    something the system has no field for — "the box was resealed with
    different tape", "this customer called us and explained".
    """

    return_id: str
    org_id: str
    user_id: str
    system_decision: str
    human_decision: str
    reason_category: str
    reason_detail: str
    system_confidence: str | None = None
    system_risk_score: float | None = None
    system_fraud_score: float | None = None
    feature_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def was_disagreement(self) -> bool:
        """Derived, not stored.

        Storing it separately would let the flag and the decisions drift apart
        — a row could claim agreement while recording two different values.
        Deriving it makes that impossible.
        """
        return self.system_decision != self.human_decision

    def validate(self) -> None:
        if not self.reason_detail or len(self.reason_detail.strip()) < 10:
            raise ValueError(
                "An override needs a reason of at least 10 characters. This is "
                "the training signal — 'wrong' teaches nothing, 'box was "
                "resealed with different tape' teaches the next model what to "
                "look for."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "return_id": self.return_id,
            "system_decision": self.system_decision,
            "human_decision": self.human_decision,
            "was_disagreement": self.was_disagreement,
            "reason_category": self.reason_category,
            "reason_detail": self.reason_detail,
            "system_confidence": self.system_confidence,
            "feature_snapshot": self.feature_snapshot,
        }


def route_return(inputs: RoutingInputs) -> dict[str, Any]:
    """Decide whether a person must handle this return.

    Reasons accumulate rather than short-circuiting. A reviewer opening a
    flagged return should see every factor that flagged it, not just the first
    one the code happened to check — "high value" alone is a different
    situation from "high value AND contradictory evidence AND low confidence".
    """
    reasons: list[str] = []
    action = inputs.action.lower()

    # ── Hard stops, ahead of every confidence consideration ─────────────────
    if action in NEVER_AUTOMATABLE:
        return {
            "decision": RouteDecision.MANUAL if inputs.strong_findings else RouteDecision.REVIEW,
            "reasons": [
                f"{action!r} is never automated. It either moves money outward "
                f"or cannot be undone, so a person decides regardless of how "
                f"confident the system is."
            ],
            "automatable": False,
        }

    if not inputs.org_automation_enabled:
        reasons.append(
            "This organization has not enabled automation. Nothing is "
            "auto-actioned until it is switched on deliberately."
        )

    if action not in AUTOMATABLE_ACTIONS:
        reasons.append(f"{action!r} is not on the list of automatable actions.")
    elif inputs.org_automation_enabled and action not in inputs.org_automated_actions:
        reasons.append(f"This organization has not enabled automation for {action!r}.")

    # ── Confidence signals ──────────────────────────────────────────────────
    if inputs.intelligence_confidence in {"low", "unknown"}:
        reasons.append(
            f"Prediction confidence is {inputs.intelligence_confidence} — the "
            f"underlying model has not been validated against real outcomes."
        )

    if inputs.decision_confidence == "low":
        reasons.append(
            "The best and second-best dispositions are not distinguishable on "
            "the evidence available."
        )

    if inputs.relative_interval_width is not None and inputs.relative_interval_width > 0.6:
        reasons.append(
            f"The estimate's range spans "
            f"{inputs.relative_interval_width:.0%} of its own value."
        )

    if inputs.strong_findings:
        reasons.append(
            f"{inputs.strong_findings} strong contradiction(s) between signals."
        )
    elif inputs.total_findings >= 3:
        reasons.append(
            f"{inputs.total_findings} signal findings — none decisive alone, "
            f"worth a look together."
        )

    if inputs.value_minor > inputs.auto_approve_ceiling_minor:
        reasons.append(
            f"Value exceeds this organization's automation ceiling."
        )

    # ── Decide ──────────────────────────────────────────────────────────────
    if inputs.strong_findings:
        decision = RouteDecision.MANUAL
    elif reasons:
        decision = RouteDecision.REVIEW
    else:
        decision = RouteDecision.AUTOMATE

    return {
        "decision": decision,
        "reasons": reasons or ["Every confidence signal is clean and the "
                               "organization has enabled automation for this action."],
        "automatable": decision == RouteDecision.AUTOMATE,
    }
