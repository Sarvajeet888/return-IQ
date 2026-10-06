"""
User Account & Identity Management (Phase 5.1)
Covers: profile update, forgot/reset password, delete account, session management.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.v1.deps import get_current_user
from app.core.config import get_settings
from app.core.security import hash_password
from app.db import store
from app.services import email_service
from app.schemas.schemas import ForgotPasswordRequest, ResetPasswordRequest, UpdateProfileRequest

settings = get_settings()
router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)) -> dict:
    """Full profile including org context."""
    org = store.get_org(user["org_id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "avatar_url": user.get("avatar_url", ""),
        "is_verified": user.get("is_verified", True),
        "mfa_enabled": user.get("mfa_enabled", False),
        "last_login": user.get("last_login"),
        "created_at": user.get("created_at"),
        "org": {
            "id": org["id"],
            "name": org["name"],
            "plan_tier": org["plan_tier"],
        } if org else None,
    }


@router.patch("/profile")
async def update_profile(
    payload: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Update name and/or avatar URL."""
    updates: dict = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name
    if payload.avatar_url is not None:
        updates["avatar_url"] = payload.avatar_url
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    store.update_user(user["id"], updates)
    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user["id"],
        "action": "update_profile", "detail": "User updated profile",
    })
    return {"message": "Profile updated", "updates": updates}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, background: BackgroundTasks) -> dict:
    """
    Generate a single-use password reset token and (in a real deployment)
    email it to the user. In demo/dev mode the token is returned directly
    so the flow can be tested end-to-end without SMTP configured.

    Note: we intentionally return the same success message whether or not
    the email exists — leaking 'this email isn't registered' is a
    user enumeration vulnerability.
    """
    user = store.get_user_by_email(payload.email)
    if user:
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        store.create_password_reset_token(token, user["id"], expires_at)
        # In production: send_email(payload.email, "Reset your password", f"/reset-password?token={token}")
        # SMTP is not wired up in this codebase yet (see FIXES_STATUS.md) - the
        # token below MUST stay gated behind DEMO_MODE + non-production. This
        # was previously returned unconditionally, which meant anyone who knew
        # a user's email could reset their password directly from this
        # response with no access to their inbox - a full account-takeover
        # vector, live in every deployment since email delivery was never
        # implemented. Wire real SMTP before enabling this in production, and
        # never re-enable demo_token once DEMO_MODE=false / ENVIRONMENT=production.
        # Send the email on a background task. smtplib is blocking; calling it
        # inline would stall the event loop for the whole SMTP handshake, and
        # would also make response time leak whether the address exists.
        base_url = _app_base_url()
        background.add_task(email_service.send_password_reset, payload.email, token, base_url)

        if settings.DEMO_MODE and settings.ENVIRONMENT != "production":
            return {
                "message": "If that email is registered, a reset link has been sent.",
                "demo_token": token,  # dev/demo convenience only - never returned in production
                "email_configured": email_service.is_configured(),
            }
    return {"message": "If that email is registered, a reset link has been sent."}


def _app_base_url() -> str:
    """
    Public frontend URL for links inside emails.

    Prefers APP_BASE_URL, falls back to the first configured CORS origin -
    which is correct in nearly every deployment and saves configuring the
    same value twice.
    """
    if settings.APP_BASE_URL:
        return settings.APP_BASE_URL
    origins = getattr(settings, "CORS_ORIGINS", None) or []
    if origins:
        return origins[0]
    return "http://localhost:3000"


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict:
    """Consume a reset token and set a new password."""
    record = store.get_password_reset_token(payload.token)
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if record.get("used"):
        raise HTTPException(status_code=400, detail="Reset token has already been used")
    expires = record.get("expires_at")
    if expires:
        expires_dt = datetime.fromisoformat(expires) if isinstance(expires, str) else expires
        if expires_dt.replace(tzinfo=UTC) < datetime.now(UTC):
            raise HTTPException(status_code=400, detail="Reset token has expired")
    store.update_user(record["user_id"], {"password_hash": hash_password(payload.new_password)})
    store.consume_password_reset_token(payload.token)
    store.revoke_all_refresh_tokens_for_user(record["user_id"])
    return {"message": "Password reset successfully. Please log in again."}


@router.delete("/account")
async def delete_account(user: dict = Depends(get_current_user)) -> dict:
    """
    Soft-delete (deactivate) the requesting user's own account.
    Org admins deleting themselves is allowed but will orphan the org if
    they're the last admin — caller is responsible for that check.
    """
    store.revoke_all_refresh_tokens_for_user(user["id"])
    store.update_user(user["id"], {"status": "deleted"})
    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user["id"],
        "action": "delete_account", "detail": "User deleted own account",
    })
    return {"message": "Account deactivated successfully"}


@router.get("/sessions")
async def get_sessions(user: dict = Depends(get_current_user)) -> dict:
    """Returns current session info. Full session enumeration requires a
    refresh_tokens table query — available but intentionally minimal here
    since device fingerprinting is out of scope for Phase 5."""
    return {
        "user_id": user["id"],
        "current_session": "active",
        "last_login": user.get("last_login"),
        "note": "Call DELETE /sessions to revoke all other sessions.",
    }


@router.delete("/sessions")
async def revoke_all_sessions(user: dict = Depends(get_current_user)) -> dict:
    """Revoke all refresh tokens (kills all sessions except the current request)."""
    store.revoke_all_refresh_tokens_for_user(user["id"])
    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user["id"],
        "action": "revoke_sessions", "detail": "All sessions revoked",
    })
    return {"message": "All other sessions have been revoked"}


@router.get("/activity")
async def get_account_activity(user: dict = Depends(get_current_user)) -> list:
    """Recent audit log entries for this user."""
    logs = store.get_audit_logs(user["org_id"], limit=100)
    return [l for l in logs if l.get("user_id") == user["id"]]
