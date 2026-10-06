"""PHASE 34 — public API: key scoping.

WHAT THE AUDIT FOUND
--------------------
`api_keys` has six columns: key_hash, org_id, name, prefix, is_active,
created_at. There are **no scopes**.

`get_org_from_api_key()` returns the organization and nothing else, so every
key grants everything the external API exposes. A key handed to a read-only
analytics vendor can create returns. A key embedded in a storefront widget —
where it is visible to anyone who opens developer tools — can do the same.

Phase 6 built a permission system precisely so that "who can do what" has one
answer. **API keys bypass it entirely**, which means the answer is one thing
for staff and another for integrations, and only one of those is written down.

Two further gaps:

**No expiry.** A key issued today works forever. The integration it was
created for is decommissioned, the contractor moves on, the key stays valid.

**No usage tracking.** Nobody can answer "is this key still in use?", so
nobody ever revokes one — revoking an unknown key risks breaking an unknown
integration, and the safe-feeling choice is always to leave it.

THE DESIGN
----------
Scopes reuse the Phase 6 permission strings rather than inventing a parallel
vocabulary. `returns.read` means the same thing whether a person or a key
holds it, so there is one model to reason about and one place to audit.

A key's scopes are a **subset** of what its creating role could grant. An
analyst cannot mint a key with `org.manage` — otherwise key creation becomes
a privilege-escalation primitive, and the Phase 6 matrix is decorative for
anyone who can click "create API key".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from app.core.permissions import Permission, permissions_for

__all__ = [
    "ApiKeyScopeError",
    "DEFAULT_SCOPES",
    "PUBLIC_API_SCOPES",
    "MAX_KEY_LIFETIME",
    "validate_scopes",
    "key_has_permission",
    "describe_scopes",
]


class ApiKeyScopeError(ValueError):
    """A key configuration that must not be created."""


# Permissions meaningful over the public API. Deliberately narrower than the
# full Phase 6 set: user management, billing and integration configuration are
# console operations, and exposing them to a key that may be pasted into a
# CI config widens the blast radius of a leak for no integration benefit.
PUBLIC_API_SCOPES: Final[frozenset[str]] = frozenset({
    Permission.RETURNS_READ,
    Permission.RETURNS_CREATE,
    Permission.RETURNS_UPDATE,
    Permission.RETURNS_APPROVE,
    Permission.RETURNS_REJECT,
    Permission.RISK_READ,
    Permission.COD_SCORE,
    Permission.REMITTANCE_READ,
    Permission.REPORTS_READ,
    Permission.ML_READ,
})

# What a key gets when the caller does not specify. Read-only.
#
# The default matters more than the maximum: most keys are created by someone
# in a hurry who accepts whatever is offered. A permissive default means most
# keys in the wild are permissive.
DEFAULT_SCOPES: Final[frozenset[str]] = frozenset({
    Permission.RETURNS_READ,
    Permission.RISK_READ,
    Permission.REPORTS_READ,
})

# Keys expire. A year is long enough not to be an operational nuisance and
# short enough that a forgotten key does not outlive the integration by
# several years.
MAX_KEY_LIFETIME: Final[timedelta] = timedelta(days=365)

# Scopes that let a key change money or state. Flagged so the creating UI can
# require a second look, and so an audit can list them.
WRITE_SCOPES: Final[frozenset[str]] = frozenset({
    Permission.RETURNS_CREATE,
    Permission.RETURNS_UPDATE,
    Permission.RETURNS_APPROVE,
    Permission.RETURNS_REJECT,
    Permission.COD_SCORE,
})


def validate_scopes(requested: list[str] | None, *, creator_role: str) -> frozenset[str]:
    """Resolve and check the scopes for a new key.

    Refuses anything the creating role does not itself hold. Without this,
    creating an API key is a privilege-escalation primitive: an analyst who
    cannot approve returns mints a key that can, then uses the key.
    """
    if not requested:
        return DEFAULT_SCOPES

    scopes = frozenset(s.strip() for s in requested if s and s.strip())
    if not scopes:
        return DEFAULT_SCOPES

    unknown = sorted(scopes - PUBLIC_API_SCOPES)
    if unknown:
        raise ApiKeyScopeError(
            f"These are not scopes available over the public API: "
            f"{', '.join(unknown)}. Available: "
            f"{', '.join(sorted(PUBLIC_API_SCOPES))}."
        )

    held = permissions_for(creator_role)
    exceeded = sorted(scopes - held)
    if exceeded:
        raise ApiKeyScopeError(
            f"You cannot create a key with permissions you do not have "
            f"yourself: {', '.join(exceeded)}. Otherwise creating an API key "
            f"would be a way around your own role."
        )

    return scopes


def key_has_permission(key_scopes: list[str] | None, permission: str) -> bool:
    """Does this key permit the operation?

    A key with no recorded scopes returns **False**, not True.

    That choice matters for the migration: existing keys predate scoping and
    have no scopes column populated. Failing open would leave every current
    key omnipotent — exactly the state this phase exists to end — and the
    failure would be invisible because everything would keep working.

    Failing closed breaks existing integrations loudly at deploy, which is
    recoverable in minutes by assigning scopes. The migration therefore
    backfills existing keys explicitly rather than relying on a default.
    """
    if not key_scopes:
        return False
    return permission in set(key_scopes)


@dataclass(frozen=True)
class ScopeDescription:
    scope: str
    label: str
    is_write: bool

    def as_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "label": self.label, "write": self.is_write}


_LABELS: Final[dict[str, str]] = {
    Permission.RETURNS_READ: "Read returns and their details",
    Permission.RETURNS_CREATE: "Create new returns",
    Permission.RETURNS_UPDATE: "Update return details",
    Permission.RETURNS_APPROVE: "Approve returns",
    Permission.RETURNS_REJECT: "Reject returns",
    Permission.RISK_READ: "Read risk and fraud scores",
    Permission.COD_SCORE: "Score cash-on-delivery orders",
    Permission.REMITTANCE_READ: "Read courier remittance records",
    Permission.REPORTS_READ: "Read reports and analytics",
    Permission.ML_READ: "Read model predictions",
}


def describe_scopes(scopes: list[str] | None) -> list[dict[str, Any]]:
    """Plain-English scope list for the key-creation screen and for audit.

    `returns.approve` means nothing to the person pasting a key into a vendor
    portal. "Approve returns" tells them what they are handing over.
    """
    return [
        ScopeDescription(
            scope=scope,
            label=_LABELS.get(scope, scope),
            is_write=scope in WRITE_SCOPES,
        ).as_dict()
        for scope in sorted(scopes or [])
    ]


@dataclass
class KeyHealth:
    """Whether a key should still exist.

    Answers the question that makes revocation possible. Nobody revokes a key
    they cannot describe, so an unused key sits active for years because
    removing it risks breaking an unknown integration.
    """

    name: str
    prefix: str
    is_active: bool
    created_at: str
    last_used_at: str | None
    expires_at: str | None
    scopes: list[str] = field(default_factory=list)

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        findings: list[str] = []

        if not self.is_active:
            return {"status": "revoked", "findings": []}

        if self.expires_at:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", ""))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry < now:
                findings.append("Expired — this key no longer authenticates.")
            elif (expiry - now).days <= 30:
                findings.append(
                    f"Expires in {(expiry - now).days} days. Rotate it before "
                    f"the integration breaks."
                )
        else:
            findings.append(
                "No expiry. This key works forever, including after the "
                "integration it was made for is gone."
            )

        if self.last_used_at is None:
            findings.append(
                "Never used. If nothing depends on it, revoking costs nothing."
            )
        else:
            used = datetime.fromisoformat(self.last_used_at.replace("Z", ""))
            if used.tzinfo is None:
                used = used.replace(tzinfo=UTC)
            idle_days = (now - used).days
            if idle_days > 90:
                findings.append(
                    f"Unused for {idle_days} days. Likely a leftover from a "
                    f"decommissioned integration."
                )

        write_scopes = sorted(set(self.scopes) & WRITE_SCOPES)
        if write_scopes:
            findings.append(
                f"Can change data: {', '.join(write_scopes)}. Confirm this key "
                f"is stored somewhere appropriate for a write credential."
            )

        return {
            "status": "attention" if findings else "healthy",
            "findings": findings,
        }
