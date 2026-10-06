"""PHASE 16 — feature engineering.

WHY THIS IS NOT BLOCKED BY THE DATA PROBLEM
-------------------------------------------
Mega Phase 2's model work needs *labels* — confirmed outcomes saying what
actually happened. Features are different: they are computed from operational
data every merchant already has the moment they process a second return.
Building them now means the inputs are ready when labels arrive, and several
of them improve the rule-based scores today.

THE BUG THIS MODULE EXISTS TO PREVENT
-------------------------------------
`count_customer_returns()` counts *every* return a customer has ever made,
with no date bound. At scoring time that is harmless — a return made next
month does not exist yet. The damage appears the moment features are
recomputed for training:

    Return from January, scored during training in December
      -> customer_return_rate reflects all 11 subsequent returns
      -> the model learns "customers who will return a lot, return a lot"
      -> evaluation looks excellent, production performs at chance

This is **point-in-time leakage**, and it is the most common way an ML
pipeline lies to the people building it. Phase 15 catches leaky *columns*;
this catches leaky *values in legitimate columns*, which is far harder to see
because the feature name is entirely reasonable.

Every function here takes an `as_of` timestamp and considers only records
strictly before it. That parameter is mandatory, with no default, for the same
reason `org_id` was made mandatory in Phase 4: an optional correctness
parameter is one somebody forgets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

__all__ = [
    "FeatureSet",
    "customer_features",
    "product_features",
    "temporal_features",
    "return_features",
    "build_features",
]


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        text = str(value).replace("Z", "").replace(" ", "T", 1)
        return datetime.fromisoformat(text.split("+")[0])
    except (ValueError, TypeError):
        return None


def _before(records: list[dict], as_of: datetime, field: str = "created_at") -> list[dict]:
    """Records strictly before `as_of`.

    Strictly before, not before-or-equal: a record with the same timestamp as
    the return being scored is at best simultaneous and at worst the return
    itself. Including it would let a return contribute to its own history.
    """
    out = []
    for r in records:
        when = _parse(r.get(field))
        if when is not None and when < as_of:
            out.append(r)
    return out


# Indian festive windows drive both order and return volume, and a returns
# model that ignores them mistakes seasonal spikes for behaviour change.
# Month-day pairs kept approximate on purpose: Diwali moves each year, and a
# hardcoded exact date would be wrong in most of them.
_FESTIVE_WINDOWS: Final[list[tuple[int, int, int, str]]] = [
    (10, 1, 11, 30, "diwali_season"),      # Oct-Nov
    (12, 15, 12, 31, "year_end"),
    (1, 1, 1, 26, "new_year_republic"),
    (8, 1, 8, 31, "independence_sales"),
]


@dataclass(frozen=True)
class FeatureSet:
    """Computed features plus the timestamp they were computed as of.

    Carrying `as_of` in the result is not bookkeeping. It is what lets a
    reviewer confirm a training row was built with a legitimate cutoff rather
    than taking it on trust.
    """

    features: dict[str, Any]
    as_of: datetime
    coverage: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "features": self.features,
            "as_of": self.as_of.isoformat(),
            "coverage": self.coverage,
        }


def customer_features(
    customer_returns: list[dict],
    customer_orders_count: int,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Behavioural history for one customer, as known at `as_of`.

    `customer_orders_count` is passed in rather than derived because
    ReturnIQ does not own the order table — it sees returns. Pretending
    otherwise would produce a return-ratio that silently assumes every order
    was returned.
    """
    history = _before(customer_returns, as_of)
    n = len(history)

    if n == 0:
        # A first-time returner is a distinct state, not a customer with a
        # rate of zero. Encoding it as 0.0 makes them indistinguishable from
        # someone with fifty orders and no returns, who is a very different
        # risk.
        return {
            "customer_return_count": 0,
            "customer_return_ratio": None,
            "customer_days_since_last_return": None,
            "customer_returns_last_30d": 0,
            "customer_returns_last_90d": 0,
            "customer_is_first_return": True,
            "customer_avg_days_between_returns": None,
        }

    dates = sorted(d for d in (_parse(r.get("created_at")) for r in history) if d)
    last = dates[-1] if dates else None

    gaps = [(b - a).days for a, b in zip(dates, dates[1:])] if len(dates) > 1 else []

    return {
        "customer_return_count": n,
        # None, not a division by zero, when the order count is unknown.
        "customer_return_ratio": (
            round(n / customer_orders_count, 4) if customer_orders_count else None
        ),
        "customer_days_since_last_return": (as_of - last).days if last else None,
        # Velocity matters more than lifetime volume for fraud: five returns
        # this month is a different signal from five returns over three years.
        "customer_returns_last_30d": len([d for d in dates if (as_of - d).days <= 30]),
        "customer_returns_last_90d": len([d for d in dates if (as_of - d).days <= 90]),
        "customer_is_first_return": False,
        "customer_avg_days_between_returns": (
            round(sum(gaps) / len(gaps), 1) if gaps else None
        ),
    }


