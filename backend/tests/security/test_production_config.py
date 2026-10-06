"""FINAL RELEASE — production configuration safety.

These pin the guards that stand between "deployed" and "publicly known admin
password". Every one of them corresponds to a real default that shipped in
this codebase before the final release pass.
"""
from __future__ import annotations

import os

import pytest

from app.core.config import Settings


@pytest.fixture
def clean_env(monkeypatch):
    """A bare environment with only the mandatory secrets set."""
    for key in ("DEMO_MODE", "ENVIRONMENT", "DEBUG"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SECRET_KEY", "t" * 40)
    monkeypatch.setenv("API_KEY_HASH_PEPPER", "p" * 40)
    return monkeypatch


# ───────────────────────── defaults must fail safe ───────────────────────────

def test_demo_mode_is_off_by_default(clean_env):
    """THE production bug this release closed.

    DEMO_MODE previously defaulted to "true", so a deployment that simply
    forgot to set it shipped a seeded organisation with a KNOWN admin login
    (admin@sapnacollection.com / Demo@12345, role org_admin), plus demo
    API-key and password-reset-token endpoints, live and reachable.

    A missing environment variable is not an acceptable distance between
    "deployed" and "publicly known admin password".
    """
    assert Settings().DEMO_MODE is False


def test_debug_is_off_by_default(clean_env):
    assert Settings().DEBUG is False


# ──────────────────── production refuses dangerous config ────────────────────

def test_demo_mode_is_refused_in_production(clean_env):
    """Belt-and-braces beyond the safe default.

    The env var is set by hand, and a hand-set value is exactly what gets
    copied between environments by accident.
    """
    clean_env.setenv("ENVIRONMENT", "production")
    clean_env.setenv("DEMO_MODE", "true")

    with pytest.raises(RuntimeError, match="DEMO_MODE=true is refused"):
        Settings()


def test_debug_is_refused_in_production(clean_env):
    """Debug responses expose stack traces, file paths, dependency versions
    and query fragments to anyone who can trigger a 500."""
    clean_env.setenv("ENVIRONMENT", "production")
    clean_env.setenv("DEBUG", "true")

    with pytest.raises(RuntimeError, match="DEBUG=true is refused"):
        Settings()


def test_the_refusal_explains_what_to_do_instead(clean_env):
    """A guard that blocks without saying why gets disabled by whoever is
    trying to ship at 6pm."""
    clean_env.setenv("ENVIRONMENT", "production")
    clean_env.setenv("DEMO_MODE", "true")

    with pytest.raises(RuntimeError) as exc:
        Settings()
    assert "ENVIRONMENT=staging" in str(exc.value)


# ─────────────────────── legitimate use still works ──────────────────────────

def test_demo_mode_is_allowed_outside_production(clean_env):
    """The guard must not make demos impossible — only accidental ones.
    A wall that blocks every path gets removed entirely."""
    clean_env.setenv("ENVIRONMENT", "staging")
    clean_env.setenv("DEMO_MODE", "true")

    assert Settings().DEMO_MODE is True


def test_production_with_correct_config_starts_normally(clean_env):
    clean_env.setenv("ENVIRONMENT", "production")
    clean_env.setenv("DEMO_MODE", "false")
    clean_env.setenv("DEBUG", "false")

    settings = Settings()
    assert settings.DEMO_MODE is False
    assert settings.ENVIRONMENT == "production"


# ───────────────────────── secrets still hard-fail ───────────────────────────

def test_production_still_refuses_a_placeholder_secret(clean_env):
    """Pre-existing guard, pinned here so the final release cannot regress it
    while changing neighbouring code."""
    clean_env.setenv("ENVIRONMENT", "production")
    clean_env.setenv("SECRET_KEY", "change-me-in-production")

    with pytest.raises(Exception):
        Settings()
