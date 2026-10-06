"""PHASE 25 — counterfactual decision view.

THE INSTRUCTION
---------------
> Repair    Expected value: Rs 1,550
> Restock   Expected value: Rs 1,050
> Difference: +Rs 500
> "This makes the recommendation understandable."

Phase 24 already returns every option with its value and range, so the
comparison itself is done. What is missing is the part that actually makes a
recommendation understandable:

    **What would have to be true for this to be wrong?**

BREAK-EVEN, NOT JUST DIFFERENCE
-------------------------------
"Repair is worth Rs 500 more" invites one question a warehouse manager cannot
answer from that sentence: *how sure are we?*

"Repair beats restock only if repairs succeed at least 63% of the time; we
estimate 70%, and our uncertainty on that figure is +/-15 points" is a
different kind of statement. The manager knows their own repair bench. They
can look at that 63% and say "ours run about half" — and overrule the system
correctly, using knowledge the system does not have.

That is the real value of a counterfactual view. Not explaining the answer;
exposing the assumption the answer rests on, so a human with better
information can catch it.

WHY THIS MATTERS MORE HERE THAN ELSEWHERE
-----------------------------------------
Phase 24's inputs are probabilities from a model trained on synthetic data. A
break-even threshold does not depend on that model being right — it is
arithmetic on the merchant's own costs and recoveries. So it stays useful even
while the probabilities do not, which makes it the most trustworthy output
this system currently produces.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.money import Money
from app.services.decision_engine import (
    LABELS,
    DecisionResult,
    DispositionInputs,
    evaluate_dispositions,
)

__all__ = ["Comparison", "BreakEven", "compare_to_alternative", "counterfactual_view"]


@dataclass(frozen=True)
class BreakEven:
    """The success rate at which two options become equal."""

    threshold: float | None
    current_estimate: float
    uncertainty: float
    reachable: bool
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "break_even_probability": (
                round(self.threshold, 4) if self.threshold is not None else None
            ),
            "current_estimate": round(self.current_estimate, 4),
            "uncertainty": round(self.uncertainty, 4),
            "within_uncertainty": self.reachable,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class Comparison:
    chosen: str
    alternative: str
    difference: Money
    ranges_overlap: bool
    break_even: BreakEven | None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "chosen": self.chosen,
            "chosen_label": LABELS.get(self.chosen, self.chosen),
            "alternative": self.alternative,
            "alternative_label": LABELS.get(self.alternative, self.alternative),
            "difference": self.difference.as_dict(),
            "ranges_overlap": self.ranges_overlap,
        }
        if self.break_even:
            payload["sensitivity"] = self.break_even.as_dict()
        return payload


def _break_even_probability(
    chosen: DispositionInputs,
    alternative_value: Money,
) -> float | None:
    """The success rate at which `chosen` stops beating the alternative.

    Solving:  recovery x p - costs - time = alternative_value
              p = (alternative_value + costs + time) / recovery

    Returns None when recovery is zero — an option that recovers nothing has
    no success rate to trade off, and reporting a threshold there would be
    dividing by nothing to produce a number that means nothing.
    """
    if chosen.recovery.minor_units == 0:
        return None

    from app.services.decision_engine import _time_cost

    costs = chosen.processing_cost + chosen.logistics_cost
    time_cost = _time_cost(chosen.recovery, chosen.days_to_realise)
    required = alternative_value + costs + time_cost

    return required.minor_units / chosen.recovery.minor_units


def compare_to_alternative(
    options: list[DispositionInputs],
    result: DecisionResult,
    chosen_key: str,
    alternative_key: str,
) -> Comparison:
    """Compare two specific options, with the assumption exposed."""
    by_key = {o.disposition: o for o in options}
    outcomes = {o.disposition: o for o in result.outcomes}

    chosen_spec = by_key[chosen_key]
    chosen_outcome = outcomes[chosen_key]
    alternative_outcome = outcomes[alternative_key]

    difference = chosen_outcome.expected_value - alternative_outcome.expected_value
    overlap = chosen_outcome.overlaps(alternative_outcome)

    threshold = _break_even_probability(
        chosen_spec, alternative_outcome.expected_value
    )

    if threshold is None:
        break_even = BreakEven(
            threshold=None,
            current_estimate=chosen_spec.success_probability,
            uncertainty=chosen_spec.probability_spread,
            reachable=False,
            explanation=(
                f"{LABELS.get(chosen_key, chosen_key)} recovers nothing, so "
                f"there is no success rate to trade off — the comparison rests "
                f"entirely on cost."
            ),
        )
    elif threshold > 1.0:
        break_even = BreakEven(
            threshold=threshold,
            current_estimate=chosen_spec.success_probability,
            uncertainty=chosen_spec.probability_spread,
            reachable=False,
            explanation=(
                f"{LABELS.get(chosen_key, chosen_key)} cannot beat "
                f"{LABELS.get(alternative_key, alternative_key)} at any success "
                f"rate — even if it worked every single time, the costs would "
                f"still put it behind."
            ),
        )
    elif threshold < 0.0:
        break_even = BreakEven(
            threshold=threshold,
            current_estimate=chosen_spec.success_probability,
            uncertainty=chosen_spec.probability_spread,
            reachable=False,
            explanation=(
                f"{LABELS.get(chosen_key, chosen_key)} beats "
                f"{LABELS.get(alternative_key, alternative_key)} even if it "
                f"never succeeds. This one is not a close call."
            ),
        )
    else:
        half = chosen_spec.probability_spread / 2
        low = chosen_spec.success_probability - half
        high = chosen_spec.success_probability + half
        within = low <= threshold <= high

        if within:
            explanation = (
                f"{LABELS.get(chosen_key, chosen_key)} wins only if it succeeds "
                f"at least {threshold:.0%} of the time. We estimate "
                f"{chosen_spec.success_probability:.0%}, but our uncertainty on "
                f"that figure spans {low:.0%}–{high:.0%} — so the threshold sits "
                f"inside the range and this could genuinely go either way. If "
                f"you know your own success rate, use it."
            )
        else:
            margin = chosen_spec.success_probability - threshold
            explanation = (
                f"{LABELS.get(chosen_key, chosen_key)} wins if it succeeds at "
                f"least {threshold:.0%} of the time. We estimate "
                f"{chosen_spec.success_probability:.0%} — "
                f"{abs(margin):.0%} clear of the threshold, and outside our "
                f"uncertainty band, so the ranking holds unless your own rate "
                f"is very different from ours."
            )

        break_even = BreakEven(
            threshold=threshold,
            current_estimate=chosen_spec.success_probability,
            uncertainty=chosen_spec.probability_spread,
            reachable=within,
            explanation=explanation,
        )

    return Comparison(
        chosen=chosen_key,
        alternative=alternative_key,
        difference=difference,
        ranges_overlap=overlap,
        break_even=break_even,
    )


def counterfactual_view(options: list[DispositionInputs]) -> dict[str, Any]:
    """The recommendation, plus what it would take to be wrong.

    Every alternative is compared against the leader, so a manager sees not
    only "why this" but "why not that" for each option they might have
    reached for instead.
    """
    result = evaluate_dispositions(options)
    ranked = result.ranked

    if not ranked:
        return {"recommendation": None, "comparisons": []}

    best = ranked[0]
    comparisons = [
        compare_to_alternative(options, result, best.disposition, other.disposition).as_dict()
        for other in ranked[1:]
    ]

    return {
        **result.as_dict(),
        "comparisons": comparisons,
        "counterfactual_note": (
            "Each comparison shows what would have to be true for the "
            "recommendation to flip. Break-even thresholds are arithmetic on "
            "your own costs and recoveries — they do not depend on the model "
            "being right, so they stay reliable even where the probabilities "
            "are uncertain."
        ),
    }
