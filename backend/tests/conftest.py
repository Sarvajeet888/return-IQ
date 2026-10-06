"""Pytest fixtures.

IMPORTANT - env vars are set at MODULE IMPORT time, not in a fixture.

Settings are read once into module-level `settings` objects across the app
(`settings = get_settings()` appears in config.py, rate_limit.py, and several
route modules), and slowapi's `@limiter.limit(settings.RATE_LIMIT_REGISTER)`
decorators are evaluated at import time too. So the values are frozen the
moment any app module is first imported.

Originally these vars were set in a session-scoped autouse fixture. That
worked while every test file imported app code lazily (inside fixtures), but
broke as soon as test modules started importing app code at module level
(e.g. `from app.core import cache`) - pytest imports all test modules during
collection, which happens BEFORE any fixture runs, so the app captured the
default 5/minute register limit and later tests got 429s.

Setting them here, at conftest import time, guarantees they are in place
before pytest imports any test module.
"""
from __future__ import annotations
import os
import uuid

import pytest

# ── MUST run before any `app.*` import anywhere in the test suite ────────────
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("API_KEY_HASH_PEPPER", "test-pepper-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("MAX_LOGIN_ATTEMPTS", "3")
os.environ.setdefault("LOCKOUT_DURATION_MINUTES", "15")
os.environ.setdefault("USE_REDIS_RATE_LIMIT", "false")
# Rate limits are effectively disabled for the suite. Rate limiting itself is
# tested explicitly in tests/security/, not incidentally by every other test.
os.environ.setdefault("RATE_LIMIT_DEFAULT", "100000/minute")
os.environ.setdefault("RATE_LIMIT_LOGIN", "100000/minute")
os.environ.setdefault("RATE_LIMIT_REGISTER", "100000/minute")


def pytest_configure(config):
    """Point the app at a temp SQLite DB before any app import."""
    import tempfile
    db_dir = tempfile.mkdtemp(prefix="returniq_test_")
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_dir}/test.db")


@pytest.fixture(scope="session", autouse=True)
def _test_environment():
    """Kept for backward compatibility - env setup now happens at import."""
    yield


@pytest.fixture(scope="session")
def app_client(_test_environment):
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def unique_email():
    return f"user_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture()
def registered_user(app_client, unique_email):
    """Registers a brand-new org+user and returns (client, access_token, email, password)."""
    password = "TestPass123"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Test User", "email": unique_email, "password": password,
        "org_name": f"Test Org {uuid.uuid4().hex[:6]}", "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return app_client, r.json()["access_token"], unique_email, password
