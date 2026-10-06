"""PHASE 35 — grounded analytics: change decomposition.

THE ROADMAP'S GATE
-------------------
> "Only after the underlying analytics are trustworthy... ReturnIQ should
> answer from actual structured data... Don't let the LLM invent metrics."

That gate is why this phase is not simply blocked like Phases 17-19. Those
needed a trained model. This one needs real observed data and exact
arithmetic -- both of which already exist. The live endpoint below decomposes
`item_value_minor`, an amount customers actually returned, not a model's
prediction. If someone chooses to decompose a predicted field instead, that
is the caller's decision and Phase 14's provenance labelling still applies
to whatever produced the number -- this module does not launder that.

TWO GUARANTEES THIS MODULE ENFORCES STRUCTURALLY
--------------------------------------------------
**Reconciliation is not approximate.** Every other "trust" mechanism in this
project (Phase 18's benchmark, Phase 20's intervals, Phase 27's drift) deals
with statistical estimates and states a margin of error. This module does
not estimate anything -- a segment's contribution to a change is a sum over
the rows that actually happened, so the parts equal the whole exactly, not
approximately. `reconciles` is a hard equality check in currency mode.

**The narrative cannot drift from the numbers, because there is no
generation step.** `narrative()` is string interpolation over fields already
computed and tested. There is no free-text model in this loop at all: the
"don't let the LLM invent metrics" requirement is met by there being no LLM
between the arithmetic and the answer. A natural-language front end that
maps a typed question to one of these calls could sit in front of this
module later, but whatever sits there must relay this module's numbers
verbatim -- it must never be permitted to phrase a percentage itself.

THE BUG THIS MODULE'S DESIGN AVOIDS -- FOUND IN THE ROADMAP'S OWN EXAMPLE
--------------------------------------------------------------------------
The roadmap's illustration lists four "contributors" together as if they
summed to one 14.2% figure:

    Electronics: +21%
    Damage returns: +27%
    Region X: +18%
    Reverse shipping: +9%

These are four *different partitions* of the same returns -- category,
reason, region, cost type -- not four slices of one pie. A single return can
be Electronics AND a damage claim AND from Region X simultaneously, so its
cost increase gets counted once under each lens. Read naively, the list
implies roughly 75 percentage points of explanation for a 14.2% change,
which overstates the picture by nearly 5x.

`decompose_change()` therefore only ever reports contributions within ONE
dimension, where they are a true partition and provably sum to the total.
`compare_dimensions()` runs several dimensions side by side with an explicit
warning that they are not additive with each other -- and
`test_insight_engine.py` constructs a scenario where two dimensions each
independently claim 100% of the same increase, to make the point mechanically
rather than only in prose.

EXACT VS. ESTIMATED, A DISTINCTION WORTH MAKING PRECISELY
-------------------------------------------------------------
Phase 19 hid segment metrics below a row-count floor because a metric like
MAE on 3 rows is a poor *estimate* of the model's typical error on a wider
population -- it is a statistical inference problem.

A segment's contribution to a change is not an estimate of anything. It is
an exact sum over the actual rows that happened. Hiding it below a floor
would be dishonest -- the number is not noisy, it is simply small. So this
module always reports the real figure, and instead attaches
`low_sample_warning` when a segment's count is thin: the risk is not that
the number is wrong, it is that a reader extrapolates two returns into a
trend. The distinction matters and the field names say which is happening.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.core.money import Money
from app.ml.evaluation import MIN_SEGMENT_ROWS  # same floor, same reasoning as Phase 19

__all__ = [
    "InsightError",
    "SegmentContribution",
    "ChangeDecomposition",
    "VALID_DIMENSIONS",
    "decompose_change",
    "compare_dimensions",
    "narrative",
]


class InsightError(ValueError):
    """A question that cannot be answered from the data available."""


# The allowlist a "dimension" is checked against. Kept small and explicit for
# the same reason Phase 32 validated workflow conditions against a known set:
# an unrecognised dimension should refuse loudly, not silently group
# everything into one bucket.
VALID_DIMENSIONS: Final[frozenset[str]] = frozenset({
    "item_category", "courier", "payment_mode", "return_reason_code",
})


def _sum(rows: list[dict[str, Any]], value_key: str, *, exact: bool) -> int | float:
    """Total a field across rows.

    `exact=True` accumulates as int (minor units) so 10,000 rows of exact
    money never drift, the same lesson Phase 3 encoded in the Money type.
    `exact=False` is for plain numeric fields with no currency meaning.
    """
    total: int | float = 0 if exact else 0.0
    for row in rows:
        value = row.get(value_key)
        if value is None:
            continue
        total += int(value) if exact else float(value)
    return total


@dataclass(frozen=True)
class SegmentContribution:
    """One segment's exact share of a change."""

    dimension: str
    value: str
    before_total: int | float
    after_total: int | float
    before_count: int
    after_count: int
    absolute_change: int | float
    # Share of the TOTAL change this segment accounts for. Always computed
    # when the total changed at all -- this is exact arithmetic, not an
    # estimate, so there is no reason to withhold it.
    contribution_pct_of_change: float | None
    # This segment's OWN growth rate. A materially different concept from
    # the above, and the field names are deliberately distinct so the two
    # are never confused in code that consumes this.
    segment_growth_pct: float | None
    status: str  # "measured" | "new_this_period" | "discontinued"
    # Not a suppression flag. The number above is exact either way; this
    # says the exact number describes very few returns, so a reader should
    # treat it as an anecdote rather than a pattern.
    low_sample_warning: bool

    def as_dict(self, currency: str | None) -> dict[str, Any]:
        def fmt(amount: int | float) -> Any:
            if currency:
                return Money(int(amount), currency).as_dict()
            return round(amount, 2)

        return {
            "value": self.value,
            "before": fmt(self.before_total),
            "after": fmt(self.after_total),
            "before_count": self.before_count,
            "after_count": self.after_count,
            "absolute_change": fmt(self.absolute_change),
            "contribution_pct_of_change": (
                round(self.contribution_pct_of_change, 1)
                if self.contribution_pct_of_change is not None else None
            ),
            "segment_growth_pct": (
                round(self.segment_growth_pct, 1)
                if self.segment_growth_pct is not None else None
            ),
            "status": self.status,
            "low_sample_warning": self.low_sample_warning,
        }


