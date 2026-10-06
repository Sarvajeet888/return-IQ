"""PHASE 35 — grounded change decomposition.

Two properties above all others: contributions reconcile EXACTLY (this is
arithmetic, not an estimate), and a decomposition across several dimensions
must never be read as additive with itself.
"""
from __future__ import annotations

import pytest

from app.ml.evaluation import MIN_SEGMENT_ROWS
from app.services.insight_engine import (
    InsightError,
    compare_dimensions,
    decompose_change,
    narrative,
)


def _rows(n: int, category: str, reason: str, value: int) -> list[dict]:
    return [
        {"item_category": category, "return_reason_code": reason,
         "courier": "Delhivery", "payment_mode": "COD", "item_value_minor": value}
        for _ in range(n)
    ]


# ─────────────────────── reconciliation is exact, not approximate ────────────

def test_contributions_reconcile_exactly_in_currency_mode():
    """This is the property every other 'trust' mechanism in this project
    stops short of: there is no margin of error here, because a segment's
    contribution is a literal sum over rows that happened, not an estimate
    of anything."""
    before = _rows(10, "apparel", "size_issue", 10000)
    after = _rows(6, "apparel", "size_issue", 10000) + _rows(4, "apparel", "size_issue", 25000)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    assert d.reconciles is True
    assert sum(s.absolute_change for s in d.segments) == d.total_absolute_change


def test_reconciliation_holds_at_ledger_scale_with_no_float_drift():
    """10,000 rows of an amount that would drift under float summation
    (Phase 3's lesson, reapplied here)."""
    before = _rows(10_000, "apparel", "size_issue", 1999)
    after = _rows(10_000, "apparel", "size_issue", 2099)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    assert d.reconciles is True
    assert d.total_absolute_change == 10_000 * (2099 - 1999)


def test_reconciliation_is_close_to_tautological_given_correct_grouping():
    """A finding, recorded honestly, from trying to sabotage-prove this flag.

    Every straightforward attempt to break `reconciles` by hardcoding it
    True still passed the whole suite — because summing the same rows after
    regrouping them is guaranteed equal to the ungrouped total by the
    associative property of addition. There is no "sometimes wrong" case to
    construct through the summation step itself.

    The only way reconciliation can genuinely fail is if the GROUPING step
    drops or double-counts a row before summing — for instance, a row with
    no dimension value falling out of every bucket instead of landing in an
    "unknown" bucket. That is what this test constructs and verifies stays
    correct, and it is the only lever that actually moves the flag.
    """
    before = [{"item_value_minor": 100} for _ in range(5)]        # no item_category key
    after = (
        [{"item_value_minor": 100} for _ in range(3)]
        + [{"item_category": "Electronics", "item_value_minor": 200} for _ in range(2)]
    )

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")

    # Every row landed somewhere -- confirmed by row counts, not just the
    # flag -- which is what makes the reconciliation genuine here rather
    # than a coincidence of the arithmetic.
    assert sum(s.before_count for s in d.segments) == len(before)
    assert sum(s.after_count for s in d.segments) == len(after)
    assert d.reconciles is True
    assert any(s.value == "unknown" for s in d.segments)


def test_reconciliation_holds_across_many_segments():
    before = (_rows(20, "a", "x", 100) + _rows(20, "b", "x", 100)
              + _rows(20, "c", "x", 100) + _rows(20, "d", "x", 100))
    after = (_rows(20, "a", "x", 150) + _rows(20, "b", "x", 80)
             + _rows(20, "c", "x", 100) + _rows(20, "d", "x", 300))

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    assert d.reconciles is True
    assert len(d.segments) == 4


# ─────────────── the roadmap's own example, shown to be misleading ───────────

