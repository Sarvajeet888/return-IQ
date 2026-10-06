"""Rate limiting via slowapi.

Uses Redis as the shared counter store when USE_REDIS_RATE_LIMIT is on (the
correct choice for multi-worker/multi-instance deployments — an in-memory
counter doesn't sync across uvicorn workers, which was the previous "config
exists but nothing enforces it" gap). Falls back to an in-process memory
store for local/single-worker dev so nothing extra needs to run to test it.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()


def _rate_limit_key(request: Request) -> str:
    """Client IP for rate-limit bucketing.

    Previously this was slowapi's default get_remote_address, which reads
    the raw TCP peer address. In this project's docker-compose topology
    every request is proxied through nginx, so every user's traffic was
    bucketed under nginx's own container IP - meaning rate limits were
    effectively global across all users combined, not per-client, and a
    real attacker's brute-force attempts shared the same budget as every
    legitimate user.

    Trusting X-Forwarded-For is only safe because the backend is no longer
    directly internet-exposed (docker-compose.yml no longer publishes its
    port) - nginx is the sole entry point and sets this header honestly.
    If you ever change the deployment topology so the backend IS directly
    reachable again, this must go back to get_remote_address, or an
    attacker could spoof X-Forwarded-For per request to bypass rate
    limits entirely.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


_storage_uri = settings.REDIS_URL if settings.USE_REDIS_RATE_LIMIT else "memory://"

limiter = Limiter(key_func=_rate_limit_key, storage_uri=_storage_uri, default_limits=[settings.RATE_LIMIT_DEFAULT])
