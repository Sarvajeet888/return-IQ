"""PHASE 24 — disposition economics.

The property under test: the engine refuses to rank options it cannot
distinguish, because in this domain false precision spends money.
"""
from __future__ import annotations

import pytest

from app.core.money import Money
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
        disposition=disposition,
        recovery=inr(recovery),
        success_probability=probability,
        probability_spread=spread,
        processing_cost=inr(processing),
        logistics_cost=inr(logistics),
        days_to_realise=days,
        recovery_spread=recovery_spread,
    )


# ────────────────────────────── the arithmetic ───────────────────────────────

def test_expected_value_is_recovery_times_probability_minus_costs():
    result = evaluate_dispositions([
        _option(Disposition.RESTOCK, "1000.00", 1.0, processing="100.00",
                logistics="50.00", days=0),
    ])
    # 1000 x 1.0 - 100 - 50 - 0 = 850
    assert result.outcomes[0].expected_value == inr("850.00")


def test_costs_are_subtracted_even_when_the_option_fails():
    """A repair that fails still consumed the technician's hour.

    Modelling costs as probability-weighted would flatter every risky option —
    exactly the options that need scrutiny.
    """
    result = evaluate_dispositions([
        _option(Disposition.REPAIR, "1000.00", 0.0, processing="300.00",
                logistics="50.00", days=0),
    ])
    assert result.outcomes[0].expected_value == inr("-350.00")


def test_money_stays_exact():
    """Phase 3 carries through: no float drift in the economics."""
    result = evaluate_dispositions([
        _option(Disposition.RESELL, "19.99", 1.0, processing="0.00",
                logistics="0.00", days=0),
    ])
    assert result.outcomes[0].expected_value.minor_units == 1999


def test_time_cost_penalises_slow_options():
    """Rs 1,000 recovered in 90 days is not worth Rs 1,000 today.

    Without this term the model systematically over-recommends slow options,
    counting their higher recovery while ignoring that the money is not
    available.
    """
    fast = evaluate_dispositions([
        _option(Disposition.LIQUIDATE, "1000.00", 1.0, days=3),
    ]).outcomes[0]
    slow = evaluate_dispositions([
        _option(Disposition.REPAIR, "1000.00", 1.0, days=90),
    ]).outcomes[0]

    assert slow.time_cost > fast.time_cost
    assert slow.expected_value < fast.expected_value


def test_zero_days_incurs_no_time_cost():
    result = evaluate_dispositions([_option(Disposition.DISPOSE, "0.00", 1.0, days=0)])
    assert result.outcomes[0].time_cost.is_zero()


# ────────────────── the refusal: overlapping ranges ──────────────────────────

def test_overlapping_options_are_declared_indistinguishable():
    """THE test for this phase.

    Measured on the roadmap's own example with honest input uncertainty:

        Repair    Rs 1,033   (range Rs   574 - Rs 1,571)
        Restock   Rs   929   (range Rs   818 - Rs 1,046)

    Repair "wins" by Rs 104. The ranges overlap heavily, so the Rs 104 is not
    real — and a merchant told "repair, +Rs 104" spends technician hours
    chasing money that was never there.
    """
    result = evaluate_dispositions([
        _option(Disposition.REPAIR, "2100.00", 0.70, 0.30, processing="350.00",
                days=21, recovery_spread=0.25),
        _option(Disposition.RESTOCK, "1200.00", 0.90, 0.10, processing="80.00",
                days=3, recovery_spread=0.10),
    ])
    payload = result.as_dict()

    assert payload["recommendation"]["confidence"] == "low"
    assert Disposition.RESTOCK in payload["recommendation"]["indistinguishable_from"]
    assert "not distinguishable" in payload["recommendation"]["reason"]


def test_a_clear_winner_is_recommended_confidently():
    """The refusal must not fire on genuinely separated options, or it becomes
    noise nobody reads."""
    result = evaluate_dispositions([
        _option(Disposition.RESTOCK, "2000.00", 0.95, 0.02, days=2),
        _option(Disposition.DISPOSE, "0.00", 1.0, processing="20.00", days=1),
    ])
    payload = result.as_dict()

    assert payload["recommendation"]["confidence"] == "high"
    assert payload["recommendation"]["disposition"] == Disposition.RESTOCK
    assert "indistinguishable_from" not in payload["recommendation"]


