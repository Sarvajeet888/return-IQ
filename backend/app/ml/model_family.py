"""PHASE 17 — the model family.

WHAT THIS IS
------------
Nine model *specifications*, not nine trained models. Each declares what it
predicts, which features it may use, what task it is, which metric decides
whether it is any good, and what data volume it needs before training is
defensible.

WHY SPECIFICATIONS FIRST
------------------------
The roadmap's Phase 17 instruction is "do NOT use one giant model". Today
ReturnIQ has one XGBoost regressor whose output is reused, reshaped and
relabelled into six different numbers on screen. Splitting that into nine
models is an architectural change, and the architecture can be built and
tested before any of them can be trained.

The measured position (see PHASE_17_FEASIBILITY.md): eight of the nine have no
target column in the available data, and the ninth trains to ROC-AUC 0.556
against an oracle ceiling of 0.754. So the honest deliverable is the structure
that turns "train Model C" into a config change the day real data exists,
rather than a rewrite.

WHAT THIS DELIBERATELY PREVENTS
-------------------------------
Every spec carries `min_labelled_rows` and a forbidden-feature list. A model
cannot be trained by bypassing them, because the harness reads the spec rather
than accepting arguments. That is the difference between a guard rail and a
comment asking people to be careful.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "TaskType",
    "ModelSpec",
    "MODEL_FAMILY",
    "get_spec",
    "readiness",
    "family_status",
]


class TaskType:
    REGRESSION: Final = "regression"
    BINARY: Final = "binary_classification"
    MULTICLASS: Final = "multiclass_classification"


# Features shared by every model. Deliberately excludes anything about the
# outcome — those live in each spec's `forbidden_features` where they are
# specific, and in dataset_builder.LEAKY_FEATURES globally.
_BASE_FEATURES: Final[list[str]] = [
    "product_value", "actual_weight", "volumetric_weight", "chargeable_weight",
    "courier", "category", "payment_mode", "return_reason",
    "pickup_tier", "destination_tier", "distance_km", "fragile", "festive",
]

# Point-in-time features from Phase 16. Safe for every model because
# feature_engineering computes them with an `as_of` cutoff.
_HISTORY_FEATURES: Final[list[str]] = [
    "customer_return_count", "customer_return_ratio",
    "customer_days_since_last_return", "customer_returns_last_30d",
    "customer_returns_last_90d", "customer_is_first_return",
    "customer_avg_days_between_returns",
    "sku_return_count", "sku_damage_rate", "sku_is_first_return",
    "day_of_week", "is_weekend", "month", "quarter", "is_festive_window",
]

_EVIDENCE_FEATURES: Final[list[str]] = [
    "evidence_count", "has_evidence", "damage_photo_count",
    "customer_evidence_count", "damage_claimed_without_photo",
    "days_since_delivery",
]


@dataclass(frozen=True)
class ModelSpec:
    """One model in the family."""

    key: str
    name: str
    task: str
    target: str
    features: list[str]
    primary_metric: str
    # The floor below which this model's metric is not worth reporting.
    # Higher for rare-event models: a 6% base rate needs far more rows to
    # accumulate enough positives than a balanced target does.
    min_labelled_rows: int
    # Features that would be leakage *for this model specifically*, beyond the
    # global list. Model E may use inspection results; Model C may not, because
    # inspection is how damage is determined.
    forbidden_features: list[str] = field(default_factory=list)
    # What this model is for, in the merchant's terms. Ends up in the model
    # card (Phase 49) and in the UI's explanation of a recommendation.
    purpose: str = ""
    # Stated up front so nobody discovers it after training.
    known_difficulty: str = ""

    def validate(self) -> None:
        if self.target in self.features:
            raise ValueError(f"{self.key}: target {self.target!r} is also a feature")
        overlap = set(self.features) & set(self.forbidden_features)
        if overlap:
            raise ValueError(
                f"{self.key}: {sorted(overlap)} listed as both feature and forbidden"
            )
        if self.min_labelled_rows < 1000:
            raise ValueError(
                f"{self.key}: min_labelled_rows below 1000 contradicts the "
                f"Phase 15 floor. Raise the floor deliberately in "
                f"dataset_builder if it should change, not per-model."
            )


MODEL_FAMILY: Final[dict[str, ModelSpec]] = {
    "cost": ModelSpec(
        key="cost",
        name="Model A — Return cost",
        task=TaskType.REGRESSION,
        target="actual_cost_minor",
        features=_BASE_FEATURES + _HISTORY_FEATURES,
        primary_metric="mae",
        min_labelled_rows=1_000,
        purpose="What will it cost to process this return, end to end?",
        known_difficulty=(
            "The current deployed model puts ~92% of importance on distance_km, "
            "making it functionally a courier pricing calculator. A replacement "
            "must be checked for the same collapse -- if distance dominates "
            "again, the model has learned shipping, not returns."
        ),
    ),
    "fraud": ModelSpec(
        key="fraud",
        name="Model B — Fraud probability",
        task=TaskType.BINARY,
        target="actual_fraud_confirmed",
        features=_BASE_FEATURES + _HISTORY_FEATURES + _EVIDENCE_FEATURES,
        primary_metric="pr_auc",
        # Rare event. At a ~5% base rate, 1,000 rows yields ~50 positives,
        # which is too few to fit anything stable. 5,000 gives ~250.
        min_labelled_rows=5_000,
        forbidden_features=["inspection_result", "disposition"],
        purpose="How likely is this return fraudulent?",
        known_difficulty=(
            "Measured on the synthetic dataset: ROC-AUC 0.556 against an "
            "oracle ceiling of 0.754. PR-AUC is the primary metric, not "
            "ROC-AUC or accuracy -- at a 5% base rate, predicting 'never "
            "fraud' scores 95% accuracy and is worthless."
        ),
    ),
    "damage": ModelSpec(
        key="damage",
        name="Model C — Damage probability",
        task=TaskType.BINARY,
        target="actual_damage_grade",
        features=_BASE_FEATURES + _HISTORY_FEATURES + _EVIDENCE_FEATURES,
        primary_metric="pr_auc",
        min_labelled_rows=2_000,
        # Inspection is how damage is *determined*. Using it as a feature
        # means predicting the inspection from the inspection.
        forbidden_features=["inspection_result", "inspection_notes", "disposition"],
        purpose="Will this item arrive damaged?",
        known_difficulty=(
            "Labels come from warehouse inspection, so they carry inspector "
            "subjectivity. Grade consistency should be checked across "
            "inspectors before trusting the target."
        ),
    ),
    "resale": ModelSpec(
        key="resale",
        name="Model D — Resale probability",
        task=TaskType.BINARY,
        target="was_resold",
        features=_BASE_FEATURES + _HISTORY_FEATURES,
        primary_metric="pr_auc",
        min_labelled_rows=2_000,
        purpose="Can this item be resold as-is?",
        known_difficulty=(
            "Survivorship bias: only items the merchant *attempted* to resell "
            "have an outcome. Items scrapped on arrival never enter the "
            "training set, so the model sees a filtered population."
        ),
    ),
    "recovery": ModelSpec(
        key="recovery",
        name="Model E — Recovery value",
        task=TaskType.REGRESSION,
        target="actual_resale_price_minor",
        features=_BASE_FEATURES + _HISTORY_FEATURES + ["actual_damage_grade"],
        primary_metric="mae",
        min_labelled_rows=1_000,
        purpose="How much will we recover from this item?",
        known_difficulty=(
            "Damage grade is permitted here because recovery is decided AFTER "
            "inspection -- unlike Model C, where it would be the answer. The "
            "prediction point differs, so what counts as leakage differs."
        ),
    ),
    "repair": ModelSpec(
        key="repair",
        name="Model F — Repair success",
        task=TaskType.BINARY,
        target="repair_successful",
        features=_BASE_FEATURES + ["actual_damage_grade"],
        primary_metric="pr_auc",
        min_labelled_rows=1_000,
        purpose="If we attempt a repair, will it work?",
        known_difficulty=(
            "Only meaningful for merchants who actually repair. For most D2C "
            "apparel sellers this model should not be deployed at all -- "
            "shipping an untrained model because the roadmap lists it would be "
            "worse than omitting it."
        ),
    ),
    "processing_time": ModelSpec(
        key="processing_time",
        name="Model G — Processing time",
        task=TaskType.REGRESSION,
        target="hours_to_resolution",
        features=_BASE_FEATURES + _HISTORY_FEATURES,
        primary_metric="mae",
        min_labelled_rows=1_000,
        purpose="How long will this return take to resolve?",
        known_difficulty=(
            "Heavily influenced by the merchant's own staffing, not the "
            "return's properties. Likely needs per-organization calibration "
            "(Phase 30) rather than one global model."
        ),
    ),
    "customer_risk": ModelSpec(
        key="customer_risk",
        name="Model H — Future return probability",
        task=TaskType.BINARY,
        target="customer_returned_again_90d",
        features=_HISTORY_FEATURES,
        primary_metric="pr_auc",
        min_labelled_rows=5_000,
        purpose="Will this customer return something again soon?",
        known_difficulty=(
            "Requires a 90-day observation window after each return, so the "
            "most recent quarter of data is unusable as training labels. "
            "Plan for that gap rather than discovering it mid-training."
        ),
    ),
    "disposition": ModelSpec(
        key="disposition",
        name="Model I — Disposition recommendation",
        task=TaskType.MULTICLASS,
        target="final_disposition",
        features=_BASE_FEATURES + _HISTORY_FEATURES + ["actual_damage_grade"],
        primary_metric="macro_f1",
        min_labelled_rows=2_000,
        purpose="Restock, repair, resell, liquidate, recycle or dispose?",
        known_difficulty=(
            "Trained on what staff DID, which encodes their habits including "
            "their mistakes. It learns to imitate current practice, not to "
            "optimise. Phase 24's economics calculation is what should drive "
            "the recommendation; this model is a prior, not an oracle."
        ),
    ),
}


def get_spec(key: str) -> ModelSpec:
    if key not in MODEL_FAMILY:
        raise KeyError(
            f"Unknown model {key!r}. Family: {', '.join(sorted(MODEL_FAMILY))}"
        )
    return MODEL_FAMILY[key]


def readiness(key: str, labelled_rows: int) -> dict[str, Any]:
    """Can this model be trained yet?"""
    spec = get_spec(key)
    ready = labelled_rows >= spec.min_labelled_rows
    return {
        "model": spec.key,
        "name": spec.name,
        "labelled_rows": labelled_rows,
        "required": spec.min_labelled_rows,
        "shortfall": max(spec.min_labelled_rows - labelled_rows, 0),
        "ready": ready,
        "target_column": spec.target,
        "primary_metric": spec.primary_metric,
        "known_difficulty": spec.known_difficulty,
    }


def family_status(labelled_counts: dict[str, int]) -> dict[str, Any]:
    """Readiness across the whole family.

    `labelled_counts` is keyed by model key; a missing key means zero, which
    is the correct default -- a target column that does not exist yet has no
    labels, and reporting it as unknown would obscure that.
    """
    models = {
        key: readiness(key, labelled_counts.get(key, 0))
        for key in MODEL_FAMILY
    }
    ready = [k for k, v in models.items() if v["ready"]]
    return {
        "models": models,
        "ready_count": len(ready),
        "total": len(MODEL_FAMILY),
        "ready": sorted(ready),
        "note": (
            "Labels accumulate only as real returns are resolved and their "
            "outcomes confirmed. No model here can be made ready by writing "
            "code."
        ),
    }


# Validated at import. A malformed spec should break the build, not surface
# during a training run at 2am.
for _spec in MODEL_FAMILY.values():
    _spec.validate()
