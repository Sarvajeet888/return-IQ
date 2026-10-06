"""PHASE 6 — Permission engine.

WHY REPLACE ROLE CHECKS
-----------------------
Authorization was expressed as role strings at each endpoint:

    require_role("org_admin", "warehouse_manager", "finance")

Three problems that this module fixes.

**1. Role sets drift.** `("org_admin", "super_admin")` and
`("super_admin", "org_admin")` appear in different files meaning the same
thing, and `super_admin` is redundant everywhere because the check already
bypasses for it. Thirty call sites, no single place to see who can do what.

**2. Typos are unreachable code, not errors.** `require_role("finance")`
compiles, imports, and serves traffic. It simply denies everyone forever,
because no user can ever hold that role. A real instance of this was live in
the codebase -- see `_UNASSIGNABLE_ROLES_FOUND` below.

**3. Adding a role means auditing every endpoint.** With permissions, a new
role is one entry in `ROLE_PERMISSIONS`; endpoints never change.

WHAT THIS IS NOT
----------------
This is still role-based access control, not attribute-based. Resource-level
and warehouse-level permissions ("this manager, but only for the Pune
warehouse") are Phase 6's stretch goal and are deliberately not attempted
here -- they need a resource-scoping model that does not exist yet.
"""
from __future__ import annotations

from typing import Final

__all__ = [
    "Permission",
    "ROLE_PERMISSIONS",
    "ROLES",
    "has_permission",
    "permissions_for",
]


class Permission:
    """Permission constants, namespaced `resource.action`.

    Strings rather than an Enum on purpose: they are persisted in audit logs
    and will eventually appear in customer-defined roles and API scopes, so a
    stable wire representation matters more than type-checking convenience.
    """

    # Returns
    RETURNS_READ: Final = "returns.read"
    RETURNS_CREATE: Final = "returns.create"
    RETURNS_UPDATE: Final = "returns.update"
    RETURNS_APPROVE: Final = "returns.approve"
    RETURNS_REJECT: Final = "returns.reject"
    RETURNS_DELETE: Final = "returns.delete"

    # Risk & fraud
    RISK_READ: Final = "risk.read"
    RISK_OVERRIDE: Final = "risk.override"
    COD_SCORE: Final = "cod.score"

    # Finance
    REMITTANCE_READ: Final = "remittance.read"
    REMITTANCE_RECONCILE: Final = "remittance.reconcile"

    # Reporting
    REPORTS_READ: Final = "reports.read"
    REPORTS_EXPORT: Final = "reports.export"

    # ML
    ML_READ: Final = "ml.read"
    ML_CONFIGURE: Final = "ml.configure"

    # Administration
    USERS_MANAGE: Final = "users.manage"
    ORG_MANAGE: Final = "org.manage"
    INTEGRATIONS_MANAGE: Final = "integrations.manage"
    WORKFLOWS_MANAGE: Final = "workflows.manage"
    AUDIT_READ: Final = "audit.read"
    BILLING_MANAGE: Final = "billing.manage"

    # Platform
    PLATFORM_ADMIN: Final = "platform.admin"


P = Permission

# ─────────────────────────────────────────────────────────────────────────────
# The matrix. This is the single place that answers "who can do what".
# ─────────────────────────────────────────────────────────────────────────────

_VIEWER: Final[frozenset[str]] = frozenset({
    P.RETURNS_READ,
    P.RISK_READ,
    P.REPORTS_READ,
    P.ML_READ,
})

_ANALYST: Final[frozenset[str]] = _VIEWER | {
    P.RETURNS_CREATE,
    P.RETURNS_UPDATE,
    P.REPORTS_EXPORT,
    P.COD_SCORE,
    P.REMITTANCE_READ,
}

# Warehouse staff physically handle returned goods: they inspect, update
# condition, and approve or reject on the evidence in front of them. They do
# not touch money or configuration.
_WAREHOUSE_STAFF: Final[frozenset[str]] = _VIEWER | {
    P.RETURNS_UPDATE,
    P.RETURNS_APPROVE,
    P.RETURNS_REJECT,
}

_ORG_ADMIN: Final[frozenset[str]] = _ANALYST | _WAREHOUSE_STAFF | {
    P.RETURNS_DELETE,
    P.RISK_OVERRIDE,
    P.REMITTANCE_RECONCILE,
    P.ML_CONFIGURE,
    P.USERS_MANAGE,
    P.ORG_MANAGE,
    P.INTEGRATIONS_MANAGE,
    P.WORKFLOWS_MANAGE,
    P.AUDIT_READ,
    P.BILLING_MANAGE,
}

# Every permission, including platform administration. super_admin is an
# Anthropic-side/operator role, not something a customer org can grant itself.
_SUPER_ADMIN: Final[frozenset[str]] = _ORG_ADMIN | {P.PLATFORM_ADMIN}

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "viewer": _VIEWER,
    "analyst": _ANALYST,
    "warehouse_staff": _WAREHOUSE_STAFF,
    "org_admin": _ORG_ADMIN,
    "super_admin": _SUPER_ADMIN,
}

ROLES: Final[frozenset[str]] = frozenset(ROLE_PERMISSIONS)

# Documented for the migration, and asserted in tests: two endpoints previously
# gated on roles that no user could ever hold, because the invite schema only
# permits {org_admin, analyst, warehouse_staff, viewer}.
#
#   cod_risk.py    require_role("org_admin", "warehouse_manager", "finance")
#   remittance.py  require_role("org_admin", "finance")
#
# Effect: COD scoring and remittance reconciliation were org_admin-only in
# practice, while appearing to be delegable. Analysts were silently locked out
# of a feature the code implied they had. Now expressed as COD_SCORE (analyst
# and above) and REMITTANCE_RECONCILE (org_admin), which is the intent the
# role names were reaching for.
_UNASSIGNABLE_ROLES_FOUND: Final[frozenset[str]] = frozenset(
    {"warehouse_manager", "finance"}
)


def permissions_for(role: str) -> frozenset[str]:
    """Permissions granted by a role. Unknown roles get nothing.

    Fails closed: an unrecognised role in the database -- from a bad import, a
    manual SQL edit, or a rolled-back deploy that left new role strings behind
    -- results in no access rather than defaulting to something permissive.
    """
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    """Does this role grant this permission?

    No special-casing of super_admin here. Its elevation is expressed in the
    matrix above, so the matrix stays the complete answer to "who can do what"
    rather than the answer *plus* an implicit bypass in the checking code.
    """
    return permission in permissions_for(role)
