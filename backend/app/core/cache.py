"""
Redis caching layer for ReturnIQ Enterprise (Phase 8.9)

Caches expensive read-heavy endpoints:
  - Dashboard KPIs (recomputed from scratch on every request currently)
  - Analytics aggregations
  - Customer analytics
  - AI performance metrics

Design notes:
  - Cache keys are always org-scoped ("org:{org_id}:...") so one tenant can
    never read another tenant's cached data.
  - Writes invalidate the org's cache namespace rather than trying to
    surgically patch individual keys — simpler and safe.
  - If Redis is unavailable, every function degrades gracefully to a cache
    miss rather than raising. Caching should never take the app down.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

# ── Redis client (optional) ───────────────────────────────────────────────────

_redis_client = None


def get_redis():
    """Lazily create a Redis client. Returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        logger.info("Redis cache connected")
        return _redis_client
    except Exception as exc:
        logger.warning("Redis cache unavailable, running without cache: %s", exc)
        _redis_client = None
        return None


# ── Core cache operations ─────────────────────────────────────────────────────

def cache_get(key: str) -> Any | None:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Cache get failed for %s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("Cache set failed for %s: %s", key, exc)


def cache_invalidate_org(org_id: str) -> int:
    """
    Delete all cached entries for one organisation.
    Called after any write that could change dashboard/analytics output.
    Returns the number of keys deleted.
    """
    r = get_redis()
    if r is None:
        return 0
    try:
        pattern = f"org:{org_id}:*"
        deleted = 0
        # SCAN rather than KEYS — KEYS blocks Redis on large datasets
        for key in r.scan_iter(match=pattern, count=100):
            r.delete(key)
            deleted += 1
        if deleted:
            logger.debug("Invalidated %d cache keys for org %s", deleted, org_id)
        return deleted
    except Exception as exc:
        logger.warning("Cache invalidation failed for org %s: %s", org_id, exc)
        return 0


# ── Decorator for caching endpoint results ────────────────────────────────────

def cached(ttl_seconds: int = 60, key_prefix: str = ""):
    """
    Cache the result of an async endpoint function.

    The wrapped function MUST accept an `org` dict kwarg (as all ReturnIQ
    endpoints do via Depends(get_current_org)) so the cache key can be
    org-scoped. If no org is found, caching is skipped entirely rather than
    risking a cross-tenant cache key.

    Usage:
        @router.get("/dashboard")
        @cached(ttl_seconds=30, key_prefix="dashboard")
        async def dashboard(org: dict = Depends(get_current_org)):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            org = kwargs.get("org")
            if not org or not isinstance(org, dict) or "id" not in org:
                # No org context — don't cache
                return await func(*args, **kwargs)

            # Build a cache key including any query params that affect output
            param_parts = []
            for k, v in sorted(kwargs.items()):
                if k in ("org", "user") or v is None:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    param_parts.append(f"{k}={v}")
            param_str = ":".join(param_parts) if param_parts else "default"

            key = f"org:{org['id']}:{key_prefix or func.__name__}:{param_str}"

            hit = cache_get(key)
            if hit is not None:
                return hit

            result = await func(*args, **kwargs)
            cache_set(key, result, ttl_seconds)
            return result

        return wrapper
    return decorator


# ── Recommended TTLs per endpoint type ────────────────────────────────────────
# Dashboard KPIs        : 30s  — users expect near-live numbers
# Analytics aggregations: 120s — heavier queries, less time-sensitive
# Customer analytics    : 300s — changes slowly
# AI performance        : 120s
# Reports               : not cached — user explicitly requested fresh data
