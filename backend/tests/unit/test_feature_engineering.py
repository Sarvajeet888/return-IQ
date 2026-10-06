"""PHASE 16 — feature engineering.

The property that matters most here is point-in-time correctness: a feature
computed for a January return must not see February.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import feature_engineering as fe

JAN = datetime(2026, 1, 15)
FEB = datetime(2026, 2, 15)
MAR = datetime(2026, 3, 15)


def _ret(when: datetime, **extra):
    return {"id": f"r-{when.isoformat()}", "created_at": when.isoformat(), **extra}


# ─────────────────────── point-in-time correctness ───────────────────────────

def test_features_ignore_the_future():
    """THE test for this phase.

    `count_customer_returns()` in store.py counts every return a customer has
    ever made, with no date bound. Harmless at scoring time — a return next
    month does not exist yet. Fatal when features are recomputed for training:
    the January row would carry all eleven subsequent returns, and the model
    learns "customers who will return a lot, return a lot".
    """
    history = [_ret(JAN), _ret(FEB), _ret(MAR)]

    as_of_feb = fe.customer_features(history, 10, as_of=FEB)
    assert as_of_feb["customer_return_count"] == 1        # only January

    as_of_mar = fe.customer_features(history, 10, as_of=MAR)
    assert as_of_mar["customer_return_count"] == 2        # January + February


def test_a_return_does_not_count_itself():
    """Strictly before, not before-or-equal. A record with the same timestamp
    is at best simultaneous and at worst the return being scored."""
    assert fe.customer_features([_ret(FEB)], 10, as_of=FEB)["customer_return_count"] == 0


def test_as_of_is_mandatory_and_typed():
    """An optional correctness parameter is one somebody forgets, and
    forgetting this one produces a model that evaluates beautifully and fails
    in production."""
    with pytest.raises(TypeError, match="point-in-time"):
        fe.build_features({}, as_of="2026-02-15")

    with pytest.raises(TypeError):
        fe.build_features({})          # no as_of at all


def test_product_history_is_also_point_in_time():
    history = [_ret(JAN, return_reason_code="damaged"), _ret(MAR, return_reason_code="damaged")]
    assert fe.product_features(history, as_of=FEB)["sku_return_count"] == 1


def test_evidence_is_also_point_in_time():
    """Evidence uploaded after the decision must not inform the decision."""
    docs = [
        {"created_at": JAN.isoformat(), "evidence_type": "damage_photo", "source": "customer"},
        {"created_at": MAR.isoformat(), "evidence_type": "damage_photo", "source": "customer"},
    ]
    result = fe.return_features({}, docs, as_of=FEB)
    assert result["evidence_count"] == 1


# ─────────────────── first-occurrence is a distinct state ────────────────────

def test_first_time_returner_is_not_a_zero_rate():
    """Encoding "no history" as 0.0 makes a first-time returner
    indistinguishable from someone with fifty orders and no returns — a very
    different risk."""
    result = fe.customer_features([], 0, as_of=FEB)
    assert result["customer_is_first_return"] is True
    assert result["customer_return_ratio"] is None
    assert result["customer_days_since_last_return"] is None


def test_return_ratio_is_none_when_order_count_is_unknown():
    """ReturnIQ sees returns, not orders. Assuming a denominator would produce
    a ratio that silently claims every order was returned."""
    result = fe.customer_features([_ret(JAN)], 0, as_of=FEB)
    assert result["customer_return_ratio"] is None


def test_return_ratio_computed_when_orders_are_known():
    result = fe.customer_features([_ret(JAN), _ret(JAN)], 10, as_of=FEB)
    assert result["customer_return_ratio"] == 0.2


def test_first_seen_sku_is_flagged():
    assert fe.product_features([], as_of=FEB)["sku_is_first_return"] is True


# ──────────────────────────── velocity signals ───────────────────────────────

def test_recent_velocity_is_separated_from_lifetime_volume():
    """Five returns this month is a different signal from five over three
    years, and lifetime count cannot distinguish them."""
    old = [_ret(FEB - timedelta(days=400)) for _ in range(5)]
    recent = [_ret(FEB - timedelta(days=d)) for d in (3, 8, 15, 22)]

    result = fe.customer_features(old + recent, 100, as_of=FEB)
    assert result["customer_return_count"] == 9
    assert result["customer_returns_last_30d"] == 4
    assert result["customer_returns_last_90d"] == 4


def test_days_since_last_return():
    result = fe.customer_features([_ret(FEB - timedelta(days=12))], 10, as_of=FEB)
    assert result["customer_days_since_last_return"] == 12


def test_average_gap_between_returns():
    dates = [FEB - timedelta(days=d) for d in (60, 40, 20)]
    result = fe.customer_features([_ret(d) for d in dates], 10, as_of=FEB)
    assert result["customer_avg_days_between_returns"] == 20.0


def test_average_gap_is_none_with_a_single_return():
    result = fe.customer_features([_ret(JAN)], 10, as_of=FEB)
    assert result["customer_avg_days_between_returns"] is None


# ────────────────────────── product-side signals ─────────────────────────────

def test_sku_damage_rate_separates_product_from_customer_problems():
    """A SKU returned constantly is a product problem. Without this, every
    return of a chronically-defective item scores as suspicious customer
    behaviour."""
    history = [
        _ret(JAN, return_reason_code="damaged"),
        _ret(JAN, return_reason_code="damaged"),
        _ret(JAN, return_reason_code="size_issue"),
        _ret(JAN, return_reason_code="damaged"),
    ]
    assert fe.product_features(history, as_of=FEB)["sku_damage_rate"] == 0.75


# ──────────────────────────── evidence signals ───────────────────────────────

def test_damage_claimed_without_a_photo_is_surfaced():
    """Available before anyone inspects the item, and worth stating rather
    than leaving a reviewer to infer."""
    result = fe.return_features(
        {"return_reason_code": "damaged"}, [], as_of=FEB,
    )
    assert result["damage_claimed_without_photo"] is True
    assert result["has_evidence"] is False


def test_damage_with_a_photo_is_not_flagged():
    docs = [{"created_at": JAN.isoformat(), "evidence_type": "damage_photo", "source": "customer"}]
    result = fe.return_features({"return_reason_code": "damaged"}, docs, as_of=FEB)
    assert result["damage_claimed_without_photo"] is False
    assert result["damage_photo_count"] == 1


def test_non_damage_reason_is_never_flagged_for_missing_photos():
    result = fe.return_features({"return_reason_code": "size_issue"}, [], as_of=FEB)
    assert result["damage_claimed_without_photo"] is False


# ─────────────────────────── temporal features ───────────────────────────────

def test_festive_window_is_detected():
    """Return volume, reason mix and processing time all shift around festive
    periods; a model ignoring them reads seasonal spikes as behaviour change."""
    diwali = fe.temporal_features(as_of=datetime(2026, 10, 20))
    assert diwali["is_festive_window"] is True
    assert diwali["festive_window"] == "diwali_season"


def test_ordinary_period_is_not_festive():
    assert fe.temporal_features(as_of=datetime(2026, 6, 10))["is_festive_window"] is False


def test_weekend_detection():
    assert fe.temporal_features(as_of=datetime(2026, 8, 15))["is_weekend"] is True   # Saturday
    assert fe.temporal_features(as_of=datetime(2026, 8, 13))["is_weekend"] is False  # Thursday


# ──────────────────────────── assembly & coverage ────────────────────────────

def test_build_features_assembles_every_group():
    result = fe.build_features(
        {"return_reason_code": "damaged", "delivered_at": JAN.isoformat()},
        as_of=FEB,
        customer_returns=[_ret(JAN)],
        sku_returns=[_ret(JAN, return_reason_code="damaged")],
        evidence_documents=[],
        customer_orders_count=10,
    )
    f = result.features
    assert "customer_return_count" in f
    assert "sku_damage_rate" in f
    assert "is_festive_window" in f
    assert "days_since_delivery" in f
    assert result.as_of == FEB


def test_coverage_reports_which_groups_had_data():
    """A model evaluated without knowing half its rows had no customer history
    is being evaluated on a population that does not exist."""
    result = fe.build_features({}, as_of=FEB, customer_returns=[_ret(JAN)])
    assert result.coverage["customer"] == "present"
    assert result.coverage["product"] == "none"
    assert result.coverage["temporal"] == "always"


def test_result_carries_its_cutoff_for_review():
    """Not bookkeeping: it lets a reviewer confirm a training row used a
    legitimate cutoff rather than taking it on trust."""
    payload = fe.build_features({}, as_of=FEB).as_dict()
    assert payload["as_of"] == FEB.isoformat()


def test_unparseable_dates_are_skipped_not_crashed():
    history = [{"created_at": "not-a-date"}, _ret(JAN)]
    assert fe.customer_features(history, 10, as_of=FEB)["customer_return_count"] == 1
