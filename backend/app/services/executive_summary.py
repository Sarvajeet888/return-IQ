"""PHASE 36 — executive intelligence.

WHY THIS IS A THIN LAYER, NOT A NEW ENGINE
--------------------------------------------
Everything an executive summary needs to explain a change already exists in
`insight_engine.py` (Phase 35): exact decomposition, reconciliation, the
explicit warning that dimensions are not additive with each other. Rebuilding
that logic here would be the same mistake Phase 21 found and fixed --
approximating something that can be computed exactly, a second time, badly.

This module adds two things Phase 35 deliberately left to the caller:
picking which dimension is worth leading with when nobody specifies one, and
a small set of headline KPIs an executive reads before any breakdown at all.

THE DISAMBIGUATION THIS MODULE HAS TO GET RIGHT
--------------------------------------------------
Phase 35 proved that two different dimensions can each independently explain
close to 100% of the same change (the Electronics/Damaged overlap). Picking
"the most explanatory dimension" and presenting it alone would silently
recreate that exact problem at the executive layer, dressed up as a single
confident answer instead of a list. So `lead_dimension()` checks whether more
than one dimension is comparably concentrated, and says so explicitly rather
than picking a winner and hiding the runner-up.

KPIS ARE LIMITED TO FIELDS THAT ACTUALLY EXIST
--------------------------------------------------
`ReturnRequest` has `created_at` and `updated_at`, not a dedicated
`resolved_at`. "Time to resolution" is computed as `updated_at - created_at`
for returns in a terminal status, which is what that field actually measures
for a return that has stopped changing -- not a fabricated field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from app.core.money import Money
from app.services.insight_engine import (
    VALID_DIMENSIONS,
    ChangeDecomposition,
    decompose_change,
)

__all__ = ["ExecutiveSummary", "LeadDimension", "build_summary", "lead_dimension"]

# A return in one of these has stopped changing, so updated_at - created_at
# is a real duration, not a snapshot of wherever it happens to be mid-flow.
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    "refunded", "closed", "rejected", "cancelled",
})

# Concentration ratio above which two dimensions are "comparably explanatory"
# and must both be surfaced rather than picking one. 0.85 means the runner-up
# explains at least 85% as much of the change as the leader, at the top
# segment level -- close enough that presenting only the leader would be the
# same overstatement Phase 35 found in the roadmap's own example.
_COMPARABLE_RATIO: Final[float] = 0.85


def _parse(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        text = str(value).replace("Z", "").replace(" ", "T", 1)
        return datetime.fromisoformat(text.split("+")[0])
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class LeadDimension:
    dimension: str | None
    decomposition: ChangeDecomposition | None
    comparable_alternatives: list[str]
    # Populated only when no dimension could be identified -- see the empty
    # `candidates` branch in lead_dimension() below.
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        if self.dimension is None or self.decomposition is None:
            return {"led_with": None, "reason": self.reason}

        payload = self.decomposition.as_dict()
        payload["led_with"] = self.dimension
        if self.comparable_alternatives:
            payload["also_comparably_explanatory"] = self.comparable_alternatives
            payload["disambiguation"] = (
                f"{', '.join(self.comparable_alternatives)} explain a similar "
                f"share of this change through their own top segment. This is "
                f"one useful lens, not the single cause -- see Phase 35's "
                f"cross-dimension note before treating {self.dimension!r} as "
                f"the whole story."
            )
        return payload


def lead_dimension(
    rows_before: list[dict[str, Any]],
    rows_after: list[dict[str, Any]],
    *,
    value_key: str,
    dimensions: list[str] | None = None,
    currency: str | None = None,
    label: str = "Value",
    period_before: tuple[str, str] = ("", ""),
    period_after: tuple[str, str] = ("", ""),
) -> LeadDimension:
    """Pick the single most useful dimension to lead with -- honestly.

    Ranks dimensions by how much of the total change their single largest
    segment explains, then checks whether a runner-up is close enough to the
    leader that presenting only the leader would overstate how settled the
    explanation is.
    """
    dims = dimensions or sorted(VALID_DIMENSIONS)
    all_decompositions: list[tuple[float, str, ChangeDecomposition]] = []
    candidates: list[tuple[float, str, ChangeDecomposition]] = []

    for dim in dims:
        decomposition = decompose_change(
            rows_before, rows_after, value_key=value_key, dimension=dim,
            currency=currency, label=label,
            period_before=period_before, period_after=period_after,
        )
        top = max(
            (abs(s.contribution_pct_of_change or 0) for s in decomposition.segments),
            default=0.0,
        )
        entry = (top, dim, decomposition)
        all_decompositions.append(entry)

        # A dimension with only one distinct value across the whole dataset
        # cannot meaningfully "explain" anything: its single segment is
        # tautologically 100% of the change, because there is nowhere else
        # for the change to be attributed. That 100% carries no diagnostic
        # information -- it just means every row shares one value -- and
        # ranking it as a leading driver would be reporting an artefact of
        # the data shape as if it were a finding.
        if len(decomposition.segments) >= 2:
            candidates.append(entry)

    scored = candidates
    if not scored:
        # Found live, not in a unit test: an end-to-end check using data
        # where every dimension happened to be constant (one courier, one
        # category, one payment mode, one reason -- entirely plausible for
        # a small or new merchant) fell through to `all_decompositions` and
        # presented an arbitrary alphabetically-first dimension as the
        # "primary driver", because every degenerate dimension ties at
        # exactly 100% contribution by tautology. That is fabricating a
        # finding from data that contains none. The honest output here is
        # no driver, with a reason -- not a confident-looking wrong one.
        names = ", ".join(sorted({name for _, name, _ in all_decompositions}))
        return LeadDimension(
            dimension=None, decomposition=None, comparable_alternatives=[],
            reason=(
                f"None of the tracked dimensions ({names}) vary across these "
                f"returns -- every return shares the same value in each one. "
                f"The total changed, but no specific driver can be isolated "
                f"from a dataset with no variation to attribute it to."
            ),
        )
    scored.sort(key=lambda t: -t[0])
    best_score, best_dim, best_decomposition = scored[0]

    comparable = [
        dim for score, dim, decomposition in scored[1:]
        if best_score > 0
        and score / best_score >= _COMPARABLE_RATIO
        and len(decomposition.segments) >= 2
    ]

    return LeadDimension(
        dimension=best_dim, decomposition=best_decomposition,
        comparable_alternatives=comparable,
    )


@dataclass
class ExecutiveSummary:
    period_before: tuple[str, str]
    period_after: tuple[str, str]
    total_returns_before: int
    total_returns_after: int
    total_value_before: int | None
    total_value_after: int | None
    currency: str | None
    status_breakdown_after: dict[str, int]
    median_resolution_hours: float | None
    resolution_sample_size: int
    lead: LeadDimension | None

    def as_dict(self) -> dict[str, Any]:
        def fmt(minor: int | None) -> Any:
            if minor is None or not self.currency:
                return None
            return Money(minor, self.currency).as_dict()

        return {
            "period_before": list(self.period_before),
            "period_after": list(self.period_after),
            "total_returns": {
                "before": self.total_returns_before,
                "after": self.total_returns_after,
            },
            "total_value": {"before": fmt(self.total_value_before),
                            "after": fmt(self.total_value_after)},
            "status_breakdown": self.status_breakdown_after,
            "median_resolution_hours": (
                round(self.median_resolution_hours, 1)
                if self.median_resolution_hours is not None else None
            ),
            "resolution_sample_size": self.resolution_sample_size,
            "primary_driver": self.lead.as_dict() if self.lead else None,
        }


def build_summary(
    rows_before: list[dict[str, Any]],
    rows_after: list[dict[str, Any]],
    *,
    currency: str | None = None,
    period_before: tuple[str, str] = ("", ""),
    period_after: tuple[str, str] = ("", ""),
) -> ExecutiveSummary:
    """The single call an executive dashboard needs.

    Every number here is a real aggregate over `rows_after` (or the
    before/after pair for comparisons) -- no field is invented, and returns
    with no usable data for a given KPI are excluded from that KPI's
    denominator rather than counted as zero.
    """
    status_counts: dict[str, int] = {}
    for row in rows_after:
        status = str(row.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    durations: list[float] = []
    for row in rows_after:
        if str(row.get("status", "")).lower() not in _TERMINAL_STATUSES:
            continue
        created = _parse(row.get("created_at"))
        updated = _parse(row.get("updated_at"))
        if created and updated and updated >= created:
            durations.append((updated - created).total_seconds() / 3600)

    median_hours = None
    if durations:
        ordered = sorted(durations)
        mid = len(ordered) // 2
        median_hours = (
            ordered[mid] if len(ordered) % 2
            else (ordered[mid - 1] + ordered[mid]) / 2
        )

    has_value_field = any("item_value_minor" in r for r in rows_before + rows_after)
    total_before = sum(int(r.get("item_value_minor") or 0) for r in rows_before) if has_value_field else None
    total_after = sum(int(r.get("item_value_minor") or 0) for r in rows_after) if has_value_field else None

    lead = None
    if rows_before or rows_after:
        try:
            lead = lead_dimension(
                rows_before, rows_after, value_key="item_value_minor",
                currency=currency, label="Total return value",
                period_before=period_before, period_after=period_after,
            )
        except Exception:  # noqa: BLE001 -- an executive summary must not 500 because the driver-of-change call had nothing to explain
            lead = None

    return ExecutiveSummary(
        period_before=period_before, period_after=period_after,
        total_returns_before=len(rows_before), total_returns_after=len(rows_after),
        total_value_before=total_before, total_value_after=total_after,
        currency=currency, status_breakdown_after=status_counts,
        median_resolution_hours=median_hours, resolution_sample_size=len(durations),
        lead=lead,
    )