@dataclass
class ChangeDecomposition:
    label: str
    dimension: str
    value_key: str
    currency: str | None
    period_before: tuple[str, str]
    period_after: tuple[str, str]
    total_before: int | float
    total_after: int | float
    total_absolute_change: int | float
    total_pct_change: float | None
    segments: list[SegmentContribution] = field(default_factory=list)
    reconciles: bool = True
    row_count_before: int = 0
    row_count_after: int = 0

    def as_dict(self) -> dict[str, Any]:
        def fmt(amount: int | float) -> Any:
            if self.currency:
                return Money(int(amount), self.currency).as_dict()
            return round(amount, 2)

        return {
            "label": self.label,
            "dimension": self.dimension,
            "period_before": list(self.period_before),
            "period_after": list(self.period_after),
            "total_before": fmt(self.total_before),
            "total_after": fmt(self.total_after),
            "total_absolute_change": fmt(self.total_absolute_change),
            "total_pct_change": (
                round(self.total_pct_change, 1)
                if self.total_pct_change is not None else None
            ),
            "segments": [s.as_dict(self.currency) for s in self.segments],
            "reconciles": self.reconciles,
            "provenance": {
                "value_key": self.value_key,
                "dimension": self.dimension,
                "rows_before": self.row_count_before,
                "rows_after": self.row_count_after,
            },
        }


def decompose_change(
    rows_before: list[dict[str, Any]],
    rows_after: list[dict[str, Any]],
    *,
    value_key: str,
    dimension: str,
    currency: str | None = None,
    min_sample: int = MIN_SEGMENT_ROWS,
    label: str = "Value",
    period_before: tuple[str, str] = ("", ""),
    period_after: tuple[str, str] = ("", ""),
) -> ChangeDecomposition:
    """Explain a change in `value_key` between two periods, by `dimension`.

    `rows_before`/`rows_after` are the caller's job to have already scoped to
    one organization and one time window -- this function trusts the split it
    is given, the same contract `evaluate_by_segment` (Phase 19) and
    `customer_features` (Phase 16) use.
    """
    if dimension not in VALID_DIMENSIONS:
        raise InsightError(
            f"{dimension!r} is not a dimension this can break down by. "
            f"Available: {', '.join(sorted(VALID_DIMENSIONS))}."
        )

    exact = currency is not None
    total_before = _sum(rows_before, value_key, exact=exact)
    total_after = _sum(rows_after, value_key, exact=exact)
    total_change = total_after - total_before

    if total_before == 0 and total_after == 0:
        raise InsightError(
            "Neither period has any data for this value, so there is nothing "
            "to explain. Widen the date range or check the dimension is "
            "correct."
        )

    total_pct = (total_change / total_before * 100) if total_before else None

    groups_before: dict[str, list[dict[str, Any]]] = {}
    for row in rows_before:
        groups_before.setdefault(str(row.get(dimension, "unknown")), []).append(row)
    groups_after: dict[str, list[dict[str, Any]]] = {}
    for row in rows_after:
        groups_after.setdefault(str(row.get(dimension, "unknown")), []).append(row)

    segments: list[SegmentContribution] = []
    for key in sorted(set(groups_before) | set(groups_after)):
        b_rows = groups_before.get(key, [])
        a_rows = groups_after.get(key, [])
        b_total = _sum(b_rows, value_key, exact=exact)
        a_total = _sum(a_rows, value_key, exact=exact)
        change = a_total - b_total

        if not b_rows and a_rows:
            status = "new_this_period"
        elif b_rows and not a_rows:
            status = "discontinued"
        else:
            status = "measured"

        contribution_pct = (change / total_change * 100) if total_change else None
        growth_pct = (change / b_total * 100) if b_total else None

        low_sample = (
            (0 < len(b_rows) < min_sample) or (0 < len(a_rows) < min_sample)
        )

        segments.append(SegmentContribution(
            dimension=dimension, value=key,
            before_total=b_total, after_total=a_total,
            before_count=len(b_rows), after_count=len(a_rows),
            absolute_change=change,
            contribution_pct_of_change=contribution_pct,
            segment_growth_pct=growth_pct,
            status=status, low_sample_warning=low_sample,
        ))

    # Biggest driver first, by magnitude regardless of direction -- a segment
    # that fell sharply is as important to surface as one that rose sharply.
    segments.sort(key=lambda s: -abs(s.absolute_change))

    reconciled = sum(s.absolute_change for s in segments)
    reconciles = (reconciled == total_change) if exact else abs(reconciled - total_change) < 1e-6

    return ChangeDecomposition(
        label=label, dimension=dimension, value_key=value_key, currency=currency,
        period_before=period_before, period_after=period_after,
        total_before=total_before, total_after=total_after,
        total_absolute_change=total_change, total_pct_change=total_pct,
        segments=segments, reconciles=reconciles,
        row_count_before=len(rows_before), row_count_after=len(rows_after),
    )


