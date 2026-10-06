"""PHASE 26 — human-in-the-loop.

Two properties: nothing dangerous is automated, and disagreement is captured
in a form a future model can learn from.
"""
from __future__ import annotations

import pytest

from app.services.hitl import (
    AUTOMATABLE_ACTIONS,
    NEVER_AUTOMATABLE,
    Override,
    RouteDecision,
    RoutingInputs,
    route_return,
)


def _clean(**overrides):
    """Every signal clean, automation fully enabled — the only state that
    should ever reach AUTOMATE."""
    base = dict(
        action="restock",
        intelligence_confidence="high",
        decision_confidence="high",
        relative_interval_width=0.1,
        strong_findings=0,
        total_findings=0,
        org_automation_enabled=True,
        org_automated_actions=frozenset({"restock"}),
        value_minor=50_000,
        auto_approve_ceiling_minor=100_000,
    )
    base.update(overrides)
    return RoutingInputs(**base)


# ─────────────────────────── the hard stops ──────────────────────────────────

def test_refunds_are_never_automated():
    """Money leaving is not recallable. No confidence level changes that."""
    result = route_return(_clean(action="refund", org_automated_actions=frozenset({"refund"})))
    assert result["automatable"] is False
    assert "moves money outward" in result["reasons"][0]


def test_irreversible_actions_are_never_automated():
    for action in ("dispose", "recycle", "liquidate"):
        result = route_return(_clean(action=action))
        assert result["automatable"] is False, action


def test_customer_facing_rejection_is_never_automated():
    assert route_return(_clean(action="reject"))["automatable"] is False


def test_the_two_action_lists_do_not_overlap():
    """An action that is both automatable and never-automatable would resolve
    by whichever check ran first."""
    assert AUTOMATABLE_ACTIONS.isdisjoint(NEVER_AUTOMATABLE)


# ─────────────────────── automation requires opt-in ──────────────────────────

def test_nothing_is_automated_by_default():
    """The default is not timidity. The models are trained on synthetic data,
    Phase 20 measured the intervals as wide, and Phase 24 reports low
    confidence on most returns. Silent auto-approval in that state is an
    unattended process spending a merchant's money on unvalidated numbers.
    """
    result = route_return(_clean(org_automation_enabled=False))
    assert result["decision"] == RouteDecision.REVIEW
    assert any("has not enabled automation" in r for r in result["reasons"])


def test_opt_in_is_per_action_not_global():
    """Enabling automation for restock must not enable it for pickup
    scheduling."""
    result = route_return(_clean(
        action="schedule_pickup", org_automated_actions=frozenset({"restock"}),
    ))
    assert result["automatable"] is False
    assert any("schedule_pickup" in r for r in result["reasons"])


def test_a_fully_clean_opted_in_return_is_automated():
    """The gate must actually open, or it is not a gate — it is a wall, and
    the automation feature is a lie."""
    result = route_return(_clean())
    assert result["decision"] == RouteDecision.AUTOMATE
    assert result["automatable"] is True


# ──────────────────────── confidence signals ─────────────────────────────────

def test_low_prediction_confidence_forces_review():
    result = route_return(_clean(intelligence_confidence="low"))
    assert result["decision"] == RouteDecision.REVIEW
    assert any("not been validated" in r for r in result["reasons"])


def test_indistinguishable_dispositions_force_review():
    result = route_return(_clean(decision_confidence="low"))
    assert result["decision"] == RouteDecision.REVIEW
    assert any("not distinguishable" in r for r in result["reasons"])


def test_a_wide_prediction_interval_forces_review():
    result = route_return(_clean(relative_interval_width=0.9))
    assert result["decision"] == RouteDecision.REVIEW


def test_a_strong_contradiction_escalates_to_manual():
    """Review means "confirm this". Manual means "decide this" — a strong
    contradiction is not something to rubber-stamp."""
    result = route_return(_clean(strong_findings=1))
    assert result["decision"] == RouteDecision.MANUAL


def test_several_weak_findings_reach_review_but_not_manual():
    result = route_return(_clean(total_findings=4))
    assert result["decision"] == RouteDecision.REVIEW


def test_high_value_returns_get_a_person_even_when_clean():
    result = route_return(_clean(value_minor=500_000, auto_approve_ceiling_minor=100_000))
    assert result["automatable"] is False
    assert any("ceiling" in r for r in result["reasons"])


# ───────────────────────── reasons accumulate ────────────────────────────────

def test_every_reason_is_reported_not_just_the_first():
    """"High value" alone is a different situation from "high value AND
    contradictory evidence AND low confidence". A reviewer needs all of it."""
    result = route_return(_clean(
        intelligence_confidence="low",
        decision_confidence="low",
        relative_interval_width=0.9,
        total_findings=4,
        value_minor=900_000,
    ))
    assert len(result["reasons"]) >= 4


def test_a_clean_automated_return_still_explains_itself():
    result = route_return(_clean())
    assert result["reasons"]
    assert "clean" in result["reasons"][0]


# ──────────────────────── override capture ───────────────────────────────────

def test_an_override_requires_a_substantive_reason():
    """"wrong" teaches nothing. "box was resealed with different tape" teaches
    the next model what to look for."""
    override = Override(
        return_id="r1", org_id="o1", user_id="u1",
        system_decision="repair", human_decision="restock",
        reason_category="incorrect_damage", reason_detail="no", system_confidence="low",
    )
    with pytest.raises(ValueError, match="at least 10 characters"):
        override.validate()


def test_a_substantive_reason_is_accepted():
    Override(
        return_id="r1", org_id="o1", user_id="u1",
        system_decision="repair", human_decision="restock",
        reason_category="incorrect_damage",
        reason_detail="Item arrived undamaged; the customer photographed the box, not the product.",
        system_confidence="low",
    ).validate()      # must not raise


def test_an_override_captures_both_sides_of_the_disagreement():
    """"The human said restock" is useless without "the system said repair"."""
    payload = Override(
        return_id="r1", org_id="o1", user_id="u1",
        system_decision="repair", human_decision="restock",
        reason_category="capacity",
        reason_detail="Repair bench is at capacity for the next three weeks.",
        system_confidence="low",
    ).as_dict()

    assert payload["system_decision"] == "repair"
    assert payload["human_decision"] == "restock"
    assert payload["was_disagreement"] is True


def test_agreement_is_recorded_too():
    """A model evaluated only on cases where humans disagreed is evaluated on
    a biased sample and will look far worse than it is."""
    payload = Override(
        return_id="r1", org_id="o1", user_id="u1",
        system_decision="restock", human_decision="restock",
        reason_category="confirmed",
        reason_detail="Confirmed on inspection — item is in sellable condition.",
        system_confidence="high",
    ).as_dict()
    assert payload["was_disagreement"] is False


def test_the_signals_at_the_time_are_snapshotted():
    """Without this, an override six months old cannot be interpreted: the
    models, rules and feature definitions will all have moved, and "the human
    said restock" means nothing if you cannot see what the system was looking
    at when it said repair.
    """
    payload = Override(
        return_id="r1", org_id="o1", user_id="u1",
        system_decision="repair", human_decision="restock",
        reason_category="incorrect_damage",
        reason_detail="Damage was cosmetic and on the packaging, not the item.",
        system_confidence="low",
        feature_snapshot={"fraud_score": 22, "damage_probability": 0.7,
                         "expected_value_repair": 155000},
    ).as_dict()

    assert payload["feature_snapshot"]["damage_probability"] == 0.7
    assert payload["feature_snapshot"]["expected_value_repair"] == 155000
