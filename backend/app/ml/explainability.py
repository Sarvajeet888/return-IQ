"""PHASE 21 — explainable predictions.

WHAT THE AUDIT FOUND
--------------------
The existing `top_drivers_for_row()` ranks features by
`global_importance x |feature_value|`. Its docstring is honest -- it says
"NOT full SHAP" and "label it as such in any UI/API that surfaces it".

Two problems, both measured rather than assumed.

**1. It does not vary per prediction.** Across 300 randomised returns spanning
Rs 200-90,000, 0.1-25kg and 10-2,500km:

    DISTINCT explanations produced: 6
      140x  [distance_km, product_value, chargeable_weight]
      136x  [distance_km, product_value, volumetric_weight]
      (four others, 5-7x each)

    distance_km ranked #1 in 300/300 cases.

Two orderings cover 92% of all returns. A Rs 90,000 electronics item and a
Rs 1,500 t-shirt receive the identical explanation. That is a *global* feature
ranking wearing a per-prediction label -- it tells a merchant nothing about
*their* return.

**2. The API attaches invented causal narratives.** `ai_ux.py` maps whichever
feature ranked highest onto hardcoded prose:

    "Festive-season returns correlate with bulk purchasing and impulse buying"
    "COD returns carry higher fraud risk and cash reconciliation overhead"

The model knows nothing about impulse buying. These are stories a developer
wrote, presented to merchants as if the model produced them. The roadmap is
explicit: *"Never present explanations as causal proof when they are only
model-attribution signals."*

WHAT THIS MODULE DOES INSTEAD
-----------------------------
The rule-based scores -- fraud, damage, resale, carbon -- are deterministic
arithmetic. They do not need approximation: **their exact contributions can be
computed**, because we wrote the rules. A rule-based score is the one thing in
this system that can be explained perfectly, and it was being explained with
model-style hand-waving.

For the ML cost model, attribution is labelled as attribution, with the
measured caveat that it barely varies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "Contribution",
    "Explanation",
    "explain_rule_score",
    "attribution_caveat",
]

# Applies to every explanation this system produces, model or rule.
CAUSAL_DISCLAIMER: Final[str] = (
    "This shows what moved the score, not why the return happened. These are "
    "the factors the scoring logic weighted — they are associations the system "
    "was configured or trained to use, not established causes."
)

# Measured during Phase 21, attached wherever ML attribution is surfaced.
ML_ATTRIBUTION_CAVEAT: Final[str] = (
    "Model attribution is approximate and, for the current cost model, close "
    "to constant: across 300 varied returns, distance ranked first in every "
    "one and two orderings covered 92% of cases. Treat it as a description of "
    "the model's general behaviour rather than of this particular return."
)


@dataclass(frozen=True)
class Contribution:
    """One factor's exact effect on a rule-based score."""

    factor: str
    points: float
    direction: str          # "increases" | "reduces" | "neutral"
    because: str            # the actual condition that fired

    def as_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "points": round(self.points, 2),
            "direction": self.direction,
            "because": self.because,
        }


@dataclass
class Explanation:
    score_name: str
    score: float
    method: str                     # "exact_rule" | "model_attribution"
    contributions: list[Contribution]
    baseline: float = 0.0

    @property
    def increases(self) -> list[Contribution]:
        return sorted(
            [c for c in self.contributions if c.direction == "increases"],
            key=lambda c: -c.points,
        )

    @property
    def reduces(self) -> list[Contribution]:
        return sorted(
            [c for c in self.contributions if c.direction == "reduces"],
            key=lambda c: c.points,
        )

    def reconciles(self) -> bool:
        """Do the stated contributions actually add up to the score?

        The check that separates an exact explanation from a plausible one. If
        the parts do not sum to the whole, something is unexplained, and an
        explanation with a silent remainder is worse than none — it looks
        complete.
        """
        if self.method != "exact_rule":
            return False
        total = self.baseline + sum(c.points for c in self.contributions)
        return abs(total - self.score) < 0.01

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "score_name": self.score_name,
            "score": round(self.score, 2),
            "method": self.method,
            "increases_score": [c.as_dict() for c in self.increases],
            "reduces_score": [c.as_dict() for c in self.reduces],
            "disclaimer": CAUSAL_DISCLAIMER,
        }
        if self.method == "exact_rule":
            payload["baseline"] = round(self.baseline, 2)
            payload["reconciles"] = self.reconciles()
            payload["method_note"] = (
                "Exact. This score is computed by rules we wrote, so every "
                "point is accounted for — the factors below sum to the score."
            )
        else:
            payload["method_note"] = ML_ATTRIBUTION_CAVEAT
        return payload


def explain_rule_score(
    score_name: str,
    score: float,
    *,
    baseline: float,
    fired: list[tuple[str, float, str]],
) -> Explanation:
    """Build an exact explanation for a rule-based score.

    `fired` is a list of (factor, points, because) for every rule that
    actually triggered. The caller passes what fired because only the scoring
    function knows — the point is that it *can* know, exactly, which is
    precisely what the previous model-style explanation gave up.
    """
    contributions = [
        Contribution(
            factor=factor,
            points=points,
            direction=(
                "increases" if points > 0 else "reduces" if points < 0 else "neutral"
            ),
            because=because,
        )
        for factor, points, because in fired
    ]
    return Explanation(
        score_name=score_name,
        score=score,
        method="exact_rule",
        contributions=contributions,
        baseline=baseline,
    )


def attribution_caveat() -> dict[str, str]:
    """The note that must accompany any ML attribution surfaced to a user."""
    return {
        "method": "model_attribution",
        "caveat": ML_ATTRIBUTION_CAVEAT,
        "disclaimer": CAUSAL_DISCLAIMER,
    }
