"""Authentication service - JWT, user management, org registration."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status, Request

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.db import store
from app.schemas.schemas import LoginRequest, RegisterRequest

settings = get_settings()
logger = logging.getLogger("app.auth")


def _user_summary(user: dict, role_override: str | None = None) -> dict:
    """Shared shape for the `user` object returned by login/register/me.
    Was previously copy-pasted 3x with drifting field sets - register()'s
    copy was missing avatar_url/mfa_enabled, so the frontend received a
    differently-shaped user object depending on which flow it came from."""
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": role_override or user["role"],
        "org_id": user["org_id"],
        "avatar_url": user.get("avatar_url", ""),
        "mfa_enabled": user.get("mfa_enabled", False),
    }


def _issue_tokens(user: dict) -> dict:
    """Issue a fresh access + refresh token pair, persisting the refresh
    token's jti so it can be rotated/revoked server-side."""
    access_token = create_access_token(
        subject=user["id"],
        extra={"org_id": user["org_id"], "role": user["role"], "email": user["email"]},
    )
    refresh_token, jti, expires_at = create_refresh_token(subject=user["id"])
    store.create_refresh_token_record(jti, user["id"], expires_at)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def login(req: LoginRequest) -> dict:
    if store.is_account_locked(req.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to too many failed login attempts. "
                   f"Try again in {settings.LOCKOUT_DURATION_MINUTES} minutes."
        )

    user = store.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        store.record_login_attempt(req.email, success=False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    store.record_login_attempt(req.email, success=True)
    store.update_user(user["id"], {"last_login": datetime.now(UTC)})
    store.add_audit_log({"org_id": user["org_id"], "user_id": user["id"], "action": "login", "detail": "Login successful"})

    tokens = _issue_tokens(user)
    tokens["user"] = _user_summary(user)
    return tokens


def register(req: RegisterRequest, request: Request | None = None) -> dict:
    if store.get_user_by_email(req.email):
        # 409 Conflict is the correct code for "this resource already exists"
        # (400 was returned previously). docs/guides/API_GUIDE.md documents 409,
        # and /org/members/invite already uses 409 for the same condition -
        # this makes the two duplicate-email paths consistent.
        raise HTTPException(status_code=409, detail="Email already registered")

    org = store.create_org({
        "name": req.org_name,
        "slug": req.org_name.lower().replace(" ", "-"),
        "contact_email": req.email,
        "platform_type": req.platform_type,
        "plan_tier": "free",
        "is_active": True,
        "settings": {"currency": "INR", "timezone": "Asia/Kolkata"},
    })

    user = store.create_user({
        "org_id": org["id"],
        "email": req.email.lower(),
        "full_name": req.full_name,
        "password_hash": hash_password(req.password),
        "role": "org_admin",
        "status": "active",
        "is_verified": True,
        "avatar_url": "",
        "mfa_enabled": False,
    })

    # DPDP Act: record proof of consent - who, which policy version, when,
    # from where. Written immediately after user creation so a registration
    # can never exist without its consent record.
    store.record_consent({
        "user_id": user["id"],
        "consent_type": "terms_and_privacy",
        "policy_version": req.policy_version,
        "granted": True,
        "ip_address": (request.client.host if request and request.client else None),
        "user_agent": (request.headers.get("user-agent", "")[:500] if request else None),
    })

    raw_key, prefix = generate_api_key()
    key_hash = hash_api_key(raw_key, settings.API_KEY_HASH_PEPPER)
    store.store_api_key(key_hash, {"org_id": org["id"], "name": "Default Key", "prefix": prefix, "is_active": True})

    tokens = _issue_tokens(user)
    tokens["api_key"] = raw_key
    tokens["user"] = _user_summary(user, role_override="org_admin")
    return tokens


def refresh_tokens(refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    jti = payload.get("jti")
    record = store.get_refresh_token_record(jti) if jti else None
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if record.get("revoked_at"):
        # This jti was already rotated once before - reusing it means the
        # token was likely stolen and replayed. Kill every active session
        # for this user rather than silently issuing new tokens.
        logger.warning("Refresh token reuse detected for user_id=%s jti=%s", record["user_id"], jti)
        store.revoke_all_refresh_tokens_for_user(record["user_id"])
        raise HTTPException(status_code=401, detail="Refresh token has already been used. All sessions revoked - please log in again.")

    user = store.get_user(payload["sub"])
    if not user or user.get("status") != "active":
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(
        subject=user["id"],
        extra={"org_id": user["org_id"], "role": user["role"], "email": user["email"]},
    )
    new_refresh, new_jti, expires_at = create_refresh_token(subject=user["id"])
    store.create_refresh_token_record(new_jti, user["id"], expires_at)
    store.rotate_refresh_token(jti, new_jti)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def logout(user: dict) -> None:
    payload = user.get("_token_payload") or {}
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        store.revoke_access_token(jti, datetime.fromtimestamp(exp, tz=UTC))
    store.add_audit_log({"org_id": user["org_id"], "user_id": user["id"], "action": "logout", "detail": "User logged out"})
