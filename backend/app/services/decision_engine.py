"""PHASE 24 — decision optimisation.

THE INSTRUCTION
---------------
For each possible action, calculate expected recovery minus processing cost,
logistics cost, risk and time cost. Then recommend the highest net value:

    Restock:   Rs 1,050
    Repair:    Rs 1,550
    Resell:    Rs 1,200
    Liquidate: Rs   620
    -> Recommendation: Repair

THE PROBLEM WITH THAT TABLE
---------------------------
It presents four numbers to two decimal places of implied confidence, and
every one of them is a probability multiplied by a cost. Phase 18 measured why
that matters: a model saying 0.9 when the truth is 0.3 makes the *economics*
wrong by 3x, not merely the score. Phase 20 measured the spread — the current
cost model's intervals are wide.

So the honest version of the table above is often:

    Repair:    Rs 1,550   (range Rs   900 - Rs 2,200)
    Restock:   Rs 1,050   (range Rs   700 - Rs 1,400)
    -> These overlap. On the evidence available, they are not distinguishable.

Recommending "Repair" there is false precision, and it costs real money:
repair has staff time and a failure rate, restock does not. A merchant told
"Repair, +Rs 500" will do it, and the Rs 500 was never there.

WHAT THIS MODULE DOES
---------------------
Computes the economics exactly (integer paise, Phase 3), propagates the
uncertainty of every input, and **declines to rank options whose intervals
overlap**. Same principle as the Phase 18 benchmark refusing to crown a winner
within noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from app.core.money import Money

__all__ = [
    "Disposition",
    "DispositionInputs",
    "DispositionOutcome",
    "DecisionResult",
    "evaluate_dispositions",
]


class Disposition:
    RESTOCK: Final = "restock"
    REPAIR: Final = "repair"
    RESELL: Final = "resell"
    REFURBISH: Final = "refurbish"
    LIQUIDATE: Final = "liquidate"
    RECYCLE: Final = "recycle"
    DISPOSE: Final = "dispose"


ALL_DISPOSITIONS: Final[tuple[str, ...]] = (
    Disposition.RESTOCK, Disposition.REPAIR, Disposition.RESELL,
    Disposition.REFURBISH, Disposition.LIQUIDATE, Disposition.RECYCLE,
    Disposition.DISPOSE,
)

# Human-readable, for the recommendation shown to a warehouse manager.
LABELS: Final[dict[str, str]] = {
    Disposition.RESTOCK: "Return to sellable stock",
    Disposition.REPAIR: "Repair, then restock",
    Disposition.RESELL: "Sell as open-box",
    Disposition.REFURBISH: "Refurbish and sell as refurbished",
    Disposition.LIQUIDATE: "Sell to a liquidator in bulk",
    Disposition.RECYCLE: "Send for materials recovery",
    Disposition.DISPOSE: "Scrap",
}


@dataclass(frozen=True)
class DispositionInputs:
    """Everything needed to price one option.

    Probabilities carry an explicit uncertainty band rather than a point
    value. That is the whole design: `success_probability=0.7` with
    `probability_spread=0.3` says "somewhere between 0.55 and 0.85", which is
    what the current models actually support.
    """

    disposition: str
    # Value recovered if this option succeeds.
    recovery: Money
    # Chance it succeeds at all. Repair fails; liquidation does not.
    success_probability: float
    # How uncertain that probability is. 0.0 means known exactly, which is
    # true for `dispose` and almost nothing else.
    probability_spread: float
    # Costs incurred whether or not it succeeds.
    processing_cost: Money
    logistics_cost: Money
    # Working capital tied up while this option plays out.
    days_to_realise: int
    # Uncertainty on the recovery figure itself, as a fraction.
    recovery_spread: float = 0.0

    def validate(self) -> None:
        if not 0.0 <= self.success_probability <= 1.0:
            raise ValueError(
                f"{self.disposition}: success_probability must be in [0, 1]"
            )
        if self.probability_spread < 0 or self.recovery_spread < 0:
            raise ValueError(f"{self.disposition}: spreads cannot be negative")
        for cost in (self.recovery, self.processing_cost, self.logistics_cost):
            if cost.currency != self.recovery.currency:
                raise ValueError(f"{self.disposition}: mixed currencies")


# Cost of capital, annualised. Applied to the recovery value over the days it
# takes to realise, because Rs 1,000 recovered in 90 days is not worth Rs 1,000
# today — and liquidation's whole appeal is that it is fast.
ANNUAL_CAPITAL_COST: Final[Decimal] = Decimal("0.14")


@dataclass(frozen=True)
class DispositionOutcome:
    disposition: str
    expected_value: Money
    lower: Money
    upper: Money
    recovery_if_successful: Money
    total_cost: Money
    success_probability: float
    time_cost: Money
    days_to_realise: int

    @property
    def is_uncertain(self) -> bool:
        """Is the range wide relative to the estimate?"""
        if self.expected_value.minor_units == 0:
            return self.upper.minor_units != self.lower.minor_units
        span = self.upper.minor_units - self.lower.minor_units
        return abs(span) > abs(self.expected_value.minor_units) * 0.5

    def overlaps(self, other: DispositionOutcome) -> bool:
        return not (
            self.lower.minor_units > other.upper.minor_units
            or other.lower.minor_units > self.upper.minor_units
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "label": LABELS.get(self.disposition, self.disposition),
            "expected_value": self.expected_value.as_dict(),
            "range_low": self.lower.as_dict(),
            "range_high": self.upper.as_dict(),
            "recovery_if_successful": self.recovery_if_successful.as_dict(),
            "total_cost": self.total_cost.as_dict(),
            "success_probability": round(self.success_probability, 3),
            "time_cost": self.time_cost.as_dict(),
            "days_to_realise": self.days_to_realise,
            "uncertain": self.is_uncertain,
        }


@dataclass
class DecisionResult:
    outcomes: list[DispositionOutcome] = field(default_factory=list)
    currency: str = "INR"

    @property
    def ranked(self) -> list[DispositionOutcome]:
        return sorted(
            self.outcomes, key=lambda o: o.expected_value.minor_units, reverse=True
        )

    @property
    def indistinguishable(self) -> list[DispositionOutcome]:
        """Options whose ranges overlap the leader's.

        These cannot be separated on the evidence available. Presenting a
        winner among them is false precision — and in this domain false
        precision spends money, because the recommended action has real costs
        the alternative does not.
        """
        ranked = self.ranked
        if not ranked:
            return []
        best = ranked[0]
        return [o for o in ranked if o is not best and best.overlaps(o)]

    def as_dict(self) -> dict[str, Any]:
        ranked = self.ranked
        if not ranked:
            return {"recommendation": None, "reason": "No options were evaluated."}

        best = ranked[0]
        tied = self.indistinguishable

        if tied:
            names = ", ".join(LABELS.get(o.disposition, o.disposition) for o in tied)
            recommendation = {
                "disposition": best.disposition,
                "label": LABELS.get(best.disposition, best.disposition),
                "confidence": "low",
                "reason": (
                    f"{LABELS.get(best.disposition, best.disposition)} has the "
                    f"highest expected value at {best.expected_value.format()}, "
                    f"but its range overlaps with: {names}. On the evidence "
                    f"available these options are not distinguishable — treat "
                    f"this as a starting point, not an answer."
                ),
                "indistinguishable_from": [o.disposition for o in tied],
            }
        else:
            runner_up = ranked[1] if len(ranked) > 1 else None
            margin = (
                best.expected_value - runner_up.expected_value
                if runner_up else best.expected_value
            )
            recommendation = {
                "disposition": best.disposition,
                "label": LABELS.get(best.disposition, best.disposition),
                "confidence": "high",
                "reason": (
                    f"{LABELS.get(best.disposition, best.disposition)} is worth "
                    f"{best.expected_value.format()}"
                    + (
                        f", clear of {LABELS.get(runner_up.disposition, '')} by "
                        f"{margin.format()} even at the edges of both ranges."
                        if runner_up else "."
                    )
                ),
                "margin_over_next": margin.as_dict(),
            }

        return {
            "recommendation": recommendation,
            "options": [o.as_dict() for o in ranked],
            "note": (
                "Expected values are probabilities multiplied by amounts. Where "
                "the probability is uncertain, so is the money — the ranges "
                "shown carry that through rather than hiding it behind a point "
                "estimate."
            ),
        }


def _time_cost(recovery: Money, days: int) -> Money:
    """Working capital tied up while an option plays out.

    Liquidation recovers less but recovers it next week; repair recovers more
    in six weeks. Without this term the model systematically over-recommends
    slow options, because it counts their higher recovery and ignores that the
    money is not available.
    """
    if days <= 0:
        return Money.zero(recovery.currency)
    daily = ANNUAL_CAPITAL_COST / Decimal(365)
    return recovery * (daily * Decimal(days))


def evaluate_dispositions(inputs: list[DispositionInputs]) -> DecisionResult:
    """Price every option, with its uncertainty carried through.

    Expected value = (recovery x P(success)) - processing - logistics - time.

    Costs are subtracted unconditionally, and that is deliberate: a repair
    that fails still consumed the technician's hour. Modelling costs as
    probability-weighted would flatter every risky option.
    """
    if not inputs:
        return DecisionResult()

    outcomes: list[DispositionOutcome] = []

    for spec in inputs:
        spec.validate()
        currency = spec.recovery.currency

        total_cost = spec.processing_cost + spec.logistics_cost
        time_cost = _time_cost(spec.recovery, spec.days_to_realise)

        def net(probability: float, recovery_factor: Decimal) -> Money:
            probability = min(max(probability, 0.0), 1.0)
            gross = (spec.recovery * recovery_factor) * Decimal(str(probability))
            return gross - total_cost - time_cost

        expected = net(spec.success_probability, Decimal("1"))

        # The pessimistic and optimistic corners: probability and recovery
        # both at the unfavourable end, then both at the favourable end.
        # Correlated rather than independent on purpose -- when a cost model
        # is wrong it tends to be wrong in one direction across a whole
        # category, not to cancel out.
        low = net(
            spec.success_probability - spec.probability_spread / 2,
            Decimal("1") - Decimal(str(spec.recovery_spread)) / 2,
        )
        high = net(
            spec.success_probability + spec.probability_spread / 2,
            Decimal("1") + Decimal(str(spec.recovery_spread)) / 2,
        )

        outcomes.append(DispositionOutcome(
            disposition=spec.disposition,
            expected_value=expected,
            lower=min(low, high),
            upper=max(low, high),
            recovery_if_successful=spec.recovery,
            total_cost=total_cost,
            success_probability=spec.success_probability,
            time_cost=time_cost,
            days_to_realise=spec.days_to_realise,
        ))

    return DecisionResult(outcomes=outcomes, currency=inputs[0].recovery.currency)
