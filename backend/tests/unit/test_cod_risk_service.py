"""
Unit tests for the COD pre-shipment risk scoring service.

Mirrors test_cache.py's style: mock the store layer so these test pure
scoring logic, not the database.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from app.core.money import Money
from app.services import cod_risk_service


@pytest.fixture(autouse=True)
def _default_pincode_stats():
    """By default, pretend this pincode has no return history at all --
    individual tests override this when they specifically want to exercise
    the pincode-risk rule."""
    with patch.object(cod_risk_service.store, "get_pincode_fraud_stats",
                       return_value={"sample_count": 0, "avg_fraud_score": 0.0}):
        yield


def _fake_customer(**overrides) -> dict:
    base = {
        "id": "cust-1",
        "risk_level": "low",
        "is_blacklisted": False,
        "total_returns": 0,
        "total_orders": 0,
        "clv_minor": 0,
    }
    base.update(overrides)
    return base


def _score(**kwargs):
    defaults = dict(
        org_id="org-1",
        platform_order_id="ORD-1",
        customer_phone="9876500000",
        customer_name="Test Customer",
        delivery_address="1 Test Street",
        delivery_pincode="500001",
        order_value=1000.0,
    )
    defaults.update(kwargs)
    # Phase 3: the service takes Money. Coerce here so each test can keep
    # writing a readable rupee literal instead of paise everywhere.
    ov = defaults["order_value"]
    if not isinstance(ov, Money):
        defaults["order_value"] = Money.from_major(f"{ov:.2f}", "INR")
    return cod_risk_service.score_cod_order(**defaults)


# ── Low risk: no history, no red flags ────────────────────────────────────────
def test_first_time_low_value_order_scores_low():
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=None), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=[]), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-1"}):
        result = _score(order_value=500.0)  # below the new-customer-high-value threshold
    assert result["risk_band"] == "low"
    assert result["flags"] == []


# ── Blacklisted customer must always be flagged, regardless of everything else
def test_blacklisted_customer_is_always_flagged():
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=_fake_customer(is_blacklisted=True)), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=[]), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-2"}):
        result = _score()
    codes = [f["code"] for f in result["flags"]]
    assert "CUSTOMER_BLACKLISTED" in codes
    assert result["risk_band"] == "high"


# ── Existing ReturnIQ risk_level is reused, not recomputed from scratch ───────
def test_existing_high_risk_customer_contributes_to_score():
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=_fake_customer(risk_level="high")), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=[]), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-3"}):
        result = _score()
    codes = [f["code"] for f in result["flags"]]
    assert "EXISTING_CUSTOMER_RISK_LEVEL" in codes


# ── Shared address across multiple names is a real, independent signal ───────
def test_shared_address_multiple_names_is_flagged():
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=None), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=["Someone Else"]), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-4"}):
        result = _score(order_value=500.0, customer_name="This Customer")
    codes = [f["code"] for f in result["flags"]]
    assert "SHARED_ADDRESS_MULTIPLE_NAMES" in codes


# ── Multiple weak signals together should compound, not just sum quietly ─────
def test_multiple_signals_trigger_compounding_bonus():
    risky_pincode_stats = {"sample_count": 5, "avg_fraud_score": 65.0}  # real historical signal
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=None), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=[]), \
         patch.object(cod_risk_service.store, "get_pincode_fraud_stats", return_value=risky_pincode_stats), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-5"}):
        result = _score(order_value=4500.0, delivery_pincode="500001")  # new customer + high value + risky pincode history
    codes = [f["code"] for f in result["flags"]]
    assert "MULTIPLE_SIGNALS_COMPOUNDING" in codes
    assert result["risk_band"] == "high"


# ── A pincode with too few past returns must NOT be judged risky off noise ────
def test_pincode_with_insufficient_sample_size_is_not_flagged():
    thin_pincode_stats = {"sample_count": 1, "avg_fraud_score": 90.0}  # one bad return isn't a pattern
    with patch.object(cod_risk_service.store, "get_customer_by_phone", return_value=None), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=[]), \
         patch.object(cod_risk_service.store, "get_pincode_fraud_stats", return_value=thin_pincode_stats), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-7"}):
        result = _score(order_value=500.0, delivery_pincode="500001")
    codes = [f["code"] for f in result["flags"]]
    assert "HIGH_RISK_PINCODE" not in codes


# ── Score is always capped at 100, never overflows ────────────────────────────
def test_score_never_exceeds_100():
    with patch.object(cod_risk_service.store, "get_customer_by_phone",
                       return_value=_fake_customer(is_blacklisted=True, risk_level="high", total_returns=10)), \
         patch.object(cod_risk_service.store, "get_recent_names_at_address", return_value=["A", "B", "C"]), \
         patch.object(cod_risk_service.store, "create_cod_risk_assessment", side_effect=lambda d: {**d, "id": "assess-6"}):
        result = _score(order_value=9999.0, delivery_pincode="110091")
    assert result["risk_score"] <= 100.0
