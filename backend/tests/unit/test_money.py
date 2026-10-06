"""Tests for app.core.money.

These are not decorative. Several of them encode the exact bug that the old
Float columns caused, so a future refactor that reintroduces floats fails here
loudly instead of quietly producing wrong remittance figures.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import CurrencyMismatch, Money, MoneyError


# --------------------------------------------------------------- construction

def test_from_major_string_is_exact():
    assert Money.from_major("1500.50", "INR").minor_units == 150050


def test_from_major_rejects_float():
    with pytest.raises(MoneyError, match="rejects float"):
        Money.from_major(1500.50, "INR")


def test_jpy_has_no_minor_unit():
    # Assuming 2 decimal places everywhere would make this 150000 -- 100x wrong.
    assert Money.from_major("1500", "JPY").minor_units == 1500


def test_kwd_has_three_minor_units():
    assert Money.from_major("1.234", "KWD").minor_units == 1234


def test_unknown_currency_is_rejected_not_guessed():
    with pytest.raises(MoneyError, match="Unsupported currency"):
        Money.from_major("10", "XYZ")


def test_bool_is_not_an_int():
    with pytest.raises(MoneyError):
        Money(True, "INR")


# ----------------------------------------------------------- the original bug

def test_float_drift_does_not_occur():
    """The bug that motivated this module.

    Note: not every float sum drifts -- ten 0.10s happens to round back to
    exactly 1.0, which is precisely what makes this class of bug so dangerous.
    It passes in casual testing and fails on real data. 0.70 three times does
    drift, and so does a realistic refund ledger (see the test below).
    """
    assert sum(0.70 for _ in range(3)) != 2.10      # the old behaviour

    money_total = sum(
        (Money.from_major("0.70", "INR") for _ in range(3)),
        Money.zero("INR"),
    )
    assert money_total == Money.from_major("2.10", "INR")
    assert money_total.minor_units == 210


def test_large_ledger_sum_stays_exact():
    """10,000 refunds of Rs 19.99 -- the scale a real merchant actually hits.

    As floats this sums to 199899.99999999997. That is the number that would
    not match the courier's remittance statement, with no traceable cause.
    """
    assert sum(19.99 for _ in range(10_000)) != 199_900.0    # the old behaviour

    entries = [Money.from_major("19.99", "INR")] * 10_000
    total = sum(entries, Money.zero("INR"))
    assert total.minor_units == 19_990_000
    assert total.to_major() == Decimal("199900.00")


# ----------------------------------------------------------------- arithmetic

def test_currency_mismatch_is_refused():
    with pytest.raises(CurrencyMismatch):
        Money.from_major("10", "INR") + Money.from_major("10", "USD")


def test_subtraction_can_go_negative():
    # Discrepancy amounts in remittance reconciliation are legitimately negative.
    result = Money.from_major("100", "INR") - Money.from_major("150", "INR")
    assert result.minor_units == -5000        # -5000 paise == -Rs 50.00
    assert result.format() == "-\u20b950.00"


def test_multiply_by_decimal_rate():
    gst = Money.from_major("1000", "INR") * Decimal("0.18")
    assert gst.minor_units == 18000


def test_multiply_by_float_is_refused():
    with pytest.raises(MoneyError, match="float"):
        Money.from_major("1000", "INR") * 0.18


def test_multiplication_rounds_half_up():
    # 0.005 exactly -- banker's rounding would give 0, half-up gives 1 paisa.
    assert (Money(1, "INR") * Decimal("0.5")).minor_units == 1


# ------------------------------------------------------------------ allocate

def test_allocate_loses_no_paise():
    """Rs 10.00 split three ways must still be Rs 10.00."""
    parts = Money.from_major("10.00", "INR").allocate([1, 1, 1])
    assert [p.minor_units for p in parts] == [334, 333, 333]
    assert sum(p.minor_units for p in parts) == 1000


def test_allocate_by_uneven_weights():
    parts = Money.from_major("100.00", "INR").allocate([70, 20, 10])
    assert sum(p.minor_units for p in parts) == 10_000
    assert parts[0].minor_units == 7000


def test_allocate_negative_amount_still_balances():
    parts = Money.from_major("-10.00", "INR").allocate([1, 1, 1])
    assert sum(p.minor_units for p in parts) == -1000


def test_allocate_rejects_empty_weights():
    with pytest.raises(MoneyError):
        Money.from_major("10", "INR").allocate([])


# ---------------------------------------------------------------- formatting

def test_indian_formatting():
    assert Money.from_major("1500.50", "INR").format() == "\u20b91,500.50"


def test_jpy_formats_without_decimals():
    assert Money.from_major("1500", "JPY").format() == "\u00a51,500"


def test_as_dict_wire_format():
    d = Money.from_major("1500.50", "INR").as_dict()
    assert d == {
        "minor_units": 150050,
        "currency": "INR",
        "amount": "1500.50",
        "formatted": "\u20b91,500.50",
    }


# ------------------------------------------------------------------ semantics

def test_money_is_immutable():
    m = Money.from_major("10", "INR")
    with pytest.raises(Exception):
        m.minor_units = 999


def test_money_is_hashable():
    assert len({Money(100, "INR"), Money(100, "INR"), Money(200, "INR")}) == 2


def test_comparison_across_currencies_is_refused():
    with pytest.raises(CurrencyMismatch):
        Money(100, "INR") < Money(100, "USD")