def test_certain_options_produce_a_zero_width_range():
    """Scrapping has no uncertainty — it recovers nothing, reliably."""
    outcome = evaluate_dispositions([
        _option(Disposition.DISPOSE, "0.00", 1.0, 0.0, processing="20.00", days=0),
    ]).outcomes[0]
    assert outcome.lower == outcome.upper


def test_a_wide_range_is_flagged_as_uncertain():
    outcome = evaluate_dispositions([
        _option(Disposition.REPAIR, "2000.00", 0.5, 0.6, recovery_spread=0.4),
    ]).outcomes[0]
    assert outcome.is_uncertain is True


def test_a_tight_range_is_not_flagged():
    outcome = evaluate_dispositions([
        _option(Disposition.LIQUIDATE, "700.00", 0.98, 0.02, recovery_spread=0.02),
    ]).outcomes[0]
    assert outcome.is_uncertain is False


# ─────────────────────────────── ranking ─────────────────────────────────────

def test_options_are_ranked_by_expected_value():
    result = evaluate_dispositions([
        _option(Disposition.LIQUIDATE, "500.00", 1.0, days=0),
        _option(Disposition.RESTOCK, "1500.00", 1.0, days=0),
        _option(Disposition.RECYCLE, "100.00", 1.0, days=0),
    ])
    assert [o.disposition for o in result.ranked] == [
        Disposition.RESTOCK, Disposition.LIQUIDATE, Disposition.RECYCLE,
    ]


def test_the_margin_over_the_next_option_is_reported():
    """"Repair" alone is a recommendation. "Repair, +Rs 400 over restock" is a
    decision a manager can weigh against effort."""
    payload = evaluate_dispositions([
        _option(Disposition.RESTOCK, "2000.00", 1.0, days=0),
        _option(Disposition.LIQUIDATE, "500.00", 1.0, days=0),
    ]).as_dict()
    assert payload["recommendation"]["margin_over_next"]["minor_units"] > 0


def test_a_negative_expected_value_can_still_be_the_best_option():
    """Sometimes every option loses money and the job is to lose the least.
    An engine that only recommends profitable actions is useless on exactly
    the returns that need a decision.
    """
    payload = evaluate_dispositions([
        _option(Disposition.REPAIR, "100.00", 0.5, processing="400.00", days=0),
        _option(Disposition.DISPOSE, "0.00", 1.0, processing="20.00",
                logistics="10.00", days=0),
    ]).as_dict()

    assert payload["recommendation"]["disposition"] == Disposition.DISPOSE
    assert payload["options"][0]["expected_value"]["minor_units"] < 0


# ────────────────────────────── input guards ─────────────────────────────────

def test_an_impossible_probability_is_refused():
    with pytest.raises(ValueError, match="must be in"):
        evaluate_dispositions([_option(Disposition.REPAIR, "100.00", 1.5)])


def test_a_negative_spread_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        evaluate_dispositions([_option(Disposition.REPAIR, "100.00", 0.5, -0.2)])


def test_mixed_currencies_are_refused():
    """Phase 3's rule holds here: adding USD to INR silently would make every
    figure below meaningless."""
    with pytest.raises(ValueError, match="mixed currencies"):
        evaluate_dispositions([
            DispositionInputs(
                Disposition.RESTOCK, inr("1000.00"), 0.9, 0.1,
                Money.from_major("10.00", "USD"), inr("50.00"), 5,
            ),
        ])


def test_no_options_produces_no_recommendation():
    payload = evaluate_dispositions([]).as_dict()
    assert payload["recommendation"] is None


# ──────────────────────── honesty of the output ──────────────────────────────

def test_the_output_explains_that_ranges_carry_probability_uncertainty():
    payload = evaluate_dispositions([
        _option(Disposition.RESTOCK, "1000.00", 0.9, 0.1),
    ]).as_dict()
    assert "probabilities multiplied by amounts" in payload["note"]


def test_every_option_reports_its_range_not_just_a_point():
    payload = evaluate_dispositions([
        _option(Disposition.RESTOCK, "1000.00", 0.9, 0.2),
        _option(Disposition.REPAIR, "1800.00", 0.6, 0.4),
    ]).as_dict()
    for option in payload["options"]:
        assert "range_low" in option
        assert "range_high" in option
