"""PHASE 25 — counterfactual decision view.

The property under test: the recommendation exposes the assumption it rests
on, so a human with better information can catch it.
"""
from __future__ import annotations

import pytest

from app.core.money import Money
from app.services.counterfactual import compare_to_alternative, counterfactual_view
from app.services.decision_engine import (
    Disposition,
    DispositionInputs,
    evaluate_dispositions,
)


def inr(amount: str) -> Money:
    return Money.from_major(amount, "INR")


def _option(disposition, recovery, probability, spread=0.0, *,
            processing="50.00", logistics="50.00", days=7, recovery_spread=0.0):
    return DispositionInputs(
        disposition=disposition, recovery=inr(recovery),
        success_probability=probability, probability_spread=spread,
        processing_cost=inr(processing), logistics_cost=inr(logistics),
        days_to_realise=days, recovery_spread=recovery_spread,
    )


def _compare(options, chosen, alternative):
    return compare_to_alternative(
        options, evaluate_dispositions(options), chosen, alternative,
    )


# ─────────────────────────── the difference view ─────────────────────────────

def test_the_difference_between_two_options_is_reported():
    options = [
        _option(Disposition.RESTOCK, "2000.00", 1.0, days=0),
        _option(Disposition.LIQUIDATE, "1000.00", 1.0, days=0),
    ]
    comparison = _compare(options, Disposition.RESTOCK, Disposition.LIQUIDATE)
    assert comparison.difference == inr("1000.00")


def test_overlapping_ranges_are_surfaced_in_the_comparison():
    options = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                days=21, recovery_spread=0.25),
        _option(Disposition.RESTOCK, "1200.00", 0.90, 0.10, processing="80.00",
                days=3, recovery_spread=0.10),
    ]
    comparison = _compare(options, Disposition.REPAIR, Disposition.RESTOCK)
    assert comparison.ranges_overlap is True


# ──────────────────── break-even: the actual contribution ────────────────────

def test_break_even_threshold_is_computed():
    """THE addition beyond Phase 24.

    "Repair is worth Rs 500 more" invites a question a warehouse manager
    cannot answer from that sentence: how sure are we? "Repair wins only if
    repairs succeed at least 65% of the time" is answerable — the manager
    knows their own bench.
    """
    options = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                days=21, recovery_spread=0.25),
        _option(Disposition.RESTOCK, "1200.00", 0.90, 0.10, processing="80.00",
                days=3, recovery_spread=0.10),
    ]
    sensitivity = _compare(options, Disposition.REPAIR, Disposition.RESTOCK).break_even

    # Tolerance deliberately tight. My first version used abs=0.03, and
    # sabotage proved it useless: dropping the time-cost term from the
    # break-even calculation shifts the threshold by 0.008, which a 0.03
    # tolerance swallows entirely. A test that cannot detect a missing term
    # in the formula it is testing is decoration.
    assert sensitivity.threshold == pytest.approx(0.65026, abs=0.0005)
    assert sensitivity.current_estimate == 0.70


def test_the_threshold_includes_the_time_cost_of_capital():
    """Sabotage found this missing.

    Removing time cost from the break-even formula passed every other test.
    Repair over 21 days carries Rs 16.92 of tied-up capital on a Rs 2,100
    recovery — small, but it is the difference between a threshold of 64.2%
    and 65.0%, and thresholds are the number a manager acts on.
    """
    slow = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                logistics="70.00", days=21, recovery_spread=0.25),
        _option(Disposition.RESTOCK, "1200.00", 0.90, 0.10, processing="80.00",
                logistics="70.00", days=3, recovery_spread=0.10),
    ]
    fast = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                logistics="70.00", days=0, recovery_spread=0.25),
        slow[1],
    ]

    slow_threshold = _compare(slow, Disposition.REPAIR, Disposition.RESTOCK).break_even.threshold
    fast_threshold = _compare(fast, Disposition.REPAIR, Disposition.RESTOCK).break_even.threshold

    # A slower option must clear a HIGHER bar, because its capital is tied up.
    assert slow_threshold > fast_threshold


def test_a_threshold_inside_the_uncertainty_band_is_flagged_as_a_coin_flip():
    """When the break-even point sits inside our own uncertainty, the ranking
    is not evidence — and the manager should be told so plainly."""
    options = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                days=21, recovery_spread=0.25),
        _option(Disposition.RESTOCK, "1200.00", 0.90, 0.10, processing="80.00",
                days=3, recovery_spread=0.10),
    ]
    sensitivity = _compare(options, Disposition.REPAIR, Disposition.RESTOCK).break_even

    assert sensitivity.reachable is True
    assert "either way" in sensitivity.explanation
    assert "your own success rate" in sensitivity.explanation

    # And the threshold genuinely sits inside the band — asserted directly,
    # because `reachable` alone would pass if the flag were hardcoded. My
    # first version tested only the flag, and sabotage set it to False with
    # every test still green.
    low = sensitivity.current_estimate - sensitivity.uncertainty / 2
    high = sensitivity.current_estimate + sensitivity.uncertainty / 2
    assert low <= sensitivity.threshold <= high


