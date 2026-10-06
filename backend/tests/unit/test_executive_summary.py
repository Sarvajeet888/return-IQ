"""PHASE 36 — executive intelligence.

The property under test: picking a single "primary driver" must not
silently recreate the Phase 35 double-counting problem by presenting one
dimension as the whole story when another explains the change just as well.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.executive_summary import build_summary, lead_dimension


def _rows(n, category, reason, value, *, status="pending", created=None, updated=None):
    return [
        {"item_category": category, "return_reason_code": reason, "courier": "Delhivery",
         "payment_mode": "COD", "item_value_minor": value, "status": status,
         "created_at": created, "updated_at": updated}
        for _ in range(n)
    ]


def test_when_no_dimension_varies_at_all_no_driver_is_fabricated():
    """Found live, not in a unit test -- the same class of gap the previous
    fix addressed, one level up.

    An end-to-end check using data where EVERY dimension happened to be
    constant (one courier, one category, one payment mode, one reason --
    entirely plausible for a small or new merchant) still fell through to a
    fallback branch and reported an arbitrary alphabetically-first dimension
    as the "primary driver" at 66.7%, because every degenerate dimension
    ties at exactly 100% contribution by tautology and something had to be
    picked. That is fabricating a finding from data that contains none.

    My unit tests never caught this because every fixture up to this point
    left at least one real dimension varying. This one deliberately does not.
    """
    before = _rows(30, "Electronics", "Damaged", 100_000)
    after = _rows(20, "Electronics", "Damaged", 250_000)
    for r in before + after:
        r["courier"] = "Delhivery"
        r["payment_mode"] = "COD"

    result = lead_dimension(before, after, value_key="item_value_minor", currency="INR")

    assert result.dimension is None
    assert result.decomposition is None
    payload = result.as_dict()
    assert payload == {"led_with": None, "reason": payload["reason"]}
    assert "no specific driver can be isolated" in payload["reason"]


def test_the_summary_reports_no_driver_honestly_rather_than_a_fabricated_one():
    """The build_summary()-level version of the same fix -- this is what the
    live endpoint actually returns."""
    before = _rows(30, "Electronics", "Damaged", 100_000)
    after = _rows(20, "Electronics", "Damaged", 250_000)
    for r in before + after:
        r["courier"] = "Delhivery"
        r["payment_mode"] = "COD"

    summary = build_summary(before, after, currency="INR")
    payload = summary.as_dict()

    assert payload["primary_driver"]["led_with"] is None
    assert "no specific driver" in payload["primary_driver"]["reason"]


# ────────────────── the disambiguation this module has to get right ──────────

def test_two_comparably_explanatory_dimensions_are_both_surfaced():
    """The exact Phase 35 overlap scenario, now at the executive layer.

    Picking "the most explanatory dimension" and showing it alone would
    silently recreate the double-counting problem Phase 35 found in the
    roadmap's own example -- just dressed up as one confident answer instead
    of a visible list. Electronics and Damaged each explain 100% of this
    change through their own top segment; both must be named.
    """
    before = (_rows(25, "Electronics", "Damaged", 100)
              + _rows(25, "Electronics", "SizeIssue", 100)
              + _rows(25, "Apparel", "Damaged", 100)
              + _rows(25, "Apparel", "SizeIssue", 100))
    after = (_rows(25, "Electronics", "Damaged", 1000)
             + _rows(25, "Electronics", "SizeIssue", 100)
             + _rows(25, "Apparel", "Damaged", 100)
             + _rows(25, "Apparel", "SizeIssue", 100))

    result = lead_dimension(before, after, value_key="item_value_minor", currency="INR")

    assert result.dimension in {"item_category", "return_reason_code"}
    assert result.comparable_alternatives  # the runner-up must not be hidden
    payload = result.as_dict()
    assert "disambiguation" in payload
    assert "not the single cause" in payload["disambiguation"]


def test_a_dimension_with_only_one_value_cannot_win_by_default():
    """A real bug found by running this test, not by reading the code.

    Every row in these fixtures shares one courier. Decomposing by courier
    then produces exactly one segment, which is TAUTOLOGICALLY 100% of the
    change — there is nowhere else for the change to be attributed. My first
    version ranked that alongside genuine multi-segment dimensions and let it
    win outright, reporting a data-shape artefact as if it were a finding.

    Fixed: a dimension with fewer than two distinct values is excluded from
    leadership candidacy entirely.
    """
    before = _rows(50, "Electronics", "Damaged", 100) + _rows(50, "Apparel", "SizeIssue", 100)
    after = _rows(50, "Electronics", "Damaged", 500) + _rows(50, "Apparel", "SizeIssue", 100)
    for r in before + after:
        r["courier"] = "Delhivery"       # only one value -- must not win
        r["payment_mode"] = "COD"        # only one value -- must not win

    result = lead_dimension(before, after, value_key="item_value_minor", currency="INR")
    assert result.dimension not in {"courier", "payment_mode"}
    assert result.dimension in {"item_category", "return_reason_code"}


def test_the_comparable_ratio_only_fires_above_its_threshold():
    """A dimension explaining a small, genuinely secondary share of the
    change must not trigger the disambiguation — only a real rival should.

    Verified by direct computation before writing this test:
        by category: Electronics +50%, Apparel +50%, Home 0%   -> top 50%
        by reason:   SizeIssue +100%, Damaged 0%                -> top 100%

    Reason concentrates the whole change in one segment; category splits it
    across two. 50/100 = 0.5, well under the 0.85 comparable threshold, so
    category must not be listed as a rival explanation to reason.
    """
    before = (_rows(45, "Electronics", "SizeIssue", 1000)
              + _rows(45, "Apparel", "SizeIssue", 1000)
              + _rows(10, "Home", "Damaged", 1000))
    after = (_rows(45, "Electronics", "SizeIssue", 1100)
             + _rows(45, "Apparel", "SizeIssue", 1100)
             + _rows(10, "Home", "Damaged", 1000))
    for r in before + after:
        r["courier"] = "Delhivery"
        r["payment_mode"] = "COD"

    result = lead_dimension(before, after, value_key="item_value_minor", currency="INR")
    assert result.dimension == "return_reason_code"
    assert result.comparable_alternatives == []


# ─────────────────────────────── KPIs ─────────────────────────────────────────

def test_total_returns_and_value_are_summed_correctly():
    before = _rows(10, "Apparel", "x", 1000)
    after = _rows(15, "Apparel", "x", 1000)
    summary = build_summary(before, after, currency="INR")

    assert summary.total_returns_before == 10
    assert summary.total_returns_after == 15
    assert summary.total_value_after == 15_000


def test_a_missing_value_field_reports_none_not_a_fabricated_zero():
    rows = [{"item_category": "x", "status": "pending"} for _ in range(5)]
    summary = build_summary(rows, rows, currency="INR")
    assert summary.total_value_before is None
    assert summary.total_value_after is None


def test_status_breakdown_reflects_the_after_period():
    after = (_rows(3, "a", "x", 100, status="approved")
             + _rows(2, "a", "x", 100, status="rejected"))
    summary = build_summary(after, after, currency="INR")
    assert summary.status_breakdown_after == {"approved": 3, "rejected": 2}


# ─────────────────────────── resolution time ──────────────────────────────────

def _terminal_row(hours: float, status="refunded"):
    created = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "item_category": "x", "return_reason_code": "x", "courier": "x",
        "payment_mode": "COD", "item_value_minor": 100, "status": status,
        "created_at": created, "updated_at": created + timedelta(hours=hours),
    }


def test_median_resolution_time_is_computed_from_terminal_returns_only():
    """updated_at - created_at only means 'time to resolution' for a return
    that has stopped changing. Including in-flight returns would mix a real
    duration with a mid-flow snapshot of wherever the return happens to be."""
    rows = [
        _terminal_row(2, "refunded"), _terminal_row(4, "refunded"),
        _terminal_row(6, "closed"),
        {**_terminal_row(9999), "status": "pending"},  # must be excluded
    ]
    summary = build_summary(rows, rows, currency="INR")
    assert summary.resolution_sample_size == 3
    assert summary.median_resolution_hours == 4.0


def test_no_terminal_returns_yields_no_resolution_figure():
    rows = [{**_terminal_row(5), "status": "pending"}]
    summary = build_summary(rows, rows, currency="INR")
    assert summary.median_resolution_hours is None
    assert summary.resolution_sample_size == 0


def test_a_return_updated_before_it_was_created_is_excluded_not_negative():
    """Clock skew or a bad backfill could otherwise produce a negative
    'resolution time', which is nonsensical and would corrupt the median."""
    created = datetime(2026, 1, 5, tzinfo=UTC)
    bad = {"item_category": "x", "status": "refunded",
           "created_at": created, "updated_at": created - timedelta(hours=1)}
    good = _terminal_row(3)
    summary = build_summary([bad, good], [bad, good], currency="INR")
    assert summary.resolution_sample_size == 1
    assert summary.median_resolution_hours == 3.0


# ──────────────────────────── robustness ──────────────────────────────────────

def test_empty_data_does_not_crash():
    summary = build_summary([], [], currency="INR")
    assert summary.total_returns_after == 0
    assert summary.lead is None


def test_the_summary_serializes_cleanly():
    before = _rows(20, "Apparel", "x", 1000)
    after = _rows(25, "Apparel", "x", 1500)
    payload = build_summary(before, after, currency="INR").as_dict()
    assert "primary_driver" in payload
    assert "total_returns" in payload
