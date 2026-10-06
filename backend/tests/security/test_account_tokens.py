"""PHASE 5 — Invitation & email-verification token security.

The property under test is that a token grants exactly one action, exactly
once, within a bounded window, and that nothing recoverable from the database
can be replayed.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db import store
from app.services import account_token_service as ats


@pytest.fixture
def invited_user(app_client):
    """A user row to hang tokens off. app_client triggers schema creation."""
    org = store.create_org({
        "id": str(uuid.uuid4()),
        "name": "Token Test Org",
        "slug": f"token-test-{uuid.uuid4().hex[:6]}",
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
    user = store.create_user({
        "org_id": org["id"],
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "full_name": "Invited Person",
        "password_hash": "!invited-no-password-set",
        "role": "analyst",
    })
    return user["id"]


# ────────────────────────────── core behaviour ───────────────────────────────

def test_token_round_trip(invited_user):
    raw = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    assert ats.consume(raw, ats.PURPOSE_INVITATION) == invited_user


def test_token_is_single_use(invited_user):
    """The defining property. A reusable link is a password with extra steps."""
    raw = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    assert ats.consume(raw, ats.PURPOSE_INVITATION) == invited_user
    assert ats.consume(raw, ats.PURPOSE_INVITATION) is None


def test_wrong_purpose_is_rejected(invited_user):
    """A verification token must not be usable to set a password.

    Without purpose in the lookup, anyone who could trigger a verification
    email for their own address could present that token to the invitation
    endpoint.
    """
    raw = ats.issue(invited_user, ats.PURPOSE_EMAIL_VERIFICATION)
    assert ats.consume(raw, ats.PURPOSE_INVITATION) is None
    # And the token survives the failed attempt for its real purpose.
    assert ats.consume(raw, ats.PURPOSE_EMAIL_VERIFICATION) == invited_user


def test_expired_token_is_rejected(invited_user):
    raw = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    # Age the row directly rather than sleeping for seven days.
    from app.db.models import AccountToken
    from app.db.store import SessionLocal
    with SessionLocal() as db:
        row = db.get(AccountToken, hashlib.sha256(raw.encode()).hexdigest())
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert ats.consume(raw, ats.PURPOSE_INVITATION) is None


def test_unknown_token_is_rejected(invited_user):
    assert ats.consume("not-a-real-token-value-padding-here", ats.PURPOSE_INVITATION) is None


def test_empty_token_is_rejected(invited_user):
    assert ats.consume("", ats.PURPOSE_INVITATION) is None
    assert ats.consume(None, ats.PURPOSE_INVITATION) is None


def test_reissuing_invalidates_the_previous_token(invited_user):
    """Re-inviting somebody must revoke the earlier link.

    Otherwise 'resend the invitation' silently leaves two live credentials,
    and an admin who reissues to correct a mistaken address has not actually
    withdrawn the first one.
    """
    first = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    second = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    assert ats.consume(first, ats.PURPOSE_INVITATION) is None
    assert ats.consume(second, ats.PURPOSE_INVITATION) == invited_user


# ──────────────────────────── storage guarantees ─────────────────────────────

def test_raw_token_is_never_stored(invited_user):
    """Database read access must not yield usable invitations."""
    from app.db.models import AccountToken
    from app.db.store import SessionLocal

    raw = ats.issue(invited_user, ats.PURPOSE_INVITATION)
    with SessionLocal() as db:
        rows = db.query(AccountToken).filter_by(user_id=invited_user).all()
        stored = [r.token_hash for r in rows]

    assert raw not in stored
    assert hashlib.sha256(raw.encode()).hexdigest() in stored


def test_token_has_meaningful_entropy(invited_user):
    """Guards against a future 'simplification' to something guessable.

    The old flow used `Welcome@` plus six hex characters -- 24 bits with a
    fixed public prefix.
    """
    tokens = {ats.issue(invited_user, ats.PURPOSE_INVITATION) for _ in range(20)}
    assert len(tokens) == 20                 # no collisions
    assert all(len(t) >= 40 for t in tokens)  # 32 CSPRNG bytes, urlsafe-b64


def test_unknown_purpose_is_refused(invited_user):
    with pytest.raises(ValueError):
        ats.issue(invited_user, "some_purpose_nobody_defined")


# ──────────────────────────────── HTTP layer ─────────────────────────────────

def test_accept_invitation_endpoint_rejects_bad_token(app_client):
    r = app_client.post("/api/v1/auth/accept-invitation", json={
        "token": "x" * 40, "password": "NewPassword123",
    })
    assert r.status_code == 400
    # Generic message: must not confirm whether the token ever existed.
    assert "invalid or has expired" in r.json()["detail"]


def test_invited_account_cannot_log_in_before_accepting(app_client, invited_user):
    """The sentinel password hash must not be usable as a credential."""
    user = store.get_user(invited_user)
    r = app_client.post("/api/v1/auth/login", json={
        "email": user["email"], "password": "!invited-no-password-set",
    })
    assert r.status_code in (401, 403)
