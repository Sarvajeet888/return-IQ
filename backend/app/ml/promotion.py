"""PHASE 28 — model promotion gates.

WHAT ALREADY EXISTED
--------------------
`ml/model_registry.py` handles versioning and rollback well: versioned
directories, an atomic `registry.json`, never overwriting a registered
version, instant rollback by repointing. That did not need rebuilding.

THE GAP
-------
`activate_version()` promotes **any** registered version to production with no
check at all. A model that loses to the baseline, is unstable across seeds,
predicts uncalibrated probabilities, and fails on half its segments can be
made live with one call.

Phases 18 and 19 built the machinery to detect every one of those. Nothing
connected them to the moment they matter — the promotion.

THE LINEAGE GAP
---------------
The registry records `registered_at` and a path. Phase 28 asks for version,
training dataset, metrics, code version, deployment date, owner and rollback
version.

The missing fields are not bookkeeping. Six months from now, "why is the
model behaving differently?" is answerable only if you can see which dataset
it was trained on and what it scored at promotion. Without that, the only
available action is retraining and hoping.

WHAT A GATE IS FOR
------------------
Not to stop people deploying. To stop them deploying *accidentally* — the
Friday-afternoon promotion where nobody re-checked the numbers because the
model "looked fine in the notebook".

An override exists, requires a written reason, and records who used it. A gate
with no override gets bypassed by copying files around it, which is worse:
then the bypass leaves no trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "PromotionCheck",
    "PromotionDecision",
    "ModelCard",
    "evaluate_promotion",
]

# A model must beat the trivial baseline by at least this margin, relatively.
# Zero would let a model that ties the baseline through by rounding.
MIN_BASELINE_IMPROVEMENT: Final[float] = 0.05

# Phase 18 measured seed-to-seed variance directly; a model that disagrees
# with itself by more than this is reporting a lucky draw.
MAX_SCORE_SPREAD: Final[float] = 0.05

# Phase 18: an ECE of 0.15 means probabilities are off by 15 percentage
# points. Phase 24 multiplies those probabilities by costs, so a miscalibrated
# model makes the *money* wrong, not just the score.
MAX_CALIBRATION_ERROR: Final[float] = 0.10

# Phase 19: a segment performing this many times worse than overall.
MAX_FAILING_SEGMENTS: Final[int] = 0


@dataclass(frozen=True)
class PromotionCheck:
    name: str
    passed: bool
    detail: str
    blocking: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "passed": self.passed,
            "blocking": self.blocking,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ModelCard:
    """Provenance for one model version.

    Every field answers a question someone will ask during an incident.
    `training_dataset_id` and `training_period` answer "what did it learn
    from"; `code_version` answers "which feature definitions were in force";
    `replaces` answers "what do we roll back to".
    """

    version: str
    model_key: str                    # which of the nine (Phase 17)
    training_dataset_id: str
    training_period: tuple[str, str]
    training_rows: int
    code_version: str
    owner: str
    primary_metric: str
    metric_value: float
    baseline_value: float
    score_spread: float
    calibration_error: float | None
    failing_segments: list[str] = field(default_factory=list)
    replaces: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "model": self.model_key,
            "training_dataset_id": self.training_dataset_id,
            "training_period": list(self.training_period),
            "training_rows": self.training_rows,
            "code_version": self.code_version,
            "owner": self.owner,
            "metrics": {
                "primary_metric": self.primary_metric,
                "value": self.metric_value,
                "baseline": self.baseline_value,
                "score_spread": self.score_spread,
                "calibration_error": self.calibration_error,
            },
            "failing_segments": self.failing_segments,
            "replaces": self.replaces,
        }


@dataclass
class PromotionDecision:
    version: str
    checks: list[PromotionCheck] = field(default_factory=list)
    override_reason: str | None = None
    override_by: str | None = None

    @property
    def blocking_failures(self) -> list[PromotionCheck]:
        return [c for c in self.checks if c.blocking and not c.passed]

    @property
    def allowed(self) -> bool:
        return not self.blocking_failures or self.override_reason is not None

    def as_dict(self) -> dict[str, Any]:
        failures = self.blocking_failures
        payload: dict[str, Any] = {
            "version": self.version,
            "allowed": self.allowed,
            "checks": [c.as_dict() for c in self.checks],
            "blocking_failures": [c.name for c in failures],
        }

        if failures and self.override_reason:
            payload["overridden"] = True
            payload["override_reason"] = self.override_reason
            payload["override_by"] = self.override_by
            payload["verdict"] = (
                f"Promotion allowed by manual override despite "
                f"{len(failures)} failing check(s). This is recorded against "
                f"{self.override_by}."
            )
        elif failures:
            payload["verdict"] = (
                f"Promotion blocked: {len(failures)} check(s) failed. "
                f"Fix them, or promote with a written override if you have a "
                f"reason the checks cannot see."
            )
        else:
            payload["verdict"] = "All promotion checks passed."

        return payload


def evaluate_promotion(
    card: ModelCard,
    *,
    lower_metric_is_better: bool = False,
    override_reason: str | None = None,
    override_by: str | None = None,
) -> PromotionDecision:
    """Decide whether a model version may go live.

    Every check corresponds to something an earlier phase measured. None of
    them is a rule of thumb invented here.
    """
    checks: list[PromotionCheck] = []

    # ── Beats the trivial baseline (Phase 18) ───────────────────────────────
    if lower_metric_is_better:
        improvement = (
            (card.baseline_value - card.metric_value) / card.baseline_value
            if card.baseline_value else 0.0
        )
    else:
        improvement = (
            (card.metric_value - card.baseline_value) / card.baseline_value
            if card.baseline_value else 0.0
        )

    checks.append(PromotionCheck(
        name="beats_baseline",
        passed=improvement >= MIN_BASELINE_IMPROVEMENT,
        detail=(
            f"{card.primary_metric} {card.metric_value:.4f} vs baseline "
            f"{card.baseline_value:.4f} ({improvement:+.1%}). A model that "
            f"cannot beat 'always guess the average' lends false authority to "
            f"a coin flip."
        ),
    ))

    # ── Stable across seeds (Phase 18) ──────────────────────────────────────
    checks.append(PromotionCheck(
        name="stable_across_seeds",
        passed=card.score_spread <= MAX_SCORE_SPREAD,
        detail=(
            f"Score varies by {card.score_spread:.4f} across retrains "
            f"(limit {MAX_SCORE_SPREAD}). Above this the headline number is a "
            f"lucky draw and will not reproduce."
        ),
    ))

    # ── Calibrated (Phase 18/24) ────────────────────────────────────────────
    if card.calibration_error is None:
        checks.append(PromotionCheck(
            name="calibrated",
            passed=True,
            blocking=False,
            detail=(
                "Not applicable — calibration is only meaningful for models "
                "that output probabilities."
            ),
        ))
    else:
        checks.append(PromotionCheck(
            name="calibrated",
            passed=card.calibration_error <= MAX_CALIBRATION_ERROR,
            detail=(
                f"Calibration error {card.calibration_error:.4f} "
                f"(limit {MAX_CALIBRATION_ERROR}). Phase 24 multiplies these "
                f"probabilities by costs, so a miscalibrated model makes the "
                f"money wrong, not just the score."
            ),
        ))

    # ── No failing segments (Phase 19) ──────────────────────────────────────
    checks.append(PromotionCheck(
        name="no_failing_segments",
        passed=len(card.failing_segments) <= MAX_FAILING_SEGMENTS,
        detail=(
            f"{len(card.failing_segments)} segment(s) perform materially worse "
            f"than the overall figure: {', '.join(card.failing_segments) or 'none'}. "
            f"A merchant whose entire catalogue sits in a failing segment "
            f"experiences this as 'the product does not work'."
        ),
    ))

    # ── Provenance is recorded (Phase 28) ───────────────────────────────────
    missing = [
        name for name, value in (
            ("training_dataset_id", card.training_dataset_id),
            ("code_version", card.code_version),
            ("owner", card.owner),
        ) if not value
    ]
    checks.append(PromotionCheck(
        name="provenance_recorded",
        passed=not missing,
        detail=(
            f"Missing: {', '.join(missing)}. Six months from now, 'why is the "
            f"model behaving differently?' is answerable only if you can see "
            f"what it was trained on and who deployed it."
            if missing else
            f"Trained on {card.training_dataset_id} "
            f"({card.training_rows:,} rows, {card.training_period[0]} to "
            f"{card.training_period[1]}), code {card.code_version}, "
            f"owner {card.owner}."
        ),
    ))

    # ── Rollback target exists (Phase 28) ───────────────────────────────────
    checks.append(PromotionCheck(
        name="rollback_target",
        passed=True,
        blocking=False,
        detail=(
            f"If this version misbehaves, {card.replaces} is still on disk "
            f"and rollback is a registry repoint — no retraining needed."
            if card.replaces else
            "No previous version — this is the first model for this key, so "
            "there is nothing to roll back to. Worth knowing before promoting."
        ),
    ))

    if override_reason is not None and (
        not override_by or len(override_reason.strip()) < 20
    ):
        raise ValueError(
            "An override needs a named person and a reason of at least 20 "
            "characters. A gate that can be bypassed anonymously is not a "
            "gate — and one with no override at all gets bypassed by copying "
            "files around it, which leaves no trace at all."
        )

    return PromotionDecision(
        version=card.version,
        checks=checks,
        override_reason=override_reason,
        override_by=override_by,
    )
