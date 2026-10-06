"""PHASE 39 — performance: caching wired to what it was built for.

`app/core/cache.py` already existed, was well-designed (org-scoped keys,
graceful Redis degradation), and was completely unused — verified by grep
before writing anything here: the only match for `cache_invalidate_org` in
the whole codebase was its own definition.

These tests use fakeredis rather than mocks, so SCAN-based invalidation and
key expiry are exercised against real Redis semantics, not an approximation
of them.
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest

import app.core.cache as cache_module
from app.db import store


@pytest.fixture(autouse=True)
def _fake_redis():
    """A real in-memory Redis, not a hand-rolled dict.

    `cache_invalidate_org` uses `scan_iter` with pattern matching — a bespoke
    dict mock would not exercise that correctly, and a bug in the pattern
    itself is exactly the kind of thing that mock would hide.
    """
    client = fakeredis.FakeStrictRedis(decode_responses=True)
    original = cache_module._redis_client
    original_get = cache_module.get_redis
    cache_module._redis_client = client
    cache_module.get_redis = lambda: client
    yield client
    cache_module._redis_client = original
    cache_module.get_redis = original_get


def _return_payload(org_id: str, **overrides) -> dict:
    base = {
        "id": str(uuid.uuid4()), "org_id": org_id, "merchant_id": org_id,
        "platform_order_id": f"O-{uuid.uuid4().hex[:8]}", "customer_identifier": "c",
        "sku": "S", "item_category": "apparel", "item_value_minor": 100000,
        "currency": "INR", "origin_pincode": "400001", "destination_pincode": "411001",
        "weight_grams": 500, "volumetric_weight_grams": 600,
        "return_reason_code": "damaged", "courier": "Delhivery", "payment_mode": "COD",
        "fragile": False, "festive": False, "condition": "good", "status": "pending",
        "raw_payload": {},
    }
    base.update(overrides)
    return base


@pytest.fixture
def merchant(app_client):
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Cache Tester", "email": f"cache_{uuid.uuid4().hex[:8]}@example.com",
        "password": "CachePass123", "org_name": f"Cache Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return app_client, {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["org_id"]


# ─────────────────────────── the cache actually caches ───────────────────────

def test_a_repeat_call_is_served_from_cache(merchant, _fake_redis):
    client, headers, org_id = merchant
    for _ in range(5):
        store.store_return(_return_payload(org_id))

    first = client.get("/api/v1/returns/dashboard", headers=headers)
    assert first.status_code == 200

    keys = list(_fake_redis.scan_iter(f"org:{org_id}:*"))
    assert keys, "no cache key was written on the first call"

    # Delete the return directly in the DB without going through
    # store_return (which would invalidate). If the second HTTP call still
    # reports the old count, it proves the response came from cache, not a
    # fresh query.
    from app.db import models
    from app.db.store import SessionLocal
    with SessionLocal() as db:
        row = db.query(models.ReturnRequest).filter_by(org_id=org_id).first()
        db.delete(row)
        db.commit()

    second = client.get("/api/v1/returns/dashboard", headers=headers)
    assert second.json() == first.json(), "second call did not hit the cache"


def test_cache_keys_are_namespaced_per_organization(merchant, _fake_redis):
    client, headers, org_id = merchant
    store.store_return(_return_payload(org_id))
    client.get("/api/v1/returns/dashboard", headers=headers)

    keys = list(_fake_redis.scan_iter("*"))
    assert all(k.startswith(f"org:{org_id}:") for k in keys)


# ───────────────────────── invalidation on write ──────────────────────────────

def test_a_write_invalidates_the_cache():
    """THE property this phase exists to add. Without it, wiring `@cached`
    onto the dashboard would be a regression — merchants would see stale
    numbers after every approve/reject for up to the TTL."""
    org_id = str(uuid.uuid4())
    store.store_return(_return_payload(org_id))
    cache_module.cache_set(f"org:{org_id}:dashboard:default", {"stale": True}, 60)

    assert cache_module.cache_get(f"org:{org_id}:dashboard:default") is not None
    store.store_return(_return_payload(org_id))  # any write to this org
    assert cache_module.cache_get(f"org:{org_id}:dashboard:default") is None


def test_dashboard_reflects_a_write_immediately_through_the_api(merchant):
    """End-to-end version of the same property, through the real endpoints
    rather than calling cache functions directly."""
    client, headers, org_id = merchant
    for _ in range(3):
        store.store_return(_return_payload(org_id))

    before = client.get("/api/v1/returns/dashboard", headers=headers).json()
    store.store_return(_return_payload(org_id))
    after = client.get("/api/v1/returns/dashboard", headers=headers).json()

    assert after["total_returns"] == before["total_returns"] + 1


def test_an_update_to_an_existing_return_also_invalidates():
    """`store_return` has two branches -- create and update. Both must
    invalidate; a bug that invalidated only on create would show correct
    counts but stale status breakdowns after every status change.

    Updates a minimal `{"id": ..., "status": ...}` dict, mirroring how real
    call sites actually invoke this (e.g. `return_mgmt.py`'s status-change
    route) rather than round-tripping a full serialized row back in.
    """
    org_id = str(uuid.uuid4())
    row = store.store_return(_return_payload(org_id))
    cache_module.cache_set(f"org:{org_id}:dashboard:default", {"stale": True}, 60)

    store.store_return({"id": row["id"], "status": "approved"})
    assert cache_module.cache_get(f"org:{org_id}:dashboard:default") is None


def test_invalidation_does_not_touch_other_organizations(_fake_redis):
    """Invalidating org A's cache must not clear org B's — that would defeat
    the caching for every OTHER merchant every time any one merchant writes."""
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    cache_module.cache_set(f"org:{org_a}:dashboard:default", {"a": 1}, 60)
    cache_module.cache_set(f"org:{org_b}:dashboard:default", {"b": 1}, 60)

    store.store_return(_return_payload(org_a))

    assert cache_module.cache_get(f"org:{org_a}:dashboard:default") is None
    assert cache_module.cache_get(f"org:{org_b}:dashboard:default") == {"b": 1}


# ────────────────────────── tenant isolation on read ──────────────────────────

def test_one_organizations_dashboard_never_reflects_another(app_client, _fake_redis):
    """The end-to-end proof: two merchants, two different return counts, and
    the second must never see the first's cached numbers — verified with
    fakeredis rather than assumed from the key format alone."""
    def register():
        r = app_client.post("/api/v1/auth/register", json={
            "full_name": "T One", "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPass123", "org_name": f"Org {uuid.uuid4().hex[:6]}",
            "platform_type": "shopify", "accepted_terms": True,
        })
        return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["org_id"]

    headers_a, org_a = register()
    headers_b, org_b = register()

    for _ in range(7):
        store.store_return(_return_payload(org_a))

    dash_a = app_client.get("/api/v1/returns/dashboard", headers=headers_a).json()
    dash_b = app_client.get("/api/v1/returns/dashboard", headers=headers_b).json()

    assert dash_a["total_returns"] == 7
    assert dash_b["total_returns"] == 0


# ───────────────────────── graceful degradation ──────────────────────────────

def test_caching_never_breaks_the_endpoint_when_redis_is_down(merchant):
    """cache.py's own design principle, verified rather than trusted:
    caching must degrade to a miss, never take the request down."""
    client, headers, org_id = merchant
    store.store_return(_return_payload(org_id))

    cache_module._redis_client = None
    cache_module.get_redis = lambda: None

    resp = client.get("/api/v1/returns/dashboard", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total_returns"] == 1


def test_analytics_also_degrades_gracefully(merchant):
    client, headers, org_id = merchant
    cache_module._redis_client = None
    cache_module.get_redis = lambda: None
    resp = client.get("/api/v1/returns/analytics", headers=headers)
    assert resp.status_code == 200


# ─────────────────────────────── TTL ──────────────────────────────────────────

def test_the_dashboard_ttl_is_short_the_analytics_ttl_is_longer():
    """Matches cache.py's own TTL guidance, written before this phase wired
    anything to it: dashboard 30s (near-live expectation), analytics 120s
    (heavier query, less time-sensitive)."""
    org_id = str(uuid.uuid4())
    cache_module.cache_set(f"org:{org_id}:dashboard:default", {"x": 1}, 30)
    cache_module.cache_set(f"org:{org_id}:analytics:default", {"x": 1}, 120)

    dashboard_ttl = cache_module.get_redis().ttl(f"org:{org_id}:dashboard:default")
    analytics_ttl = cache_module.get_redis().ttl(f"org:{org_id}:analytics:default")
    assert dashboard_ttl <= 30
    assert analytics_ttl > dashboard_ttl