def test_two_dimensions_can_each_independently_claim_the_full_change():
    """THE finding of this phase.

    The roadmap's own illustration lists Electronics, Damage returns, Region
    X and Reverse shipping together as if they were four slices of one
    14.2% pie. They are four DIFFERENT partitions of the same returns, and a
    single return can sit in more than one of them at once.

    Constructed here: 100 returns split evenly across category x reason.
    Only the Electronics+Damaged quarter (25 rows) increases in value; every
    other quarter is unchanged. The WHOLE 22,500-paise increase is
    attributable to that one overlapping group of returns.

    Decomposed by category alone: Electronics claims 100% of the increase.
    Decomposed by reason alone: Damaged ALSO claims 100% of the increase.
    Both are correct within their own dimension. Read together as if
    additive, they claim 200% of a change that only happened once.
    """
    before = (_rows(25, "Electronics", "Damaged", 100)
              + _rows(25, "Electronics", "SizeIssue", 100)
              + _rows(25, "Apparel", "Damaged", 100)
              + _rows(25, "Apparel", "SizeIssue", 100))
    after = (_rows(25, "Electronics", "Damaged", 1000)   # the only group that moves
             + _rows(25, "Electronics", "SizeIssue", 100)
             + _rows(25, "Apparel", "Damaged", 100)
             + _rows(25, "Apparel", "SizeIssue", 100))

    by_category = decompose_change(before, after, value_key="item_value_minor",
                                   dimension="item_category", currency="INR")
    by_reason = decompose_change(before, after, value_key="item_value_minor",
                                 dimension="return_reason_code", currency="INR")

    electronics = next(s for s in by_category.segments if s.value == "Electronics")
    damaged = next(s for s in by_reason.segments if s.value == "Damaged")

    assert electronics.contribution_pct_of_change == 100.0
    assert damaged.contribution_pct_of_change == 100.0

    # Each decomposition is internally correct...
    assert by_category.reconciles is True
    assert by_reason.reconciles is True
    # ...but summing the two "100%" figures would claim 200% of a change
    # that happened exactly once. That is the error the roadmap's own
    # example invites if its four contributors are read as one pie.
    assert electronics.contribution_pct_of_change + damaged.contribution_pct_of_change == 200.0


def test_compare_dimensions_states_the_non_additivity_explicitly():
    before = _rows(50, "Electronics", "Damaged", 100) + _rows(50, "Apparel", "SizeIssue", 100)
    after = _rows(50, "Electronics", "Damaged", 200) + _rows(50, "Apparel", "SizeIssue", 100)

    result = compare_dimensions(
        before, after, value_key="item_value_minor",
        dimensions=["item_category", "return_reason_code"], currency="INR",
    )
    assert "not additive" not in result["note"] or "must not be summed" in result["note"]
    assert "same underlying returns" in result["note"]
    assert set(result["dimensions"]) == {"item_category", "return_reason_code"}


def test_within_one_dimension_contributions_do_sum_to_one_hundred_percent():
    """The property that DOES hold, so the contrast with cross-dimension
    summing is precise rather than "nothing ever adds up"."""
    before = _rows(50, "Electronics", "x", 100) + _rows(50, "Apparel", "x", 100)
    after = _rows(50, "Electronics", "x", 300) + _rows(50, "Apparel", "x", 100)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    total_pct = sum(s.contribution_pct_of_change for s in d.segments)
    assert total_pct == pytest.approx(100.0)


# ──────────────────── contribution vs growth: different numbers ──────────────

def test_contribution_and_growth_rate_are_different_concepts_with_different_values():
    """A small segment that DOUBLES contributes little to the total change,
    while a large segment that grows modestly can dominate it. Conflating
    the two — the exact bug shape in the roadmap's own list, where a
    reader might take "+21%" as a share of the total — hides which is which.
    """
    # Verified by direct computation before writing this test (my first
    # attempt used numbers that did not actually demonstrate the claim):
    #   Apparel:     90 rows, Rs 10,000 -> Rs 11,000 each -> +10% growth,
    #                absolute change Rs 90,000
    #   Electronics: 10 rows, Rs 1,000 -> Rs 2,000 each -> +100% growth,
    #                absolute change Rs 10,000
    before = _rows(90, "Apparel", "x", 1_000_000) + _rows(10, "Electronics", "x", 100_000)
    after = _rows(90, "Apparel", "x", 1_100_000) + _rows(10, "Electronics", "x", 200_000)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    apparel = next(s for s in d.segments if s.value == "Apparel")
    electronics = next(s for s in d.segments if s.value == "Electronics")

    # Electronics doubled -- a dramatic OWN growth rate...
    assert electronics.segment_growth_pct == 100.0
    assert apparel.segment_growth_pct == 10.0
    # ...but Apparel, growing only 10%, contributed nine times more to the
    # total change because it started from a much bigger base. The two
    # numbers disagree about which segment "matters more", which is exactly
    # why they must never be presented as the same figure.
    assert apparel.absolute_change > electronics.absolute_change
    assert apparel.contribution_pct_of_change == 90.0
    assert electronics.contribution_pct_of_change == 10.0
    assert apparel.segment_growth_pct != apparel.contribution_pct_of_change


# ───────────────────────── new and discontinued segments ─────────────────────

