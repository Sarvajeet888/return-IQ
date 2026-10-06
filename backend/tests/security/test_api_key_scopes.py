"""PHASE 34 — public API key scoping.

The property under test: a key grants exactly what it was given, never
everything — and creating one cannot be a way around your own role.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.permissions import Permission
from app.services.api_key_scopes import (
    DEFAULT_SCOPES,
    PUBLIC_API_SCOPES,
    WRITE_SCOPES,
    ApiKeyScopeError,
    KeyHealth,
    describe_scopes,
    key_has_permission,
    validate_scopes,
)


# ─────────────────── scopes reuse the Phase 6 vocabulary ─────────────────────

def test_scopes_are_phase_6_permission_strings():
    """`returns.read` means the same thing whether a person or a key holds it.

    A parallel vocabulary would mean two models to reason about and two places
    to audit, and only one of them would stay current.
    """
    assert PUBLIC_API_SCOPES <= {
        getattr(Permission, name) for name in dir(Permission)
        if not name.startswith("_")
    }


def test_console_only_permissions_are_not_api_scopes():
    """User management, billing and integration config are console
    operations. Exposing them to a key that may be pasted into a CI config
    widens the blast radius of a leak for no integration benefit."""
    for scope in (Permission.USERS_MANAGE, Permission.BILLING_MANAGE,
                  Permission.ORG_MANAGE, Permission.INTEGRATIONS_MANAGE,
                  Permission.PLATFORM_ADMIN):
        assert scope not in PUBLIC_API_SCOPES


# ────────────────────────── the default matters ──────────────────────────────

def test_the_default_is_read_only():
    """The default matters more than the maximum: most keys are created by
    someone in a hurry who accepts what is offered. A permissive default means
    most keys in the wild are permissive."""
    assert DEFAULT_SCOPES.isdisjoint(WRITE_SCOPES)


def test_no_requested_scopes_yields_the_default():
    assert validate_scopes(None, creator_role="org_admin") == DEFAULT_SCOPES
    assert validate_scopes([], creator_role="org_admin") == DEFAULT_SCOPES
    assert validate_scopes(["  "], creator_role="org_admin") == DEFAULT_SCOPES


# ─────────────────── creating a key is not an escalation ─────────────────────

def test_a_key_cannot_exceed_its_creators_permissions():
    """THE test for this phase.

    Without it, creating an API key is a privilege-escalation primitive: an
    analyst who cannot approve returns mints a key that can, then uses the key.
    """
    with pytest.raises(ApiKeyScopeError, match="do not have"):
        validate_scopes([Permission.RETURNS_APPROVE], creator_role="analyst")


def test_an_admin_can_grant_what_they_hold():
    scopes = validate_scopes(
        [Permission.RETURNS_APPROVE, Permission.RETURNS_READ],
        creator_role="org_admin",
    )
    assert Permission.RETURNS_APPROVE in scopes


def test_an_analyst_can_still_create_a_read_key():
    """The check must not block legitimate use, or people share admin keys
    instead — which is strictly worse."""
    scopes = validate_scopes([Permission.RETURNS_READ], creator_role="analyst")
    assert scopes == {Permission.RETURNS_READ}


def test_an_unknown_role_can_grant_nothing():
    """Fails closed, consistent with Phase 6."""
    with pytest.raises(ApiKeyScopeError):
        validate_scopes([Permission.RETURNS_READ], creator_role="chief_wizard")


def test_a_console_only_scope_is_refused():
    with pytest.raises(ApiKeyScopeError, match="not scopes available"):
        validate_scopes([Permission.USERS_MANAGE], creator_role="org_admin")


def test_an_invented_scope_is_refused():
    with pytest.raises(ApiKeyScopeError, match="not scopes available"):
        validate_scopes(["returns.destroy"], creator_role="org_admin")


# ───────────────────────── enforcement fails closed ──────────────────────────

def test_a_key_with_no_scopes_permits_nothing():
    """Existing keys predate scoping. Failing OPEN would leave every current
    key omnipotent — exactly the state this phase exists to end — and the
    failure would be invisible, because everything would keep working.
    """
    assert key_has_permission(None, Permission.RETURNS_READ) is False
    assert key_has_permission([], Permission.RETURNS_READ) is False


def test_a_key_permits_only_what_it_holds():
    scopes = [Permission.RETURNS_READ, Permission.RISK_READ]
    assert key_has_permission(scopes, Permission.RETURNS_READ) is True
    assert key_has_permission(scopes, Permission.RETURNS_APPROVE) is False
    assert key_has_permission(scopes, Permission.RETURNS_CREATE) is False


def test_the_scope_dependency_rejects_unknown_permissions_at_import():
    """A typo must break the build, not silently deny every key forever —
    the Phase 6 lesson."""
    from app.api.v1.deps import require_api_scope

    with pytest.raises(ValueError, match="Unknown permission"):
        require_api_scope("retunrs.raed")

    assert require_api_scope(Permission.RETURNS_READ) is not None


# ──────────────────────── human-readable descriptions ────────────────────────

def test_scopes_are_described_in_plain_english():
    """`returns.approve` means nothing to the person pasting a key into a
    vendor portal. "Approve returns" tells them what they are handing over."""
    described = describe_scopes([Permission.RETURNS_APPROVE, Permission.RETURNS_READ])
    labels = {d["label"] for d in described}
    assert "Approve returns" in labels
    assert "Read returns and their details" in labels


def test_write_scopes_are_marked_as_such():
    described = {d["scope"]: d for d in describe_scopes(list(PUBLIC_API_SCOPES))}
    assert described[Permission.RETURNS_APPROVE]["write"] is True
    assert described[Permission.RETURNS_READ]["write"] is False


# ────────────────────────────── key health ───────────────────────────────────

def _health(**overrides):
    base = dict(
        name="Shopify integration", prefix="rl_live_abc",
        is_active=True,
        created_at=datetime.now(UTC).isoformat(),
        last_used_at=datetime.now(UTC).isoformat(),
        expires_at=(datetime.now(UTC) + timedelta(days=200)).isoformat(),
        scopes=[Permission.RETURNS_READ],
    )
    base.update(overrides)
    return KeyHealth(**base)


def test_a_healthy_key_reports_healthy():
    assert _health().status()["status"] == "healthy"


def test_a_key_with_no_expiry_is_flagged():
    """A key issued today works forever — outliving the integration, the
    contractor who configured it, and often the company that received it."""
    findings = _health(expires_at=None).status()["findings"]
    assert any("works forever" in f for f in findings)


def test_a_never_used_key_is_flagged_as_safe_to_revoke():
    """Makes revocation possible. Nobody removes a key they cannot describe."""
    findings = _health(last_used_at=None).status()["findings"]
    assert any("revoking costs nothing" in f for f in findings)


def test_a_long_idle_key_is_flagged():
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    findings = _health(last_used_at=old).status()["findings"]
    assert any("decommissioned integration" in f for f in findings)


def test_an_expired_key_is_reported():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    findings = _health(expires_at=past).status()["findings"]
    assert any("Expired" in f for f in findings)


def test_an_expiring_key_warns_before_it_breaks():
    soon = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    findings = _health(expires_at=soon).status()["findings"]
    assert any("Rotate it before" in f for f in findings)


def test_write_capable_keys_are_called_out():
    findings = _health(scopes=[Permission.RETURNS_APPROVE]).status()["findings"]
    assert any("Can change data" in f for f in findings)


def test_a_revoked_key_needs_no_further_findings():
    result = _health(is_active=False).status()
    assert result["status"] == "revoked"
    assert result["findings"] == []
