from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.v1.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import hash_password, verify_password
from app.db import store
from app.schemas.schemas import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    VerifyEmailRequest,
)
from app.services import account_token_service, auth_service
from app.services.auth_service import _user_summary

settings = get_settings()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

COOKIE_KWARGS = dict(
    httponly=True,
    secure=settings.COOKIE_SECURE,
    samesite=settings.COOKIE_SAMESITE,
    path="/api/v1/auth",
    max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(settings.REFRESH_COOKIE_NAME, refresh_token, **COOKIE_KWARGS)


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")


@router.post("/login")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(request: Request, req: LoginRequest, response: Response) -> dict:
    result = auth_service.login(req)
    # Refresh token travels only as an httpOnly cookie - never exposed to
    # JS, unlike the old design where both tokens sat in localStorage and
    # were readable (and exfiltratable) by any injected script.
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.post("/register")
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register(request: Request, req: RegisterRequest, response: Response) -> dict:
    result = auth_service.register(req, request)
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.post("/refresh")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def refresh(request: Request, response: Response, req: RefreshRequest | None = None) -> dict:
    # Cookie is the primary transport (browser clients). Body field is kept
    # only so non-browser API clients (tests, server-to-server) can still
    # pass a refresh token explicitly.
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME) or (req.refresh_token if req else None)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token provided")
    result = auth_service.refresh_tokens(token)
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    org = store.get_org(user["org_id"])
    return {
        **_user_summary(user),
        "last_login": user.get("last_login"),
        "org": {
            "id": org["id"],
            "name": org["name"],
            "plan_tier": org["plan_tier"],
            "platform_type": org["platform_type"],
        } if org else None
    }


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)) -> dict:
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    store.update_user(user["id"], {"password_hash": hash_password(req.new_password)})
    # Changing the password is a good moment to kill every other session.
    store.revoke_all_refresh_tokens_for_user(user["id"])
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)) -> dict:
    auth_service.logout(user)
    _clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Invitation acceptance & email verification
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/accept-invitation")
async def accept_invitation(payload: AcceptInvitationRequest) -> dict:
    """Set the initial password for an invited account, using a one-time token.

    Unauthenticated by design: the invitee has no credentials yet -- that is
    the entire point of the flow. The token is the authentication.
    """
    user_id = account_token_service.consume(
        payload.token, account_token_service.PURPOSE_INVITATION
    )
    if not user_id:
        # One message for every failure mode (unknown / expired / already
        # used / wrong purpose). Distinguishing them would confirm to an
        # attacker that a given token once existed.
        raise HTTPException(
            status_code=400,
            detail="This invitation link is invalid or has expired. "
                   "Ask your administrator to send a new one.",
        )

    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="This invitation link is no longer valid.")

    store.update_user(user_id, {
        "password_hash": hash_password(payload.password),
        "status": "active",
        # Accepting the invitation proves control of the mailbox the link was
        # sent to, so a separate verification round-trip would be redundant.
        "is_verified": True,
    })
    # Any session minted before the password existed must not survive it.
    store.revoke_all_refresh_tokens_for_user(user_id)

    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user_id,
        "action": "invitation_accepted",
        "detail": f"{user['email']} set their initial password",
    })
    return {"message": "Your account is ready. You can now sign in."}


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest) -> dict:
    """Confirm ownership of an email address via a single-use token."""
    user_id = account_token_service.consume(
        payload.token, account_token_service.PURPOSE_EMAIL_VERIFICATION
    )
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="This verification link is invalid or has expired.",
        )

    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="This verification link is no longer valid.")

    store.update_user(user_id, {"is_verified": True})
    store.add_audit_log({
        "org_id": user["org_id"], "user_id": user_id,
        "action": "email_verified", "detail": f"{user['email']} verified their address",
    })
    return {"message": "Email verified."}
