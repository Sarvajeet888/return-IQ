"""FastAPI dependency injection — JWT, API key auth, RBAC."""
from __future__ import annotations

from typing import Optional

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.core.config import get_settings
from app.core.security import decode_token, hash_api_key
from app.db import store
from app.services import api_key_scopes

settings = get_settings()
bearer = HTTPBearer(auto_error=False)


_ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer)
) -> dict:
    """Extract and validate JWT bearer token → return user dict."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    jti = payload.get("jti")
    if jti and store.is_access_token_revoked(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    user = store.get_user(payload["sub"])
    if not user or user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # attach decoded info
    user["_token_payload"] = payload
    return user


def get_current_org(user: dict = Depends(get_current_user)) -> dict:
    """Return org for authenticated user."""
    org = store.get_org(user["org_id"])
    if not org or not org.get("is_active"):
        raise HTTPException(status_code=403, detail="Organization not found or inactive")
    return org


def require_permission(*permissions: str):
    """PHASE 6: dependency factory gating on permissions, not role names.

    Multiple permissions are ANDed -- the caller needs all of them. That is
    the safe default: OR semantics would mean adding a permission to an
    endpoint could *widen* access, which is a surprising direction for a
    security control to move when you edit it.

    Unknown permission strings raise at import time rather than denying
    silently. This is the specific failure that made role checks dangerous:
    `require_role("finance")` served traffic happily while denying everyone,
    because no user could hold that role. A typo should break the build, not
    quietly disable a feature.
    """
    unknown = [p for p in permissions if p not in _ALL_PERMISSIONS]
    if unknown:
        raise ValueError(
            f"Unknown permission(s): {unknown}. "
            f"Add them to app.core.permissions.Permission first -- an "
            f"undefined permission would deny every user forever without "
            f"raising anything."
        )

    def _check(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "")
        missing = [p for p in permissions if not has_permission(role, p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                # Name the permission, not the roles that hold it. Telling a
                # user "requires org_admin" leaks the role model and invites
                # social-engineering an admin; "requires returns.approve" tells
                # them what to ask for.
                detail=f"Insufficient permissions. Required: {missing}",
            )
        return user

    return _check


def require_role(*roles: str):
    """DEPRECATED (Phase 6) — retained so existing endpoints keep working.

    Translates a role list into the permissions those roles share, then defers
    to the permission check. Kept during migration so the 30 existing call
    sites do not all have to change in one commit; new endpoints should use
    require_permission directly.
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles and user["role"] != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {list(roles)}"
            )
        return user
    return _check


def get_org_from_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Validate X-API-Key header → return org dict. Backward compatible with v2."""
    key_hash = hash_api_key(x_api_key, settings.API_KEY_HASH_PEPPER)
    record = store.get_api_key_record(key_hash)
    if not record or not record.get("is_active"):
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    # PHASE 34: expiry is checked here, not left to a cleanup job. A key whose
    # expiry has passed but whose row still exists must not authenticate.
    expires_at = record.get("expires_at")
    if expires_at:
        expiry = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(
            str(expires_at).replace("Z", "")
        )
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry < datetime.now(UTC):
            raise HTTPException(
                status_code=401,
                detail="This API key has expired. Create a new one in the "
                       "console under API keys.",
            )

    org = store.get_org(record["org_id"])
    if not org or not org.get("is_active"):
        raise HTTPException(status_code=403, detail="Organization not found or inactive")

    # Usage is recorded so keys become revocable. Nobody removes a key they
    # cannot describe, so an unused key stays active for years because
    # deleting it risks breaking an unknown integration.
    store.touch_api_key(record["key_hash"])

    # The scopes travel with the org so downstream dependencies can enforce
    # them without re-reading the key.
    return {**org, "_api_key_scopes": record.get("scopes") or [], "_via_api_key": True}


def require_api_scope(permission: str):
    """Dependency factory: this endpoint needs this scope on the key.

    Separate from `require_permission` because the subject differs — that one
    checks a user's role, this one checks a key's grant. Same permission
    strings on purpose, so there is one vocabulary to audit rather than two.
    """
    if permission not in _ALL_PERMISSIONS:
        raise ValueError(
            f"Unknown permission {permission!r}. Add it to "
            f"app.core.permissions.Permission first — an undefined scope "
            f"would deny every key forever without raising anything."
        )

    def _check(org: dict = Depends(get_org_from_api_key)) -> dict:
        if not api_key_scopes.key_has_permission(
            org.get("_api_key_scopes"), permission
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This API key does not have the {permission!r} scope. "
                    f"Create a key with that scope, or use one that has it."
                ),
            )
        return org

    return _check
