"""PHASE 20 — prediction uncertainty.

THE INSTRUCTION
---------------
> "Never pretend every prediction is equally reliable. Output: Prediction,
> Confidence, Prediction interval. Low-confidence predictions go to human
> review."

Phase 14 replaced the fabricated `confidence_score` with honest bands. This
phase adds the interval — the part that turns "expected recovery Rs 1,820"
into "Rs 1,560 to Rs 2,020", which is a statement a merchant can act on.

WHY CONFORMAL PREDICTION
------------------------
Most interval methods require assumptions the data will not honour: Gaussian
errors, correct model specification, homoscedasticity. When those assumptions
break, the interval is wrong in a way nobody notices, because a too-narrow
interval looks *better* than a wide one.

Split conformal prediction makes one assumption -- that calibration and future
data are exchangeable -- and in return gives a guarantee that is distribution
free and model agnostic: at level 0.9, at least 90% of future actuals fall
inside the interval. It holds for a linear model, a neural network, or a
random number generator. A bad model gets *wide* intervals rather than wrong
ones, which is the correct behaviour: the interval tells you the model is
uncertain instead of hiding it.

That property is why this module can be built and verified before ReturnIQ has
a trained model. The guarantee is mathematical, not empirical.

THE HONEST LIMIT
----------------
Exchangeability breaks under drift. If return patterns shift -- a new courier,
a festive season, a product-mix change -- calibration from last quarter
under-covers this quarter. Phase 27's drift monitoring is what detects that;
this module cannot, and says so rather than implying a guarantee it no longer
has.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "PredictionInterval",
    "ConformalCalibrator",
    "ReviewRouting",
    "route_by_uncertainty",
]

# Minimum calibration rows. The guarantee is finite-sample, and with n
# residuals the achievable coverage is capped at (n+1-k)/(n+1) -- with 10 rows
# you cannot express 95% at all. 100 is the floor at which the common levels
# are representable with headroom.
MIN_CALIBRATION_ROWS: Final[int] = 100


@dataclass(frozen=True)
class PredictionInterval:
    """A point prediction with an honest range around it."""

    prediction: float
    lower: float
    upper: float
    confidence_level: float
    calibration_rows: int

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def relative_width(self) -> float:
        """Width as a fraction of the prediction.

        The number that decides whether a prediction is usable. An interval of
        +/- Rs 50 on Rs 1,800 is actionable; +/- Rs 1,500 on the same
        prediction means the model does not know, and the merchant should be
        told that rather than shown a confident-looking point estimate.
        """
        denominator = abs(self.prediction)
        return self.width / denominator if denominator > 1e-9 else float("inf")

    def contains(self, actual: float) -> bool:
        return self.lower <= actual <= self.upper

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction": round(self.prediction, 2),
            "lower": round(self.lower, 2),
            "upper": round(self.upper, 2),
            "confidence_level": self.confidence_level,
            "width": round(self.width, 2),
            "relative_width": round(self.relative_width, 3),
            "calibration_rows": self.calibration_rows,
            "interpretation": (
                f"About {self.confidence_level:.0%} of actual outcomes for "
                f"returns like this one fall between {self.lower:,.0f} and "
                f"{self.upper:,.0f}."
            ),
        }


class ConformalCalibrator:
    """Split conformal prediction intervals.

    Fitted on a held-out calibration set -- NOT the training set. Using
    training residuals would produce intervals calibrated on data the model
    has already memorised, which is the same leakage error as evaluating on
    the training set, and it produces intervals that are too narrow in exactly
    the situations where you need them wide.
    """

    def __init__(self, confidence_level: float = 0.9) -> None:
        if not 0.5 <= confidence_level < 1.0:
            raise ValueError(
                f"confidence_level must be in [0.5, 1.0), got {confidence_level}. "
                f"Below 0.5 the interval is narrower than a coin flip, and 1.0 "
                f"requires an infinitely wide interval."
            )
        self.confidence_level = confidence_level
        self._quantile: float | None = None
        self._n: int = 0

    def fit(self, actual: list[float], predicted: list[float]) -> ConformalCalibrator:
        """Learn the interval width from calibration residuals."""
        if len(actual) != len(predicted):
            raise ValueError(
                f"{len(actual)} actuals vs {len(predicted)} predictions"
            )
        if len(actual) < MIN_CALIBRATION_ROWS:
            raise ValueError(
                f"{len(actual)} calibration rows; {MIN_CALIBRATION_ROWS} is the "
                f"minimum. The coverage guarantee is finite-sample: with n "
                f"residuals the achievable level is capped near n/(n+1), so a "
                f"small calibration set cannot express the requested level at "
                f"all."
            )

        residuals = sorted(abs(a - p) for a, p in zip(actual, predicted))
        n = len(residuals)

        # The finite-sample correction. Using the plain empirical quantile
        # under-covers slightly; ceil((n+1) * level) is what makes the
        # guarantee hold rather than approximately hold.
        rank = math.ceil((n + 1) * self.confidence_level)
        index = min(rank, n) - 1

        self._quantile = residuals[index]
        self._n = n
        return self

    def interval(self, prediction: float) -> PredictionInterval:
        if self._quantile is None:
            raise RuntimeError(
                "Calibrator not fitted. Call fit() on held-out calibration "
                "data before requesting intervals."
            )
        return PredictionInterval(
            prediction=prediction,
            lower=prediction - self._quantile,
            upper=prediction + self._quantile,
            confidence_level=self.confidence_level,
            calibration_rows=self._n,
        )

    def measured_coverage(
        self, actual: list[float], predicted: list[float],
    ) -> dict[str, Any]:
        """Check on fresh data whether the guarantee is actually holding.

        The guarantee assumes exchangeability. Drift breaks it, and the
        failure is silent: intervals stay the same width while covering less.
        This is the check that catches it, and Phase 27 is where it should run
        continuously.
        """
        covered = sum(
            1 for a, p in zip(actual, predicted) if self.interval(p).contains(a)
        )
        n = len(actual)
        rate = covered / n if n else 0.0

        # Finite-sample slack.
        #
        # MEASURED, not assumed. My first version used only the test-set
        # sampling error, 2*sqrt(p(1-p)/n). Across 200 trials on perfectly
        # calibrated data with no drift, that produced a 7% FALSE ALARM rate:
        # observed coverage had sd 0.0112 while the tolerance allowed 0.0155,
        # and 14 of 200 correct calibrators were reported as broken.
        #
        # The missing term is the calibration draw itself. The quantile is
        # estimated from a finite calibration set, so it varies run to run, and
        # that variance adds to the test-set variance. Both are included now.
        #
        # A drift monitor that fires on correct data is worse than no monitor,
        # because people learn to dismiss it — the same failure the Phase 8
        # audit chain had to avoid.
        if n:
            test_se = math.sqrt(
                self.confidence_level * (1 - self.confidence_level) / n
            )
            calibration_se = math.sqrt(
                self.confidence_level * (1 - self.confidence_level) / self._n
            ) if self._n else 0.0
            tolerance = 2 * math.sqrt(test_se ** 2 + calibration_se ** 2)
        else:
            tolerance = 1.0

        holding = rate >= self.confidence_level - tolerance
        return {
            "measured_coverage": round(rate, 4),
            "target_coverage": self.confidence_level,
            "n": n,
            "guarantee_holding": holding,
            "note": (
                "Coverage is within sampling tolerance of the target."
                if holding else
                f"Coverage is {self.confidence_level - rate:.1%} below target. "
                f"The calibration set is no longer exchangeable with live "
                f"data — most likely drift. Recalibrate, and investigate what "
                f"changed before trusting these intervals."
            ),
        }


class ReviewRouting:
    AUTOMATE: Final = "automate"
    REVIEW: Final = "review"
    MANUAL: Final = "manual"


def route_by_uncertainty(
    interval: PredictionInterval,
    *,
    automate_below: float = 0.20,
    review_below: float = 0.60,
) -> dict[str, Any]:
    """Route a prediction by how wide its interval is.

    Phase 20's rule: high confidence automates, medium reviews, low goes
    manual. Width relative to the prediction is the right signal because it is
    scale-free -- +/- Rs 200 is tight on a Rs 5,000 return and useless on a
    Rs 300 one.

    Thresholds are conservative by default. While ReturnIQ's models are
    trained on synthetic data, almost everything should land in review, and
    that is the correct outcome rather than a tuning problem to fix.
    """
    relative = interval.relative_width

    if relative <= automate_below:
        decision, reason = ReviewRouting.AUTOMATE, (
            f"The interval is +/-{relative / 2:.0%} of the prediction — tight "
            f"enough to act on without a person."
        )
    elif relative <= review_below:
        decision, reason = ReviewRouting.REVIEW, (
            f"The interval spans {relative:.0%} of the prediction. Usable as a "
            f"starting point, but a person should confirm it."
        )
    else:
        decision, reason = ReviewRouting.MANUAL, (
            f"The interval spans {relative:.0%} of the prediction — the model "
            f"does not meaningfully know the answer. Decide this one on the "
            f"evidence, not the estimate."
        )

    return {
        "decision": decision,
        "reason": reason,
        "relative_width": round(relative, 3),
        "interval": interval.as_dict(),
    }
