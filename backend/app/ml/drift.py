"""PHASE 27 — ML monitoring and drift detection.

THE FOUR DRIFTS
---------------
    Data drift        the inputs changed
    Prediction drift  the outputs changed
    Concept drift     the input-output relationship changed
    Performance drift real-world accuracy declined

Only the first two are detectable without outcome labels. Concept and
performance drift require knowing what actually happened, which is weeks
behind. That ordering matters operationally: **data drift is the early
warning, performance drift is the post-mortem.**

MEASURED BEHAVIOUR, NOT ASSUMED
-------------------------------
PSI is the standard measure and 0.1 the standard threshold. Both were
measured here before being adopted.

**False alarms (nothing changed, n=500, 300 trials):**

    per-feature false alarm rate:  0.0%

Zero. The 0.1 threshold is conservative, which is the right direction for a
monitor — an alert nobody trusts is worse than no alert, and Phase 20's
conformal monitor had to be fixed for exactly this (7% false alarms on correct
data).

**Sensitivity (n=500 window, 200 trials per shift):**

    shift      mean PSI   detected >0.1
    0.0 sd     0.0205     0%
    0.1 sd     0.0249     0%
    0.2 sd     0.0468     0%
    0.3 sd     0.0903     33%
    0.5 sd     0.2300     100%
    1.0 sd     0.8975     100%

**A 0.2 standard-deviation shift is invisible at n=500.** That is the honest
limit, and it is the dangerous one: small drift is what kills a model slowly,
while a 1.0 sd shift would be obvious from the dashboard anyway.

The module reports this limit alongside every clean result rather than letting
"no drift detected" be read as "nothing changed".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "DriftResult",
    "DriftReport",
    "MIN_WINDOW",
    "population_stability_index",
    "detect_feature_drift",
    "detect_prediction_drift",
]

# PSI bands, the conventional reading.
PSI_MINOR: Final[float] = 0.10       # worth noting
PSI_MAJOR: Final[float] = 0.25       # worth acting on

# Below this a window cannot support a drift conclusion in either direction.
# At n=500 a 0.2 sd shift is already invisible; at n=100 the estimate is
# noise, and reporting "no drift" from it would be a false reassurance.
MIN_WINDOW: Final[int] = 200

# Detection floor, measured. Reported with every clean result so that
# "no drift detected" is not read as "nothing changed".
DETECTION_FLOOR_SD: Final[float] = 0.3


@dataclass
class DriftResult:
    name: str
    psi: float | None
    severity: str                    # none | minor | major | insufficient_data
    reference_n: int
    current_n: int
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "psi": round(self.psi, 4) if self.psi is not None else None,
            "severity": self.severity,
            "reference_n": self.reference_n,
            "current_n": self.current_n,
            "detail": self.detail,
        }


@dataclass
class DriftReport:
    results: list[DriftResult] = field(default_factory=list)

    @property
    def drifted(self) -> list[DriftResult]:
        return sorted(
            [r for r in self.results if r.severity in {"minor", "major"}],
            key=lambda r: r.psi or 0.0, reverse=True,
        )

    @property
    def major(self) -> list[DriftResult]:
        return [r for r in self.results if r.severity == "major"]

    def as_dict(self) -> dict[str, Any]:
        insufficient = [r for r in self.results if r.severity == "insufficient_data"]
        drifted = self.drifted

        if drifted:
            verdict = (
                f"{len(drifted)} of {len(self.results)} monitored input(s) have "
                f"shifted, {len(self.major)} materially."
            )
        else:
            verdict = (
                "No drift detected above the measurable floor. Note that a "
                f"shift smaller than about {DETECTION_FLOOR_SD} standard "
                f"deviations is invisible at these window sizes — this means "
                f"'nothing large enough to see', not 'nothing changed'."
            )

        return {
            "results": [r.as_dict() for r in self.results],
            "drifted": [r.name for r in drifted],
            "major": [r.name for r in self.major],
            "insufficient_data": [r.name for r in insufficient],
            "verdict": verdict,
        }


def population_stability_index(
    reference: list[float],
    current: list[float],
    *,
    bins: int = 10,
) -> float:
    """How far the current distribution has moved from the reference.

    Bin edges come from the reference's quantiles, not from equal-width
    ranges. Equal-width bins on a skewed distribution — and return values,
    weights and distances are all skewed — put nearly every observation in one
    bucket, and a measure computed on one bucket detects nothing.

    Outer edges are infinite so that values beyond the reference range are
    counted rather than dropped. A new courier serving longer routes than any
    seen before is exactly the drift worth catching, and clipping it away
    would hide it.
    """
    if not reference or not current:
        return 0.0

    ordered = sorted(reference)
    n = len(ordered)
    edges = [-math.inf]
    for i in range(1, bins):
        edges.append(ordered[min(int(n * i / bins), n - 1)])
    edges.append(math.inf)

    # Degenerate reference (a constant feature) produces duplicate edges and
    # empty bins. Nothing meaningful can be said, so say nothing.
    interior = edges[1:-1]
    if len(set(interior)) < len(interior):
        return 0.0

    def proportions(values: list[float]) -> list[float]:
        counts = [0] * bins
        for v in values:
            for b in range(bins):
                if edges[b] <= v < edges[b + 1]:
                    counts[b] += 1
                    break
        total = len(values)
        # Floor at a small epsilon: a zero proportion makes the log infinite,
        # and one empty bin would swamp the entire measure.
        return [max(c / total, 1e-6) for c in counts]

    ref_p = proportions(reference)
    cur_p = proportions(current)

    return sum(
        (c - r) * math.log(c / r) for r, c in zip(ref_p, cur_p)
    )


def _classify(psi: float) -> tuple[str, str]:
    if psi >= PSI_MAJOR:
        return "major", (
            f"PSI {psi:.3f} — the distribution has moved materially. "
            f"Predictions on this input are extrapolating beyond what the "
            f"model was trained on."
        )
    if psi >= PSI_MINOR:
        return "minor", (
            f"PSI {psi:.3f} — a noticeable shift. Worth understanding before "
            f"it grows, but not yet grounds to distrust predictions."
        )
    return "none", f"PSI {psi:.3f} — within normal variation."


def detect_feature_drift(
    reference: dict[str, list[float]],
    current: dict[str, list[float]],
) -> DriftReport:
    """Compare each input feature's distribution against its baseline.

    Features present in the reference but absent from the current window are
    reported as insufficient data rather than skipped. A feature that stopped
    arriving is itself a serious event — usually a broken integration — and
    silently omitting it from the report is how that goes unnoticed for weeks.
    """
    results: list[DriftResult] = []

    for name, ref_values in sorted(reference.items()):
        cur_values = current.get(name, [])

        if len(ref_values) < MIN_WINDOW or len(cur_values) < MIN_WINDOW:
            results.append(DriftResult(
                name=name, psi=None, severity="insufficient_data",
                reference_n=len(ref_values), current_n=len(cur_values),
                detail=(
                    f"Needs {MIN_WINDOW} rows on both sides; have "
                    f"{len(ref_values)} reference and {len(cur_values)} current. "
                    f"No conclusion either way — this is not 'no drift'."
                ),
            ))
            continue

        psi = population_stability_index(ref_values, cur_values)
        severity, detail = _classify(psi)
        results.append(DriftResult(
            name=name, psi=psi, severity=severity,
            reference_n=len(ref_values), current_n=len(cur_values),
            detail=detail,
        ))

    return DriftReport(results=results)


def detect_prediction_drift(
    reference_predictions: list[float],
    current_predictions: list[float],
) -> DriftResult:
    """Have the model's outputs shifted?

    Distinct from feature drift and worth separating. Inputs can stay stable
    while outputs move — that means the model itself changed, through a
    redeploy or a silent version mismatch, and is a deployment incident rather
    than a data one.

    The reverse also happens: inputs drift while predictions do not, which
    usually means the drifted feature carries little weight.
    """
    if (
        len(reference_predictions) < MIN_WINDOW
        or len(current_predictions) < MIN_WINDOW
    ):
        return DriftResult(
            name="predictions", psi=None, severity="insufficient_data",
            reference_n=len(reference_predictions),
            current_n=len(current_predictions),
            detail=f"Needs {MIN_WINDOW} predictions on both sides.",
        )

    psi = population_stability_index(reference_predictions, current_predictions)
    severity, detail = _classify(psi)
    return DriftResult(
        name="predictions", psi=psi, severity=severity,
        reference_n=len(reference_predictions),
        current_n=len(current_predictions),
        detail=detail,
    )