def compare_dimensions(
    rows_before: list[dict[str, Any]],
    rows_after: list[dict[str, Any]],
    *,
    value_key: str,
    dimensions: list[str],
    currency: str | None = None,
    min_sample: int = MIN_SEGMENT_ROWS,
    label: str = "Value",
    period_before: tuple[str, str] = ("", ""),
    period_after: tuple[str, str] = ("", ""),
) -> dict[str, Any]:
    """Decompose the same change across several dimensions, with the warning
    a merchant needs to read them correctly.

    Each dimension's own breakdown reconciles exactly. What is NOT true, and
    what this function exists to say plainly, is that the dimensions sum to
    anything when compared to each other.
    """
    results = {
        dim: decompose_change(
            rows_before, rows_after, value_key=value_key, dimension=dim,
            currency=currency, min_sample=min_sample, label=label,
            period_before=period_before, period_after=period_after,
        )
        for dim in dimensions
    }
    return {
        "dimensions": {dim: result.as_dict() for dim, result in results.items()},
        "note": (
            "Each dimension above partitions the SAME returns a different "
            "way. A single return can belong to more than one segment across "
            "dimensions -- for example the same return can be both "
            "'Electronics' and a damage claim. Contribution percentages are "
            "additive only WITHIN one dimension; they must not be summed or "
            "compared ACROSS dimensions. A segment that looks large in two "
            "different breakdowns may describe the same underlying returns "
            "rather than two separate causes."
        ),
    }


def narrative(decomposition: ChangeDecomposition) -> str:
    """Render a decomposition as prose, built entirely from its own fields.

    Every number here is a direct interpolation of an already-computed,
    already-tested attribute. There is no branch in this function that
    derives a new figure -- which is the property that makes it safe to call
    this the answer to "why did X change": nothing between the arithmetic
    and the reader can alter what it says.
    """
    d = decomposition

    def fmt(amount: int | float) -> str:
        if d.currency:
            return Money(int(amount), d.currency).format()
        return f"{amount:,.2f}"

    if d.total_absolute_change > 0:
        direction = "increased"
    elif d.total_absolute_change < 0:
        direction = "decreased"
    else:
        direction = "did not change"

    pct_text = (
        f"{abs(d.total_pct_change):.1f}%"
        if d.total_pct_change is not None
        else "an unmeasurable amount (no baseline in the earlier period)"
    )

    lines = [
        f"{d.label} {direction} by {pct_text} ({fmt(d.total_absolute_change)}), "
        f"comparing {d.period_after[0] or 'the recent period'}"
        f"{' to ' + d.period_after[1] if d.period_after[1] else ''} against "
        f"{d.period_before[0] or 'the prior period'}"
        f"{' to ' + d.period_before[1] if d.period_before[1] else ''}."
    ]

    contributing = [s for s in d.segments if s.absolute_change != 0]
    if contributing:
        lines.append("Primary contributors:")
        for s in contributing[:5]:
            tag = " (new this period)" if s.status == "new_this_period" else (
                " (discontinued)" if s.status == "discontinued" else ""
            )
            warn = " -- based on very few returns" if s.low_sample_warning else ""
            if s.contribution_pct_of_change is not None:
                lines.append(
                    f"  {s.value}: {s.contribution_pct_of_change:+.1f}% of the "
                    f"change ({fmt(s.absolute_change)}){tag}{warn}"
                )
            else:
                lines.append(f"  {s.value}: {fmt(s.absolute_change)}{tag}{warn}")

    if not d.reconciles:
        lines.append(
            "NOTE: the segment contributions above do not sum to the total "
            "change. Treat this figure as unverified until that is fixed."
        )

    return "\n".join(lines)
