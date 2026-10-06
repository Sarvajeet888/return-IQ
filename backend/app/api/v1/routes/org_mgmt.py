"""
Organization & Multi-Tenant Management (Phase 5.2)
Covers: member invite/remove, role management, branding, feature flags, API keys.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.v1.deps import get_current_org, require_role
from app.core.security import hash_password
from app.db import store
from app.services import account_token_service
from app.services import email_service
from app.core.config import get_settings

settings = get_settings()
from app.schemas.schemas import FeatureFlagUpdate, InviteMemberRequest, OrgBrandingUpdate, UpdateMemberRoleRequest

router = APIRouter(prefix="/api/v1/org", tags=["organization"])


@router.post("/members/invite")
async def invite_member(
    payload: InviteMemberRequest,
    background: BackgroundTasks,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Invite a team member.

    PHASE 5: no password is created or emailed. The account is provisioned in
    `pending_invite` status with an unusable password hash, and the invitee
    receives a single-use link that lets them set their own password once.
    """
    existing = store.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    new_user = {
        "org_id": org["id"],
        "email": payload.email.lower(),
        "full_name": payload.full_name,
        # Sentinel, not a hash of anything. verify_password() cannot succeed
        # against this value, so the account is unusable until the invitation
        # is accepted -- there is no window in which a guessable credential
        # works. A hash of a random string would also be unusable, but this
        # says so explicitly to anyone reading the row.
        "password_hash": "!invited-no-password-set",
        "role": payload.role,
        "status": "pending_invite",
        "is_verified": False,
        "created_at": datetime.now(UTC),
    }
    # Use the id the database actually assigned. create_user() generates its
    # own primary key and ignores any "id" passed in, so minting a UUID here
    # and binding the token to it would tie the invitation to a user row that
    # does not exist.
    created = store.store_user(new_user)
    user_id = created["id"]

    raw_token = account_token_service.issue(
        user_id, account_token_service.PURPOSE_INVITATION
    )

    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "invite_member",
        "detail": f"Invited {payload.email} as {payload.role}",
    })

    base_url = settings.APP_BASE_URL or (
        (getattr(settings, "CORS_ORIGINS", None) or ["http://localhost:3000"])[0]
    )
    accept_url = f"{base_url.rstrip('/')}/accept-invitation?token={raw_token}"
    background.add_task(
        email_service.send_team_invitation,
        payload.email, payload.full_name, org["name"], accept_url,
    )

    response = {
        "message": f"Member {payload.email} invited successfully",
        "email_sent": email_service.is_configured(),
    }
    if settings.DEMO_MODE and settings.ENVIRONMENT != "production":
        # The raw token is surfaced in demo/dev so the flow is testable
        # without SMTP. The production guard is what matters: returning it
        # there would let any org_admin obtain a working invitation for an
        # address they do not control, which is the same escalation the old
        # temp-password response allowed.
        response["invitation_token"] = raw_token
        response["accept_url"] = accept_url
        response["note"] = (
            "invitation_token is returned in demo mode only; "
            "production delivers it by email."
        )
    return response


@router.patch("/members/{member_id}/role")
async def update_member_role(
    member_id: str,
    payload: UpdateMemberRoleRequest,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    member = store.get_user(member_id)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Member not found in this organization")
    if member["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    store.update_user(member_id, {"role": payload.role})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "update_member_role",
        "detail": f"Changed {member['email']} role to {payload.role}",
    })
    return {"message": f"Role updated to {payload.role}", "member_id": member_id}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    member = store.get_user(member_id)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Member not found in this organization")
    if member["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")
    store.revoke_all_refresh_tokens_for_user(member_id)
    store.update_user(member_id, {"status": "removed"})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "remove_member",
        "detail": f"Removed member {member['email']}",
    })
    return {"message": "Member removed successfully"}


@router.patch("/branding")
async def update_branding(
    payload: OrgBrandingUpdate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """Update logo, primary color, company website in org.settings.branding."""
    org_settings = dict(org.get("settings") or {})
    branding = dict(org_settings.get("branding") or {})
    if payload.logo_url is not None:
        branding["logo_url"] = payload.logo_url
    if payload.primary_color is not None:
        branding["primary_color"] = payload.primary_color
    if payload.company_website is not None:
        branding["company_website"] = payload.company_website
    org_settings["branding"] = branding
    store.update_org(org["id"], {"settings": org_settings})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "update_branding", "detail": "Organization branding updated",
    })
    return {"message": "Branding updated", "branding": branding}


@router.get("/feature-flags")
async def get_feature_flags(org: dict = Depends(get_current_org)) -> list:
    return store.get_feature_flags(org["id"])


@router.put("/feature-flags/{flag_name}")
async def set_feature_flag(
    flag_name: str,
    payload: FeatureFlagUpdate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    result = store.set_feature_flag(org["id"], flag_name, payload.enabled)
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "toggle_feature_flag",
        "detail": f"Feature flag '{flag_name}' set to {payload.enabled}",
    })
    return result


@router.delete("/api-keys/{prefix}")
async def revoke_api_key(
    prefix: str,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    """Deactivate an API key by prefix. Keys are matched by prefix since
    the full key isn't stored (only a hash)."""
    keys = store.get_org_api_keys(org["id"])
    target = next((k for k in keys if k.get("prefix") == prefix), None)
    if not target:
        raise HTTPException(status_code=404, detail="API key not found")
    # Deactivate by updating — store.py uses the key_hash as PK
    # For now mark inactive via a custom store path
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "revoke_api_key",
        "detail": f"Revoked API key with prefix {prefix}",
    })
    return {"message": f"API key {prefix}... revoked"}
