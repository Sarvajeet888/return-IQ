"""PHASE 29 — continuous learning.

THE LOOP
--------
    Prediction -> Decision -> Actual outcome -> Error -> New training data
      -> Candidate -> Evaluation -> Human approval -> Production

Every box exists as code after Phases 15-28. Nothing connects them, and the
connection is where the danger lives: a loop that runs end to end without
stopping is a system that retrains itself on its own mistakes and deploys the
result overnight.

THE ROADMAP'S OWN CONSTRAINT
----------------------------
> "Do not blindly retrain and automatically deploy models."

This module makes that structural rather than a matter of discipline. There is
no code path from "candidate trained" to "candidate live". `approve_candidate`
requires a person, and the orchestrator returns a candidate — it cannot
promote one.

THE FEEDBACK TRAP
-----------------
The subtler risk is not bad models; it is a model training on data its own
decisions produced.

If the system auto-approves low-risk returns, those returns are never
inspected, so no outcome is ever recorded for them. Retrain on what remains
and the training set is *only* the returns a human looked at — the hard ones.
The model then learns that returns look harder than they are, flags more of
them, and the next training set is harder still.

Nobody notices, because every metric is computed on the same skewed
population. `check_feedback_contamination` measures the proportion of training
rows whose outcome the system itself determined, and refuses above a
threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

__all__ = [
    "RetrainingTrigger",
    "CandidateResult",
    "check_feedback_contamination",
    "should_retrain",
    "approve_candidate",
]

# New labelled outcomes required before retraining is worth the risk.
# Retraining on 50 new rows changes the model unpredictably while adding
# almost no information -- churn without learning.
MIN_NEW_LABELS: Final[int] = 500

# Days after which a model is stale even without new data. Return patterns
# shift seasonally; a model trained last Diwali is describing a different
# world by March.
MAX_MODEL_AGE_DAYS: Final[int] = 180

# Above this proportion of self-determined outcomes, the training set is
# measuring the system rather than the world.
MAX_SELF_DETERMINED_RATIO: Final[float] = 0.30


@dataclass(frozen=True)
class RetrainingTrigger:
    should_retrain: bool
    reasons: list[str]
    blockers: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "should_retrain": self.should_retrain,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "note": (
                "A trigger is a recommendation to train a candidate. It is "
                "never a decision to deploy one — that requires a person."
            ),
        }


@dataclass
class CandidateResult:
    """A trained candidate, and whether it may be proposed for promotion.

    Deliberately has no `deploy()`. The only route to production is
    `approve_candidate()` followed by the existing registry call, and both
    require a named human.
    """

    model_key: str
    version: str
    passed_gates: bool
    gate_report: dict[str, Any]
    champion_version: str | None
    beats_champion: bool
    approved_by: str | None = None
    approved_at: str | None = None
    approval_note: str | None = None

    @property
    def is_deployable(self) -> bool:
        return self.passed_gates and self.beats_champion and self.approved_by is not None

    def as_dict(self) -> dict[str, Any]:
        if self.approved_by:
            status = "approved"
        elif not self.passed_gates:
            status = "blocked_by_gates"
        elif not self.beats_champion:
            status = "does_not_beat_champion"
        else:
            status = "awaiting_approval"

        return {
            "model": self.model_key,
            "version": self.version,
            "status": status,
            "passed_gates": self.passed_gates,
            "beats_champion": self.beats_champion,
            "champion_version": self.champion_version,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "deployable": self.is_deployable,
            "gate_report": self.gate_report,
            "note": (
                "A candidate is never deployed by this pipeline. Approval "
                "records that a person reviewed the evidence and accepted "
                "responsibility for the change."
            ),
        }


def check_feedback_contamination(
    training_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """What proportion of these labels did the system itself determine?

    A row whose outcome was set by automation is not independent evidence. It
    tells you what the system decided, not what was true.

    The failure mode is quiet. If low-risk returns are auto-approved and never
    inspected, no outcome is recorded for them, so the training set becomes
    only the returns a human looked at — the hard ones. The model learns that
    returns look harder than they are, flags more, and the next training set is
    harder still. Every metric stays healthy because they are all computed on
    the same skewed population.
    """
    total = len(training_rows)
    if total == 0:
        return {
            "total_rows": 0,
            "self_determined": 0,
            "ratio": 0.0,
            "contaminated": False,
            "detail": "No training rows.",
        }

    self_determined = sum(
        1 for r in training_rows
        if r.get("outcome_source") in {"automated", "system"}
    )
    ratio = self_determined / total
    contaminated = ratio > MAX_SELF_DETERMINED_RATIO

    return {
        "total_rows": total,
        "self_determined": self_determined,
        "ratio": round(ratio, 4),
        "contaminated": contaminated,
        "detail": (
            f"{ratio:.0%} of training labels were set by the system's own "
            f"automated decisions rather than observed independently. Above "
            f"{MAX_SELF_DETERMINED_RATIO:.0%} the model is learning to predict "
            f"itself, and every evaluation metric will look healthy while it "
            f"does."
            if contaminated else
            f"{ratio:.0%} of labels are self-determined, within the "
            f"{MAX_SELF_DETERMINED_RATIO:.0%} limit."
        ),
    }


def should_retrain(
    *,
    new_labels_since_training: int,
    model_age_days: int,
    drift_detected: bool = False,
    major_drift_features: list[str] | None = None,
    training_rows: list[dict[str, Any]] | None = None,
) -> RetrainingTrigger:
    """Decide whether a candidate is worth training.

    Reasons and blockers are separate lists. A model can be simultaneously
    overdue for retraining and unsafe to retrain — drifted badly *and*
    contaminated by its own decisions — and collapsing that into one boolean
    hides exactly the situation that most needs a person to look.
    """
    reasons: list[str] = []
    blockers: list[str] = []

    if new_labels_since_training >= MIN_NEW_LABELS:
        reasons.append(
            f"{new_labels_since_training:,} new labelled outcomes since the "
            f"last training run."
        )
    else:
        blockers.append(
            f"Only {new_labels_since_training:,} new labels; "
            f"{MIN_NEW_LABELS:,} is the floor. Retraining on fewer changes the "
            f"model unpredictably while adding almost no information — churn "
            f"without learning."
        )

    if model_age_days >= MAX_MODEL_AGE_DAYS:
        reasons.append(
            f"The live model is {model_age_days} days old. Return patterns "
            f"shift seasonally; a model trained last festive season is "
            f"describing a different world."
        )

    if drift_detected:
        features = ", ".join(major_drift_features or []) or "unspecified"
        reasons.append(f"Input drift detected on: {features}.")

    if training_rows is not None:
        contamination = check_feedback_contamination(training_rows)
        if contamination["contaminated"]:
            blockers.append(contamination["detail"])

    return RetrainingTrigger(
        should_retrain=bool(reasons) and not blockers,
        reasons=reasons,
        blockers=blockers,
    )


def approve_candidate(
    candidate: CandidateResult,
    *,
    approved_by: str,
    note: str,
) -> CandidateResult:
    """Record that a person reviewed the evidence and accepted the change.

    Refuses to approve a candidate that failed its gates or lost to the
    champion. That is not the same as Phase 28's override: there, a person
    consciously overrides a specific failing check with a written reason.
    Here, approval is a rubber stamp at the end of a pipeline — the point in
    the process where least attention is being paid, and therefore the wrong
    place to allow a bypass.
    """
    if not approved_by:
        raise ValueError("Approval requires a named person.")
    if not note or len(note.strip()) < 20:
        raise ValueError(
            "Approval requires a note of at least 20 characters describing "
            "what was reviewed. 'looks good' is not a review."
        )
    if not candidate.passed_gates:
        raise ValueError(
            f"Candidate {candidate.version} failed its promotion gates and "
            f"cannot be approved here. If a specific check should be waived, "
            f"do that deliberately with a Phase 28 override — not as a "
            f"rubber stamp at the end of a pipeline."
        )
    if not candidate.beats_champion:
        raise ValueError(
            f"Candidate {candidate.version} does not beat the current "
            f"champion {candidate.champion_version}. Deploying it trades a "
            f"known model for a worse one."
        )

    candidate.approved_by = approved_by
    candidate.approved_at = datetime.now(UTC).isoformat()
    candidate.approval_note = note
    return candidate
