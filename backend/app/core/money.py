"""Exact monetary arithmetic for ReturnIQ.

WHY THIS EXISTS
---------------
Every money column in ReturnIQ was previously a SQL ``Float``. Binary floating
point cannot represent 0.10 exactly, so refunds, remittances and recovery values
accumulated silent drift. In a reconciliation product that is not a rounding
nit: it means our remittance figure and the courier's remittance figure diverge
and nobody can explain the delta.

THE RULE
--------
Money is stored as an **integer count of minor units** (paise, cents, fils)
alongside an explicit **ISO-4217 currency code**. It is never stored as a float,
never as a bare number without a currency, and currency is never encoded in a
column name (``predicted_cost_inr`` was wrong -- it makes Phase 43 globalisation
a full-schema migration).

All arithmetic happens on ``int``. ``Decimal`` is used only at the boundaries
(parsing human input, formatting for display), never for storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Final

__all__ = ["Money", "Currency", "MoneyError", "CurrencyMismatch", "MINOR_UNITS"]


class MoneyError(ValueError):
    """Base class for all monetary errors."""


class CurrencyMismatch(MoneyError):
    """Raised when arithmetic is attempted across two different currencies."""


# ISO-4217 exponent: how many minor units make one major unit.
# Deliberately explicit rather than assuming 2 everywhere -- JPY has 0, and
# assuming 2 would inflate every yen amount by 100x.
MINOR_UNITS: Final[dict[str, int]] = {
    "INR": 2,   # paise
    "USD": 2,   # cents
    "EUR": 2,
    "GBP": 2,
    "AED": 2,   # fils
    "JPY": 0,   # no minor unit
    "KWD": 3,   # fils, three places
    "BHD": 3,
    "OMR": 3,
}

# Symbols are presentation only. Never used for storage or comparison.
_SYMBOLS: Final[dict[str, str]] = {
    "INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3",
    "AED": "AED ", "JPY": "\u00a5", "KWD": "KD ", "BHD": "BD ", "OMR": "OMR ",
}

Currency = str


def _validate_currency(code: str) -> str:
    if not isinstance(code, str):
        raise MoneyError(f"Currency must be a string, got {type(code).__name__}")
    up = code.upper()
    if up not in MINOR_UNITS:
        raise MoneyError(
            f"Unsupported currency {code!r}. Add it to MINOR_UNITS with the "
            f"correct ISO-4217 exponent before using it -- guessing the exponent "
            f"corrupts every amount in that currency."
        )
    return up


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact monetary amount.

    ``minor_units`` is the canonical value. ``Money(150000, "INR")`` is
    Rs 1,500.00. Instances are immutable and hashable, so they are safe to use
    as dict keys and to pass around without defensive copying.
    """

    minor_units: int
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.minor_units, bool) or not isinstance(self.minor_units, int):
            raise MoneyError(
                f"minor_units must be an int, got {type(self.minor_units).__name__}. "
                f"If you have a float, use Money.from_major() or Money.from_float()."
            )
        object.__setattr__(self, "currency", _validate_currency(self.currency))

    # ---------------------------------------------------------------- builders

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(0, currency)

    @classmethod
    def from_major(cls, amount: str | int | Decimal, currency: Currency) -> Money:
        """Build from a major-unit amount, e.g. ``"1500.50"`` -> 150050 paise.

        Accepts ``str``/``int``/``Decimal``. Rejects ``float`` deliberately: the
        moment you write ``0.1 + 0.2`` the value is already wrong, and accepting
        it here would launder that error into the database. Use
        :meth:`from_float` if you have a float from an external system and have
        accepted the precision risk.
        """
        cur = _validate_currency(currency)
        if isinstance(amount, float):
            raise MoneyError(
                "from_major() rejects float to prevent silent precision loss. "
                "Pass a str/Decimal, or use Money.from_float() if the value came "
                "from an external API you do not control."
            )
        try:
            dec = Decimal(amount)
        except (InvalidOperation, TypeError) as exc:
            raise MoneyError(f"Cannot parse {amount!r} as a monetary amount") from exc
        if not dec.is_finite():
            raise MoneyError(f"Monetary amount must be finite, got {amount!r}")

        exponent = MINOR_UNITS[cur]
        scaled = dec.scaleb(exponent).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(int(scaled), cur)

    @classmethod
    def from_float(cls, amount: float, currency: Currency) -> Money:
        """Escape hatch for values arriving from external systems as floats.

        Rounds half-up to the currency's precision at the boundary, which is the
        only safe place to do it. Logged as a distinct entry point so these call
        sites stay greppable -- each one is a place where an upstream system is
        handing us imprecise money.
        """
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise MoneyError(f"Expected a number, got {type(amount).__name__}")
        return cls.from_major(Decimal(str(amount)), currency)

    # ------------------------------------------------------------- conversions

    def to_major(self) -> Decimal:
        """Exact major-unit value as a Decimal. For display and export only."""
        return Decimal(self.minor_units).scaleb(-MINOR_UNITS[self.currency])

    def format(self, *, symbol: bool = True, grouping: bool = True) -> str:
        """Human-readable string. Presentation only -- never parse this back."""
        exponent = MINOR_UNITS[self.currency]
        negative = self.minor_units < 0
        whole = abs(self.to_major())
        text = f"{whole:,.{exponent}f}" if grouping else f"{whole:.{exponent}f}"
        prefix = _SYMBOLS.get(self.currency, self.currency + " ") if symbol else ""
        return f"{'-' if negative else ''}{prefix}{text}"

    def as_dict(self) -> dict[str, Any]:
        """Wire format for the API. Sends both the exact value and a rendered
        string, so clients never have to reimplement currency exponents."""
        return {
            "minor_units": self.minor_units,
            "currency": self.currency,
            "amount": str(self.to_major()),
            "formatted": self.format(),
        }

    # -------------------------------------------------------------- arithmetic

    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise MoneyError(f"Cannot combine Money with {type(other).__name__}")
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"Refusing to combine {self.currency} with {other.currency}. "
                f"Convert explicitly with a dated FX rate -- implicit conversion "
                f"hides which rate was used and when."
            )

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor_units + other.minor_units, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor_units - other.minor_units, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.minor_units, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.minor_units), self.currency)

    def __mul__(self, factor: int | Decimal | str) -> Money:
        """Multiply by a scalar (quantity, tax rate, percentage).

        Floats are rejected for the same reason as in :meth:`from_major`.
        Rounds half-up to the nearest minor unit.
        """
        if isinstance(factor, float):
            raise MoneyError(
                "Refusing to multiply Money by float. Pass a Decimal or str, "
                "e.g. money * Decimal('0.18') for 18% GST."
            )
        if isinstance(factor, bool) or not isinstance(factor, (int, Decimal, str)):
            raise MoneyError(f"Cannot multiply Money by {type(factor).__name__}")
        dec = Decimal(factor) if not isinstance(factor, Decimal) else factor
        scaled = (Decimal(self.minor_units) * dec).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return Money(int(scaled), self.currency)

    __rmul__ = __mul__

    def allocate(self, weights: list[int]) -> list[Money]:
        """Split an amount across weights with **no lost or invented paise**.

        The classic failure: splitting Rs 10.00 three ways gives 3.33 + 3.33 +
        3.33 = 9.99, and one paisa vanishes. This distributes remainders
        largest-first so the parts always sum exactly back to the original.
        Used for splitting a refund across order lines, or a courier remittance
        across the returns it covers.
        """
        if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
            raise MoneyError("allocate() needs at least one positive weight")

        total_weight = sum(weights)
        shares = [self.minor_units * w // total_weight for w in weights]
        remainder = self.minor_units - sum(shares)

        # Hand out the remaining units to the largest fractional parts first.
        order = sorted(
            range(len(weights)),
            key=lambda i: (self.minor_units * weights[i]) % total_weight,
            reverse=True,
        )
        step = 1 if remainder >= 0 else -1
        for i in range(abs(remainder)):
            shares[order[i % len(order)]] += step

        parts = [Money(s, self.currency) for s in shares]
        assert sum(p.minor_units for p in parts) == self.minor_units
        return parts

    # ------------------------------------------------------------- comparisons

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.minor_units < other.minor_units

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.minor_units <= other.minor_units

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.minor_units > other.minor_units

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.minor_units >= other.minor_units

    def is_zero(self) -> bool:
        return self.minor_units == 0

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Money({self.minor_units}, {self.currency!r})  # {self.format()}"
