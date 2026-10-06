"""
Unit tests for the Redis cache layer (Phase 9.2).

Two properties matter most and are tested hardest:
  1. Cache failure must NEVER break the app (graceful degradation)
  2. Cache keys must NEVER leak across organisations (tenant isolation)
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch

from app.core import cache as cache_mod


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level Redis singleton between tests."""
    cache_mod._redis_client = None
    yield
    cache_mod._redis_client = None


# ── Graceful degradation: no Redis available ─────────────────────────────────

def test_cache_get_returns_none_when_redis_unavailable():
    with patch.object(cache_mod, "get_redis", return_value=None):
        assert cache_mod.cache_get("any:key") is None


def test_cache_set_is_noop_when_redis_unavailable():
    """Must not raise - a dead cache should slow the app, not break it."""
    with patch.object(cache_mod, "get_redis", return_value=None):
        cache_mod.cache_set("any:key", {"data": 1}, ttl_seconds=60)  # no exception


def test_cache_invalidate_returns_zero_when_redis_unavailable():
    with patch.object(cache_mod, "get_redis", return_value=None):
        assert cache_mod.cache_invalidate_org("org-123") == 0


def test_cache_get_swallows_redis_exception():
    """If Redis raises mid-operation, treat it as a cache miss."""
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("redis died")
    with patch.object(cache_mod, "get_redis", return_value=broken):
        assert cache_mod.cache_get("k") is None


def test_cache_set_swallows_redis_exception():
    broken = MagicMock()
    broken.setex.side_effect = ConnectionError("redis died")
    with patch.object(cache_mod, "get_redis", return_value=broken):
        cache_mod.cache_set("k", {"a": 1})  # must not raise


# ── Round-trip behaviour with a working fake Redis ───────────────────────────

class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)

    def scan_iter(self, match=None, count=None):
        prefix = (match or "").rstrip("*")
        return [k for k in list(self.store.keys()) if k.startswith(prefix)]

    def ping(self):
        return True


def test_cache_roundtrip_preserves_value():
    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        payload = {"total": 42, "items": ["a", "b"], "nested": {"x": 1}}
        cache_mod.cache_set("org:1:dashboard", payload, ttl_seconds=30)
        assert cache_mod.cache_get("org:1:dashboard") == payload


def test_cache_get_missing_key_returns_none():
    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        assert cache_mod.cache_get("org:1:never-set") is None


def test_cache_serializes_non_json_types():
    """datetime and similar are serialized via default=str rather than crashing."""
    from datetime import datetime
    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        cache_mod.cache_set("org:1:x", {"ts": datetime(2025, 8, 1, 12, 0)})
        result = cache_mod.cache_get("org:1:x")
        assert isinstance(result["ts"], str)


# ── Tenant isolation: THE security-critical property ─────────────────────────

def test_invalidate_org_only_deletes_that_orgs_keys():
    """
    Invalidating org A must never touch org B's cache. If this test ever
    fails, one tenant is serving another tenant's data.
    """
    fake = FakeRedis()
    fake.store = {
        "org:AAA:dashboard": '{"v":1}',
        "org:AAA:analytics": '{"v":2}',
        "org:BBB:dashboard": '{"v":3}',
        "org:BBB:analytics": '{"v":4}',
    }
    with patch.object(cache_mod, "get_redis", return_value=fake):
        deleted = cache_mod.cache_invalidate_org("AAA")

    assert deleted == 2
    remaining = set(fake.store.keys())
    assert remaining == {"org:BBB:dashboard", "org:BBB:analytics"}


def test_invalidate_org_with_no_keys_is_safe():
    fake = FakeRedis()
    fake.store = {"org:BBB:dashboard": "{}"}
    with patch.object(cache_mod, "get_redis", return_value=fake):
        assert cache_mod.cache_invalidate_org("AAA-no-such-org") == 0
    assert "org:BBB:dashboard" in fake.store


def test_org_id_prefix_collision_does_not_overmatch():
    """
    Guards against a subtle bug: invalidating org "1" must not wipe org "12".
    The colon separator in the key format prevents this.
    """
    fake = FakeRedis()
    fake.store = {
        "org:1:dashboard": "{}",
        "org:12:dashboard": "{}",
    }
    with patch.object(cache_mod, "get_redis", return_value=fake):
        cache_mod.cache_invalidate_org("1")
    # "org:1:*" must not match "org:12:dashboard"
    assert "org:12:dashboard" in fake.store, "org 12's cache was wrongly deleted"


# ── The @cached decorator ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cached_decorator_skips_caching_without_org():
    """
    No org context means we cannot build a tenant-scoped key. The decorator
    must skip caching entirely rather than risk a shared/global key.
    """
    calls = []

    @cache_mod.cached(ttl_seconds=60, key_prefix="test")
    async def endpoint(**kwargs):
        calls.append(1)
        return {"result": "ok"}

    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        await endpoint()
        await endpoint()

    assert len(calls) == 2, "function should be called every time when no org context"
    assert fake.store == {}, "nothing should have been cached"


@pytest.mark.asyncio
async def test_cached_decorator_caches_on_second_call():
    calls = []

    @cache_mod.cached(ttl_seconds=60, key_prefix="dash")
    async def endpoint(org=None):
        calls.append(1)
        return {"total": 5}

    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        r1 = await endpoint(org={"id": "ORG1"})
        r2 = await endpoint(org={"id": "ORG1"})

    assert r1 == r2 == {"total": 5}
    assert len(calls) == 1, "second call should have been served from cache"


@pytest.mark.asyncio
async def test_cached_decorator_separates_orgs():
    """Two orgs calling the same endpoint must get their own cache entries."""
    call_log = []

    @cache_mod.cached(ttl_seconds=60, key_prefix="dash")
    async def endpoint(org=None):
        call_log.append(org["id"])
        return {"org": org["id"]}

    fake = FakeRedis()
    with patch.object(cache_mod, "get_redis", return_value=fake):
        a = await endpoint(org={"id": "ORG_A"})
        b = await endpoint(org={"id": "ORG_B"})

    assert a == {"org": "ORG_A"}
    assert b == {"org": "ORG_B"}, "org B must NOT receive org A's cached response"
    assert call_log == ["ORG_A", "ORG_B"]
