"""Reconciliation arithmetic tests.

These test the *arithmetic* of remittance reconciliation in isolation, without
a database. The point is to prove the property that matters commercially: our
total must equal the courier's total, exactly, at merchant scale.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import CurrencyMismatch, Money

DISCREPANCY_TOLERANCE_MINOR = 500  # Rs 5.00


def classify(remitted: Money, expected: Money | None) -> tuple[str, Money | None]:
    """Mirror of remittance_service.reconcile_remittance_line's decision logic."""
    if expected is None:
        return "unmatched_no_expected", None
    discrepancy = remitted - expected
    status = (
        "matched"
        if abs(discrepancy.minor_units) <= DISCREPANCY_TOLERANCE_MINOR
        else "mismatch"
    )
    return status, discrepancy


def test_exact_match_has_zero_discrepancy():
    m = Money.from_major("1499.50", "INR")
    status, disc = classify(m, m)
    assert status == "matched"
    assert disc.is_zero()


def test_courier_short_paid_is_flagged():
    status, disc = classify(
        Money.from_major("1400.00", "INR"), Money.from_major("1499.50", "INR")
    )
    assert status == "mismatch"
    assert disc == Money.from_major("-99.50", "INR")
    assert disc.format() == "-\u20b999.50"


def test_within_tolerance_is_matched():
    status, disc = classify(
        Money.from_major("1495.00", "INR"), Money.from_major("1499.50", "INR")
    )
    assert status == "matched"          # Rs 4.50 short, inside the Rs 5 band
    assert disc.minor_units == -450


def test_just_outside_tolerance_is_mismatch():
    status, _ = classify(
        Money.from_major("1494.49", "INR"), Money.from_major("1499.50", "INR")
    )
    assert status == "mismatch"         # Rs 5.01 short


def test_no_assessment_means_no_guess():
    """If the order was never scored we have no ground truth. Say so rather
    than inventing an expected value."""
    status, disc = classify(Money.from_major("1400.00", "INR"), None)
    assert status == "unmatched_no_expected"
    assert disc is None


def test_cross_currency_line_raises_rather_than_silently_summing():
    with pytest.raises(CurrencyMismatch):
        classify(Money.from_major("1400", "USD"), Money.from_major("1400", "INR"))


# ------------------------------------------------------- the commercial proof

def test_org_wide_total_matches_courier_statement_exactly():
    """5,000 COD orders. Our total must equal the courier's, to the paisa.

    Under the old Float columns this same ledger produced a total that
    disagreed with the courier statement by a fraction of a rupee, with no
    row you could point at as the cause. That is the bug that makes a
    reconciliation product untrustworthy.
    """
    count = 5_000

    exact_total = sum(
        (Money.from_major("1499.50", "INR") for _ in range(count)),
        Money.zero("INR"),
    )
    assert exact_total.minor_units == 149950 * count
    assert exact_total.to_major() == Decimal("7497500.00")

    # Honesty about the float comparison: 1499.50 is exactly representable in
    # binary (it is 2999/2), so summing it 5,000 times does NOT drift. Amounts
    # ending in .50, .25, .75 are all safe. The drift appears for amounts with
    # no exact binary form -- .99, .10, .70 -- which is most real prices.
    assert sum(1499.50 for _ in range(count)) == 7_497_500.0        # no drift
    assert sum(19.99 for _ in range(10_000)) != 199_900.0           # drifts

    # Which is the whole problem: correctness depended on which prices the
    # merchant happened to charge. Integer paise removes the dependency.
    drifting = sum((Money.from_major("19.99", "INR") for _ in range(10_000)),
                   Money.zero("INR"))
    assert drifting.to_major() == Decimal("199900.00")


def test_summing_rounded_subtotals_disagrees_with_grand_total():
    """Why get_summary() sums raw paise, not the per-courier rounded outputs.

    Three couriers each owed a third of Rs 100.00. Round each subtotal to
    rupees and add them and you get Rs 99.99, not Rs 100.00 -- a total that
    contradicts its own breakdown on screen.
    """
    total = Money.from_major("100.00", "INR")
    parts = total.allocate([1, 1, 1])

    assert sum(p.minor_units for p in parts) == total.minor_units      # exact
    assert [p.format() for p in parts] == ["\u20b933.34", "\u20b933.33", "\u20b933.33"]

    # Rounding each subtotal to whole rupees before adding loses a rupee:
    # the breakdown would read 33 + 33 + 33 = 99 against a stated total of 100.
    assert sum(round(p.to_major()) for p in parts) == 99
    assert total.to_major() == Decimal("100.00")