def test_a_brand_new_segment_has_no_growth_rate_but_has_a_contribution():
    """Growth rate is undefined with no baseline -- that is a real undefined
    division, not a formatting choice. Contribution is still exact: the
    segment's whole value IS the change, regardless of where it came from."""
    before = _rows(50, "Apparel", "x", 1000)
    after = _rows(50, "Apparel", "x", 1000) + _rows(10, "Electronics", "x", 500)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    electronics = next(s for s in d.segments if s.value == "Electronics")

    assert electronics.status == "new_this_period"
    assert electronics.segment_growth_pct is None
    assert electronics.contribution_pct_of_change == 100.0


def test_a_discontinued_segment_is_still_reported():
    before = _rows(50, "Apparel", "x", 1000) + _rows(10, "Electronics", "x", 500)
    after = _rows(50, "Apparel", "x", 1000)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    electronics = next(s for s in d.segments if s.value == "Electronics")
    assert electronics.status == "discontinued"
    assert electronics.absolute_change < 0


# ───────────── exact numbers always shown; small samples only warned ─────────

def test_a_thin_segment_still_reports_its_exact_number():
    """Not an estimate, so there is no statistical reason to hide it -- the
    number is small, not noisy."""
    before = _rows(2, "Electronics", "x", 1000)
    after = _rows(2, "Electronics", "x", 5000)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR", min_sample=30)
    seg = d.segments[0]
    assert seg.contribution_pct_of_change == 100.0
    assert seg.low_sample_warning is True


def test_a_segment_at_or_above_the_floor_is_not_flagged():
    before = _rows(MIN_SEGMENT_ROWS, "Electronics", "x", 1000)
    after = _rows(MIN_SEGMENT_ROWS, "Electronics", "x", 1500)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    assert d.segments[0].low_sample_warning is False


def test_a_new_segment_below_the_floor_is_flagged():
    before = _rows(50, "Apparel", "x", 1000)
    after = _rows(50, "Apparel", "x", 1000) + _rows(3, "Electronics", "x", 500)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    electronics = next(s for s in d.segments if s.value == "Electronics")
    assert electronics.low_sample_warning is True


# ───────────────────────────── refusals ──────────────────────────────────────

def test_an_unknown_dimension_is_refused():
    before = _rows(10, "a", "x", 100)
    with pytest.raises(InsightError, match="not a dimension"):
        decompose_change(before, before, value_key="item_value_minor",
                         dimension="customer_shoe_size")


def test_no_data_in_either_period_is_refused():
    with pytest.raises(InsightError, match="nothing to explain"):
        decompose_change([], [], value_key="item_value_minor",
                         dimension="item_category", currency="INR")


def test_a_zero_baseline_with_real_current_data_still_computes():
    """Total pct change is undefined with no baseline (real division by
    zero), but the module must not refuse outright just because the AFTER
    period has data the BEFORE period lacks entirely."""
    after = _rows(10, "Electronics", "x", 1000)
    d = decompose_change([], after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    assert d.total_pct_change is None
    assert d.total_absolute_change == 10_000
    assert d.reconciles is True


# ──────────────────────────── narrative fidelity ─────────────────────────────

def test_narrative_numbers_are_the_structured_numbers_verbatim():
    """There is no generation step to drift. Every figure in the text is a
    direct interpolation of an already-tested field, checked here by
    confirming the exact formatted substrings appear in the output.
    """
    before = _rows(60, "Electronics", "x", 1000) + _rows(40, "Apparel", "x", 1000)
    after = _rows(60, "Electronics", "x", 1500) + _rows(40, "Apparel", "x", 1000)

    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR",
                         label="Total return value")
    text = narrative(d)

    assert f"{d.total_pct_change:.1f}%" in text
    for s in d.segments:
        if s.absolute_change != 0:
            assert f"{s.contribution_pct_of_change:+.1f}%" in text
            assert s.value in text


def test_narrative_states_direction_correctly():
    up = _rows(10, "a", "x", 100)
    up_after = _rows(10, "a", "x", 200)
    down = decompose_change(up_after, up, value_key="item_value_minor",
                            dimension="item_category", currency="INR")
    increase = decompose_change(up, up_after, value_key="item_value_minor",
                                dimension="item_category", currency="INR")

    assert "decreased" in narrative(down)
    assert "increased" in narrative(increase)


def test_narrative_flags_a_broken_reconciliation_rather_than_hiding_it():
    """If reconciliation is ever false — which should not happen given exact
    arithmetic, but the check exists precisely to catch the case where it
    somehow does — the narrative must say so rather than presenting an
    unverified figure with confidence."""
    before = _rows(10, "a", "x", 100)
    after = _rows(10, "a", "x", 200)
    d = decompose_change(before, after, value_key="item_value_minor",
                         dimension="item_category", currency="INR")
    object.__setattr__(d, "reconciles", False)  # force the broken state
    assert "unverified" in narrative(d)
