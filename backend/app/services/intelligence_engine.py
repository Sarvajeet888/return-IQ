"""PHASE 14 — the Intelligence Engine.

WHAT THIS FIXES
---------------
`score_return()` returns eight numbers in one flat dict. They look alike, they
are formatted alike, and the UI renders them alike. But they are not alike:

    predicted_cost_inr    XGBoost regression on 15 features
    fraud_score           a hand-written rule: += 25 if COD, += 15 if festive
    damage_probability    a lookup table keyed on return_reason
    resale_value_estimate item_value x a multiplier chosen by condition
    carbon_footprint_kg   distance x weight x a courier constant
    confidence_score      arithmetic on risk_score and item_value

A merchant reading "fraud score 82, confidence 0.99" reasonably concludes a
model assessed this customer. One did not. That gap between what the number
implies and what produced it is the thing this module closes.

THE CONFIDENCE FIELD SPECIFICALLY
---------------------------------
The old computation:

    confidence = min(0.85 + (risk_score < 80) * 0.1 + (item_value < 5000) * 0.04, 0.99)

It can take exactly four values: 0.85, 0.89, 0.95, 0.99. It never consults the
model. A Rs 4,999 item reports 0.99 and a Rs 5,001 item reports 0.95 --
a cliff at a round number that means nothing.

Its code comment cited "model R2=0.999". Per `data/DATASET_ASSESSMENT.md`,
that R-squared came from a model trained on 5,000 rows of **synthetic** data
whose labels derive from the generator's own parameters, and the deployed cost
model needs 15 features while the available dataset has 2 with no cost target
column at all. The figure is not just optimistic; it is unverifiable.

Reporting 0.99 confidence on that basis is the single most misleading thing
this system does, because confidence is exactly the number a merchant uses to
decide whether to trust the rest.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not make the predictions better. The model is still trained on
synthetic data; that is fixed by obtaining real returns data, not by writing
code. What it does is stop the system from overstating what it knows, so that
a human reading a recommendation can see which parts rest on a model, which
rest on a rule somebody wrote, and how much any of it should be trusted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "Provenance",
    "Confidence",
    "Signal",
    "IntelligenceReport",
    "build_report",
]


class Provenance:
    """How a number came to exist.

    The distinction the flat dict erased. Presenting a rule's output with the
    same weight as a model's output is how a system ends up trusted for things
    it cannot do -- and distrusted for the things it can.
    """

    ML_MODEL: Final = "ml_model"        # a trained model produced this
    RULE: Final = "rule"                # a hand-written heuristic
    DERIVED: Final = "derived"          # arithmetic on other signals
    OBSERVED: Final = "observed"        # measured fact, not a prediction


class Confidence:
    """Honest confidence bands.

    Bands, not a decimal. A decimal invites false precision: 0.87 implies a
    calibration that does not exist here. Until predictions are validated
    against real outcomes (Phase 19/27), the truthful statement is
    directional, and a band says that out loud.
    """

    HIGH: Final = "high"                # validated against real outcomes
    MODERATE: Final = "moderate"        # deterministic rule, predictable output
    LOW: Final = "low"                  # model trained on unvalidated data
    UNKNOWN: Final = "unknown"          # no basis for a claim


@dataclass(frozen=True)
class Signal:
    """One number, plus everything needed to judge it."""

    name: str
    value: Any
    provenance: str
    confidence: str
    basis: str                          # plain-English: what produced this
    caveat: str | None = None           # what would make it wrong

    def as_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "value": self.value,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "basis": self.basis,
        }
        if self.caveat:
            out["caveat"] = self.caveat
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Signal descriptions. One place stating what each number really is.
# ─────────────────────────────────────────────────────────────────────────────

# The cost model is the only signal produced by a trained model. Its confidence
# is LOW rather than HIGH, and that is the honest reading: the reported
# R2=0.9993 comes from synthetic data whose labels derive from the generator's
# own parameters. Feature importances put distance_km at ~92%, which makes it
# functionally a courier pricing calculator rather than returns intelligence.
_SIGNAL_SPEC: Final[dict[str, dict[str, str]]] = {
    "predicted_cost": {
        "provenance": Provenance.ML_MODEL,
        "confidence": Confidence.LOW,
        "basis": "XGBoost regression over 15 features (cost_xgb_v1.0.0).",
        "caveat": (
            "Trained on synthetic data. The reported R2 is not validated "
            "against real returns, and distance dominates the model's feature "
            "importances -- treat this as an estimate of shipping cost rather "
            "than of total return cost."
        ),
    },
    "fraud_score": {
        "provenance": Provenance.RULE,
        "confidence": Confidence.MODERATE,
        "basis": (
            "Hand-written scoring rules over payment mode, return reason, "
            "item value and customer return rate."
        ),
        "caveat": (
            "Not a trained fraud model. It reflects the judgement of whoever "
            "chose the weights, and has not been benchmarked against confirmed "
            "fraud cases."
        ),
    },
    "damage_probability": {
        "provenance": Provenance.RULE,
        "confidence": Confidence.MODERATE,
        "basis": "Lookup table on return reason, declared condition and fragility.",
        "caveat": (
            "Derived from what the customer stated, not from inspecting the "
            "item or its photographs."
        ),
    },
    "resale_value": {
        "provenance": Provenance.DERIVED,
        "confidence": Confidence.MODERATE,
        "basis": "Item value scaled by a category and condition multiplier.",
        "caveat": "Multipliers are assumptions, not observed resale outcomes.",
    },
    "carbon_footprint_kg": {
        "provenance": Provenance.DERIVED,
        "confidence": Confidence.MODERATE,
        "basis": "Distance x chargeable weight x a per-courier emissions constant.",
        "caveat": "Emissions constants are industry averages, not courier-reported figures.",
    },
    "risk_score": {
        "provenance": Provenance.DERIVED,
        "confidence": Confidence.MODERATE,
        "basis": (
            "Weighted blend of cost-to-value ratio, customer return rate and "
            "merchant return rate."
        ),
        "caveat": "Inherits the cost model's uncertainty through cost-to-value ratio.",
    },
}


@dataclass
class IntelligenceReport:
    """Everything known about one return, with each claim's basis attached."""

    return_id: str | None
    signals: list[Signal] = field(default_factory=list)
    model_version: str = "unknown"

    def get(self, name: str) -> Signal | None:
        return next((s for s in self.signals if s.name == name), None)

    @property
    def overall_confidence(self) -> str:
        """The weakest link, not the average.

        Averaging would let four MODERATE rules mask one LOW model output that
        the recommendation actually depends on. A chain is as strong as its
        weakest link, and a recommendation is as trustworthy as its shakiest
        input.
        """
        levels = {s.confidence for s in self.signals}
        for level in (Confidence.UNKNOWN, Confidence.LOW,
                      Confidence.MODERATE, Confidence.HIGH):
            if level in levels:
                return level
        return Confidence.UNKNOWN

    @property
    def requires_human_review(self) -> bool:
        """Low or unknown confidence goes to a person.

        Phase 26 makes this configurable per organization. The default is
        conservative because the current default state -- a model on synthetic
        data -- should not be auto-approving anything involving money.
        """
        return self.overall_confidence in (Confidence.LOW, Confidence.UNKNOWN)

    def as_dict(self) -> dict[str, Any]:
        return {
            "return_id": self.return_id,
            "model_version": self.model_version,
            "overall_confidence": self.overall_confidence,
            "requires_human_review": self.requires_human_review,
            "signals": [s.as_dict() for s in self.signals],
            "disclosure": (
                "Signals are labelled by how they were produced. 'ml_model' "
                "means a trained model; 'rule' means a hand-written heuristic; "
                "'derived' means arithmetic over other signals. Confidence "
                "reflects how well each has been validated against real "
                "outcomes, not how certain the number looks."
            ),
        }