def product_features(sku_returns: list[dict], *, as_of: datetime) -> dict[str, Any]:
    """History for one SKU, as known at `as_of`.

    A SKU that is returned constantly is a product problem, not a customer
    problem — and telling those apart is most of what a returns product is
    for. Without this, every return of a chronically-defective item scores as
    suspicious customer behaviour.
    """
    history = _before(sku_returns, as_of)
    n = len(history)

    if n == 0:
        return {
            "sku_return_count": 0,
            "sku_damage_rate": None,
            "sku_is_first_return": True,
        }

    damaged = sum(
        1 for r in history
        if str(r.get("return_reason_code", "")).lower() in {"damaged", "defective", "quality_issue"}
    )

    return {
        "sku_return_count": n,
        "sku_damage_rate": round(damaged / n, 4),
        "sku_is_first_return": False,
    }


def temporal_features(*, as_of: datetime) -> dict[str, Any]:
    """Calendar context.

    Cheap to compute and genuinely predictive: return volume, reason mix and
    processing time all shift around festive periods.
    """
    season = None
    for start_m, start_d, end_m, end_d, name in _FESTIVE_WINDOWS:
        start = (start_m, start_d)
        end = (end_m, end_d)
        if start <= (as_of.month, as_of.day) <= end:
            season = name
            break

    return {
        "day_of_week": as_of.weekday(),          # 0 = Monday
        "is_weekend": as_of.weekday() >= 5,
        "day_of_month": as_of.day,
        "month": as_of.month,
        "quarter": (as_of.month - 1) // 3 + 1,
        "festive_window": season,
        "is_festive_window": season is not None,
    }


def return_features(
    return_data: dict,
    evidence_documents: list[dict],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Facts about this return itself.

    Evidence availability is included because it is one of the few signals
    available *before* anyone inspects the item. A damage claim with no
    photograph is a different proposition from one with three.
    """
    delivered = _parse(return_data.get("delivered_at"))
    evidence = _before(evidence_documents, as_of)

    damage_photos = sum(
        1 for d in evidence
        if d.get("evidence_type") == "damage_photo"
        or d.get("is_damage_photo")
    )
    customer_supplied = sum(1 for d in evidence if d.get("source") == "customer")

    return {
        "days_since_delivery": (as_of - delivered).days if delivered else None,
        "evidence_count": len(evidence),
        "has_evidence": len(evidence) > 0,
        "damage_photo_count": damage_photos,
        "customer_evidence_count": customer_supplied,
        # A damage claim with no photograph. Not proof of anything, but the
        # kind of thing a reviewer should see stated rather than infer.
        "damage_claimed_without_photo": (
            str(return_data.get("return_reason_code", "")).lower() in {"damaged", "defective"}
            and damage_photos == 0
        ),
    }


def build_features(
    return_data: dict,
    *,
    as_of: datetime,
    customer_returns: list[dict] | None = None,
    sku_returns: list[dict] | None = None,
    evidence_documents: list[dict] | None = None,
    customer_orders_count: int = 0,
) -> FeatureSet:
    """Assemble every feature group for one return.

    `as_of` is mandatory and has no default. An optional correctness parameter
    is one somebody forgets, and forgetting it here produces a model that
    evaluates beautifully and fails in production — the most expensive
    possible failure mode, because nothing about it looks like a bug.
    """
    if not isinstance(as_of, datetime):
        raise TypeError(
            "as_of must be a datetime. Features are point-in-time: without a "
            "cutoff, historical rows are computed using data from their own "
            "future, and the resulting model learns to predict the past."
        )

    as_of = as_of.replace(tzinfo=None)

    features: dict[str, Any] = {}
    features.update(customer_features(
        customer_returns or [], customer_orders_count, as_of=as_of,
    ))
    features.update(product_features(sku_returns or [], as_of=as_of))
    features.update(temporal_features(as_of=as_of))
    features.update(return_features(
        return_data, evidence_documents or [], as_of=as_of,
    ))

    # Which groups had data to work with. A model evaluated without knowing
    # that half its rows had no customer history is being evaluated on a
    # population that does not exist.
    coverage = {
        "customer": "present" if customer_returns else "none",
        "product": "present" if sku_returns else "none",
        "evidence": "present" if evidence_documents else "none",
        "temporal": "always",
    }

    return FeatureSet(features=features, as_of=as_of, coverage=coverage)
