"""PHASE 4 — Tenant isolation, tested at the data-access layer.

WHY THESE EXIST, GIVEN tests/security/test_security.py ALREADY PASSES
--------------------------------------------------------------------
The existing IDOR tests go through the HTTP API, so they only prove that the
*route guards* work. Every route currently calls `_get_owned_return_or_404()`
before touching a child resource, so those tests pass whether or not the store
layer is safe.

That is a discipline guarantee, not a structural one. It holds exactly as long
as every developer remembers the guard on every new endpoint, forever. The
first person to write a route that queries notes directly reintroduces the
leak, and the HTTP tests will still be green.

These tests call `store` functions directly with a foreign org_id — bypassing
the route layer entirely — so they fail if isolation depends on the caller
being polite.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.money import Money
from app.db import store


# ─────────────────────────────── fixtures ────────────────────────────────────

def _make_org(name: str) -> str:
    org = store.create_org({
        "id": str(uuid.uuid4()),
        "name": name,
        "slug": f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        "contact_email": f"{uuid.uuid4().hex[:8]}@example.com",
        "platform_type": "shopify",
        "plan_tier": "starter",
        "is_active": True,
        "risk_threshold": 50.0,
        "rate_limit_per_minute": 60,
        "total_returns": 0,
        "total_revenue_saved_minor": 0,
        "currency": "INR",
        "settings": {},
    })
    return org["id"]


def _make_user(org_id: str) -> str:
    user = store.create_user({
        "org_id": org_id,
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "full_name": "Staff Member",
        "password_hash": "not-a-real-hash",
        "role": "org_admin",
    })
    return user["id"]


def _make_return(org_id: str) -> str:
    return_id = str(uuid.uuid4())
    store.store_return({
        "id": return_id,
        "org_id": org_id,
        "merchant_id": org_id,
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "cust-secret",
        "sku": "SECRET-SKU-001",
        "item_category": "Electronics",
        "item_value_minor": Money.from_major("9999.99", "INR").minor_units,
        "currency": "INR",
        "origin_pincode": "400001",
        "destination_pincode": "411001",
        "weight_grams": 500,
        "volumetric_weight_grams": 600,
        "return_reason_code": "damaged",
        "courier": "Delhivery",
        "payment_mode": "COD",
        "fragile": False,
        "festive": False,
        "condition": "good",
        "status": "pending",
        "raw_payload": {},
        "created_at": datetime.now(UTC),
    })
    return return_id


@pytest.fixture
def two_orgs(app_client):
    """Depends on app_client so the application lifespan creates the schema.

    These tests deliberately bypass HTTP, but the tables still have to exist --
    schema creation lives in the app startup lifespan, not in a conftest
    fixture.
    """
    # Org A owns a return with a prediction and notes. Org B owns nothing.
    org_a = _make_org("Victim Corp")
    org_b = _make_org("Attacker Corp")
    return_id = _make_return(org_a)

    store.store_prediction({
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "predicted_cost_minor": 45000,
        "currency": "INR",
        "risk_score": 77.0,
        "fraud_score": 91.0,          # commercially sensitive
        "damage_probability": 0.4,
        "resale_value_estimate_minor": 30000,
        "carbon_footprint_kg": 2.0,
        "confidence_score": 0.9,
        "routing_decision": "manual_review",
        "model_version": "test",
        "inference_latency_ms": 5.0,
        "feature_snapshot": {},
        "explainability": {},
        "created_at": datetime.now(UTC),
    })
    store.add_return_note({
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "user_id": _make_user(org_a),
        "note": "CONFIDENTIAL: customer suspected of serial fraud.",
        "created_at": datetime.now(UTC),
    })
    return {"org_a": org_a, "org_b": org_b, "return_id": return_id}


# ─────────────────────── the attacks (store layer, no HTTP) ──────────────────

def test_owner_can_read_own_prediction(two_orgs):
    """Control: scoping must not break the legitimate path."""
    pred = store.get_prediction(two_orgs["return_id"], two_orgs["org_a"])
    assert pred is not None
    assert pred["fraud_score"] == 91.0


def test_foreign_org_cannot_read_prediction(two_orgs):
    """A competitor's fraud score is commercially sensitive: it reveals how
    the model rates their customers."""
    assert store.get_prediction(two_orgs["return_id"], two_orgs["org_b"]) is None


def test_foreign_org_cannot_read_notes(two_orgs):
    """Notes are free text written by staff. Assume the worst is in there."""
    notes = store.get_return_notes(two_orgs["return_id"], two_orgs["org_b"])
    assert notes == []


def test_owner_can_read_own_notes(two_orgs):
    notes = store.get_return_notes(two_orgs["return_id"], two_orgs["org_a"])
    assert len(notes) == 1
    assert "CONFIDENTIAL" in notes[0]["note"]


def test_foreign_org_cannot_read_documents(two_orgs):
    """Documents are customer-uploaded evidence photographs."""
    assert store.get_return_documents(two_orgs["return_id"], two_orgs["org_b"]) == []


def test_foreign_org_cannot_read_sla(two_orgs):
    assert store.get_sla_for_return(two_orgs["return_id"], two_orgs["org_b"]) is None


def test_batch_prediction_fetch_filters_foreign_ids(two_orgs):
    """The batch path is where a leak hides best.

    The caller hands over a list of IDs and gets a dict back, so a foreign row
    would blend into legitimate results instead of standing out. Org B asks
    for Org A's return ID directly.
    """
    result = store.get_predictions_for_returns(
        [two_orgs["return_id"]], two_orgs["org_b"]
    )
    assert result == {}

    owner_result = store.get_predictions_for_returns(
        [two_orgs["return_id"]], two_orgs["org_a"]
    )
    assert two_orgs["return_id"] in owner_result


def test_returns_list_is_org_scoped(two_orgs):
    a_returns = store.get_returns_for_org(two_orgs["org_a"])
    b_returns = store.get_returns_for_org(two_orgs["org_b"])
    a_ids = {r["id"] for r in a_returns}
    b_ids = {r["id"] for r in b_returns}
    assert two_orgs["return_id"] in a_ids
    assert two_orgs["return_id"] not in b_ids
    assert a_ids.isdisjoint(b_ids)


def test_dashboard_stats_do_not_aggregate_foreign_money(two_orgs):
    """Aggregates are a subtler leak: no row is exposed, but a competitor's
    revenue figures would be folded into your totals."""
    stats_b = store.get_dashboard_stats(two_orgs["org_b"])
    assert stats_b["total_returns"] == 0
    assert stats_b["revenue_saved"]["minor_units"] == 0


# ───────────────────────── structural guarantee ──────────────────────────────

def test_child_resource_readers_require_org_id(app_client):
    """Guard against regression by inspecting the signatures themselves.

    If someone later adds a default (`org_id: str = None`) to make a call site
    convenient, isolation silently becomes optional again. This test fails on
    that change rather than waiting for a leak to be noticed in production.
    """
    import inspect

    for fn_name in (
        "get_prediction",
        "get_return_notes",
        "get_return_documents",
        "get_sla_for_return",
        "get_predictions_for_returns",
    ):
        sig = inspect.signature(getattr(store, fn_name))
        assert "org_id" in sig.parameters, f"{fn_name} lost its org_id parameter"
        assert sig.parameters["org_id"].default is inspect.Parameter.empty, (
            f"{fn_name}.org_id has a default value -- tenant isolation must "
            f"never be optional. Remove the default and fix the call site."
        )