def build_report(
    scoring_result: dict[str, Any],
    return_id: str | None = None,
) -> IntelligenceReport:
    """Turn a flat `score_return()` result into a labelled report.

    Deliberately additive. The existing keys keep working for every current
    caller; this sits alongside them rather than replacing the shape and
    forcing a rewrite of the frontend in the same change.
    """
    value_keys = {
        "predicted_cost": "predicted_cost_inr",
        "fraud_score": "fraud_score",
        "damage_probability": "damage_probability",
        "resale_value": "resale_value_estimate",
        "carbon_footprint_kg": "carbon_footprint_kg",
        "risk_score": "risk_score",
    }

    signals: list[Signal] = []
    for name, spec in _SIGNAL_SPEC.items():
        raw = scoring_result.get(value_keys[name])
        if raw is None:
            continue
        signals.append(Signal(
            name=name,
            # Decimal is not JSON-serialisable and float() at the boundary is
            # safe here: these are scores for display, not money. Monetary
            # values keep their exact integer representation elsewhere.
            value=float(raw),
            provenance=spec["provenance"],
            confidence=spec["confidence"],
            basis=spec["basis"],
            caveat=spec.get("caveat"),
        ))

    return IntelligenceReport(
        return_id=return_id,
        signals=signals,
        model_version=str(scoring_result.get("model_version", "unknown")),
    )
