"""Organization management — settings, API keys, members, audit logs."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_org, require_permission, require_role
from app.core.permissions import Permission
from app.core.config import get_settings
from app.core.security import generate_api_key, hash_api_key
from app.db import store
from app.services import webhook_security
from app.services import audit_service
from app.schemas.schemas import ApiKeyCreate, OrgSettingsUpdate

settings = get_settings()
router = APIRouter(prefix="/api/v1/org", tags=["organization"])


@router.get("/")
async def get_org(org: dict = Depends(get_current_org)) -> dict:
    return org


@router.patch("/settings")
async def update_settings(
    payload: OrgSettingsUpdate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    updates: dict = {}
    if payload.risk_threshold is not None:
        updates["risk_threshold"] = payload.risk_threshold

    org_settings = dict(org.get("settings") or {})
    if payload.currency is not None:
        org_settings["currency"] = payload.currency
    if payload.timezone is not None:
        org_settings["timezone"] = payload.timezone
    if payload.auto_approve_below_risk is not None:
        org_settings["auto_approve_below_risk"] = payload.auto_approve_below_risk
    if payload.notify_on_fraud is not None:
        org_settings["notify_on_fraud"] = payload.notify_on_fraud
    if payload.webhook_url is not None:
        # PHASE 33: validate before storing.
        #
        # This field was Optional[str] with no checking, so
        # http://169.254.169.254/latest/meta-data/iam/security-credentials/
        # returned 200 OK. That is the cloud instance metadata endpoint:
        # ReturnIQ's own server would fetch the IAM credentials of the machine
        # it runs on and deliver them to an attacker-controlled destination.
        if payload.webhook_url.strip():
            try:
                org_settings["webhook_url"] = webhook_security.validate_webhook_url(
                    payload.webhook_url
                )
            except webhook_security.WebhookUrlError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        else:
            org_settings["webhook_url"] = ""
    updates["settings"] = org_settings

    updated_org = store.update_org(org["id"], updates)
    store.add_audit_log({"org_id": org["id"], "user_id": user["id"], "action": "update", "detail": "Organization settings updated"})
    return updated_org


@router.get("/api-keys")
async def list_api_keys(org: dict = Depends(get_current_org)) -> list:
    keys = store.get_org_api_keys(org["id"])
    return [{"name": k["name"], "prefix": k["prefix"], "is_active": k["is_active"], "created_at": k["created_at"]} for k in keys]


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyCreate,
    user: dict = Depends(require_role("org_admin", "super_admin")),
    org: dict = Depends(get_current_org),
) -> dict:
    raw_key, prefix = generate_api_key()
    key_hash = hash_api_key(raw_key, settings.API_KEY_HASH_PEPPER)
    record = {
        "org_id": org["id"], "name": payload.name,
        "prefix": prefix, "is_active": True,
        "created_at": datetime.now(UTC),
    }
    store.store_api_key(key_hash, record)
    store.add_audit_log({"org_id": org["id"], "user_id": user["id"], "action": "api_key_generated", "detail": f"API key '{payload.name}' created"})
    return {"name": payload.name, "prefix": prefix, "raw_api_key": raw_key, "note": "Save this key — it will not be shown again"}


@router.get("/members")
async def list_members(org: dict = Depends(get_current_org)) -> list:
    members = store.get_users_for_org(org["id"])
    return [{"id": m["id"], "email": m["email"], "full_name": m["full_name"],
             "role": m["role"], "status": m["status"], "last_login": m.get("last_login")} for m in members]


@router.get("/audit-logs")
async def get_audit_logs(
    user: dict = Depends(require_permission(Permission.AUDIT_READ)),
    org: dict = Depends(get_current_org),
) -> list:
    return store.get_audit_logs(org["id"])


@router.get("/audit-logs/verify")
async def verify_audit_integrity(
    user: dict = Depends(require_permission(Permission.AUDIT_READ)),
    org: dict = Depends(get_current_org),
) -> dict:
    """PHASE 8: verify this organization's audit chain has not been altered.

    Exposed to org admins rather than kept internal on purpose. An audit trail
    whose integrity only the vendor can check asks the customer to take the
    vendor's word for it -- which is the assurance an audit trail exists to
    replace. A merchant under DPDP or contractual obligation should be able to
    demonstrate integrity themselves, on demand.

    A false result identifies the first broken event, so everything recorded
    before that point remains usable evidence.
    """
    return audit_service.verify_chain(org["id"])


@router.get("/notifications")
async def get_notifications(org: dict = Depends(get_current_org)) -> list:
    return store.get_notifications_for_org(org["id"])


@router.get("/demo-key", tags=["setup"])
async def get_demo_key() -> dict:
    """Demo API key — only available in DEMO_MODE. Same endpoint as v2 for backward compat."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Not available in production")
    creds = store.get_demo_credentials()
    return {
        "demo_api_key": (creds or {}).get("api_key", ""),
        "demo_credentials": {"email": "admin@sapnacollection.com", "password": "Demo@12345"},
        "note": "Use these credentials to log in, or the API key for direct API calls.",
    }