def test_a_threshold_outside_the_band_reports_the_ranking_as_holding():
    options = [
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                days=21, recovery_spread=0.25),
        _option(Disposition.LIQUIDATE, "700.00", 0.98, 0.02, processing="40.00",
                logistics="40.00", days=5, recovery_spread=0.05),
    ]
    sensitivity = _compare(options, Disposition.REPAIR, Disposition.LIQUIDATE).break_even

    assert sensitivity.reachable is False
    assert "ranking holds" in sensitivity.explanation

    # The threshold must genuinely sit outside the band.
    low = sensitivity.current_estimate - sensitivity.uncertainty / 2
    assert sensitivity.threshold < low


def test_an_unreachable_threshold_says_so_plainly():
    """If an option cannot win even at 100% success, saying "it needs 140%"
    would be technically true and useless."""
    options = [
        _option(Disposition.REPAIR, "500.00", 0.7, 0.2, processing="600.00", days=30),
        _option(Disposition.RESTOCK, "1500.00", 0.95, 0.05, days=2),
    ]
    sensitivity = _compare(options, Disposition.REPAIR, Disposition.RESTOCK).break_even

    assert sensitivity.reachable is False
    assert "even if it worked every single time" in sensitivity.explanation


def test_a_dominant_option_says_it_wins_regardless():
    options = [
        _option(Disposition.RESTOCK, "3000.00", 0.95, 0.05, days=1),
        _option(Disposition.DISPOSE, "0.00", 1.0, processing="200.00", days=1),
    ]
    sensitivity = _compare(options, Disposition.RESTOCK, Disposition.DISPOSE).break_even

    assert sensitivity.reachable is False
    assert "even if it never succeeds" in sensitivity.explanation


def test_a_zero_recovery_option_has_no_success_rate_to_trade_off():
    """Dividing by a zero recovery would produce a threshold that means
    nothing. Reporting None and explaining why is the honest answer."""
    options = [
        _option(Disposition.DISPOSE, "0.00", 1.0, processing="20.00", days=0),
        _option(Disposition.RECYCLE, "50.00", 0.9, 0.1, days=2),
    ]
    sensitivity = _compare(options, Disposition.DISPOSE, Disposition.RECYCLE).break_even

    assert sensitivity.threshold is None
    assert "recovers nothing" in sensitivity.explanation


# ────────────────── break-even does not depend on the model ──────────────────

def test_the_threshold_is_unchanged_by_the_probability_estimate():
    """The most important property here.

    Break-even is arithmetic on the merchant's own costs and recoveries. It
    does not depend on the model's probability being right — so it stays
    reliable even while the probabilities do not, which makes it the most
    trustworthy output this system currently produces.
    """
    def threshold_at(probability):
        options = [
            _option(Disposition.REPAIR, "2000.00", probability, 0.2,
                    processing="300.00", days=14),
            _option(Disposition.RESTOCK, "1000.00", 0.9, 0.1, days=3),
        ]
        return _compare(options, Disposition.REPAIR, Disposition.RESTOCK).break_even.threshold

    # The model's estimate swings wildly; the threshold does not move.
    assert threshold_at(0.3) == pytest.approx(threshold_at(0.9), abs=0.001)


# ─────────────────────────── the assembled view ──────────────────────────────

def test_every_alternative_is_compared_against_the_leader():
    """A manager sees not only "why this" but "why not that" for each option
    they might have reached for."""
    options = [
        _option(Disposition.REPAIR, "2100.00", 0.7, 0.3, processing="350.00", days=21),
        _option(Disposition.RESTOCK, "1200.00", 0.9, 0.1, processing="80.00", days=3),
        _option(Disposition.LIQUIDATE, "700.00", 0.98, 0.02, days=5),
    ]
    view = counterfactual_view(options)
    assert len(view["comparisons"]) == 2


def test_the_view_carries_the_recommendation_and_its_confidence():
    options = [
        _option(Disposition.RESTOCK, "2000.00", 0.95, 0.02, days=2),
        _option(Disposition.DISPOSE, "0.00", 1.0, processing="20.00", days=1),
    ]
    view = counterfactual_view(options)
    assert view["recommendation"]["confidence"] == "high"
    assert view["recommendation"]["disposition"] == Disposition.RESTOCK


def test_the_note_explains_why_thresholds_are_trustworthy():
    view = counterfactual_view([
        _option(Disposition.RESTOCK, "1000.00", 0.9, 0.1),
        _option(Disposition.LIQUIDATE, "500.00", 0.98, 0.02),
    ])
    assert "do not depend on the model being right" in view["counterfactual_note"]


def test_no_options_produces_an_empty_view():
    view = counterfactual_view([])
    assert view["recommendation"] is None
    assert view["comparisons"] == []


def test_a_single_option_has_nothing_to_compare_against():
    view = counterfactual_view([_option(Disposition.RESTOCK, "1000.00", 0.9, 0.1)])
    assert view["comparisons"] == []
    assert view["recommendation"]["disposition"] == Disposition.RESTOCK
