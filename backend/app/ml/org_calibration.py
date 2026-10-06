"""PHASE 30 — organization-specific calibration.

THE INSTRUCTION
---------------
> Global model -> Organization calibration -> Customer-specific behaviour.
> Different businesses have different return patterns. The system should adapt
> without leaking data between tenants.

WHY CALIBRATE RATHER THAN TRAIN PER ORGANIZATION
------------------------------------------------
A separate model per merchant sounds better and is worse. A merchant
processing 200 returns a month reaches Phase 15's 1,000-row floor after five
months, and a model fitted on 1,000 rows of one merchant's traffic will overfit
their recent quarter. Meanwhile the global model has everyone's data.

Calibration keeps the global model's *ranking* — which returns are riskier
than which — and corrects only its *level*. That is the part that genuinely
differs between businesses: an electronics seller has a higher base damage
rate than an apparel seller, and a global model trained mostly on apparel will
under-predict damage for them consistently, while still ordering their returns
correctly.

Correcting a level needs far less data than learning a ranking.

THE ISOLATION REQUIREMENT
-------------------------
Every function here takes org_id and uses only that org's outcomes. This is
Phase 4's rule applied to ML: a calibration fitted on merchant A's returns and
applied to merchant B would be one merchant's commercial behaviour leaking
into another's predictions -- harder to notice than a data leak and just as
much a breach.

WHAT THIS DOES NOT DO
---------------------
It does not personalise per end-customer. The roadmap's third tier
("customer-specific behaviour") requires per-customer outcome volume that no
merchant will have for years, and fitting a correction per shopper would be
fitting noise with extra steps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "Calibration",
    "MIN_CALIBRATION_OUTCOMES",
    "fit_org_calibration",
    "apply_calibration",
]

# Below this an org's correction is fitted on noise. Deliberately lower than
# Phase 15's 1,000-row training floor: correcting a level is a one-parameter
# problem, while learning a ranking is not.
MIN_CALIBRATION_OUTCOMES: Final[int] = 200

# Corrections beyond this are refused. A merchant needing a 3x correction does
# not have a calibration problem -- the global model does not describe their
# business at all, and quietly scaling its output would hide that behind a
# number that looks adjusted.
MAX_CORRECTION_FACTOR: Final[float] = 2.0

# Below this the difference is not worth applying: it is inside the noise of a
# 200-row sample, and a correction that changes nothing still has to be
# explained to whoever finds it later.
MIN_MEANINGFUL_CORRECTION: Final[float] = 0.05


@dataclass(frozen=True)
class Calibration:
    org_id: str
    model_key: str
    factor: float | None
    outcomes_used: int
    applied: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "model": self.model_key,
            "factor": round(self.factor, 4) if self.factor is not None else None,
            "outcomes_used": self.outcomes_used,
            "applied": self.applied,
            "reason": self.reason,
        }


def fit_org_calibration(
    org_id: str,
    model_key: str,
    outcomes: list[dict[str, Any]],
    *,
    predicted_key: str = "predicted",
    actual_key: str = "actual",
) -> Calibration:
    """Fit a single multiplicative correction from one org's own outcomes.

    `outcomes` must already be scoped to this org by the caller. This function
    does not filter -- a function that silently drops foreign rows would mask
    a caller passing the wrong set, and the failure would be invisible. The
    contract is enforced at the call site (store functions are org-scoped per
    Phase 4) and asserted in tests.

    Uses the ratio of summed actuals to summed predictions rather than the
    mean of per-row ratios. Per-row ratios explode when a prediction is near
    zero, and a single Rs 2 prediction against a Rs 400 actual would dominate
    the entire correction.
    """
    usable = [
        o for o in outcomes
        if o.get(predicted_key) is not None and o.get(actual_key) is not None
    ]

    if len(usable) < MIN_CALIBRATION_OUTCOMES:
        return Calibration(
            org_id=org_id, model_key=model_key, factor=None,
            outcomes_used=len(usable), applied=False,
            reason=(
                f"{len(usable)} confirmed outcomes; {MIN_CALIBRATION_OUTCOMES} "
                f"is the minimum. Below this a correction is fitted on noise, "
                f"and this organization keeps the global model unchanged."
            ),
        )

    total_predicted = sum(float(o[predicted_key]) for o in usable)
    total_actual = sum(float(o[actual_key]) for o in usable)

    if total_predicted <= 0:
        return Calibration(
            org_id=org_id, model_key=model_key, factor=None,
            outcomes_used=len(usable), applied=False,
            reason=(
                "Predictions for this organization sum to zero or less, so "
                "there is no level to correct."
            ),
        )

    factor = total_actual / total_predicted

    if abs(factor - 1.0) < MIN_MEANINGFUL_CORRECTION:
        return Calibration(
            org_id=org_id, model_key=model_key, factor=factor,
            outcomes_used=len(usable), applied=False,
            reason=(
                f"The global model is already within "
                f"{abs(factor - 1.0):.1%} for this organization. No correction "
                f"applied — a change this small is inside the noise of a "
                f"{len(usable)}-row sample."
            ),
        )

    if factor > MAX_CORRECTION_FACTOR or factor < 1 / MAX_CORRECTION_FACTOR:
        return Calibration(
            org_id=org_id, model_key=model_key, factor=factor,
            outcomes_used=len(usable), applied=False,
            reason=(
                f"The global model is out by {factor:.2f}x for this "
                f"organization, beyond the {MAX_CORRECTION_FACTOR}x limit. "
                f"This is not a calibration problem — the model does not "
                f"describe this business, and scaling its output would hide "
                f"that behind a number that looks adjusted. Investigate before "
                f"relying on predictions here."
            ),
        )

    direction = "under" if factor > 1 else "over"
    return Calibration(
        org_id=org_id, model_key=model_key, factor=factor,
        outcomes_used=len(usable), applied=True,
        reason=(
            f"The global model {direction}-predicts by "
            f"{abs(factor - 1.0):.0%} for this organization across "
            f"{len(usable)} confirmed outcomes. Corrected by {factor:.3f}x."
        ),
    )


def apply_calibration(prediction: float, calibration: Calibration) -> float:
    """Apply an org's correction, or return the global prediction unchanged.

    Falling back to the global model is the correct default, not a degraded
    one. A new merchant with no history gets the model trained on everyone
    else's data, which is the best available estimate for them.
    """
    if not calibration.applied or calibration.factor is None:
        return prediction
    return prediction * calibration.factor
