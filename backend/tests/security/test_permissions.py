"""PHASE 6 — Permission engine.

The class of bug these exist to prevent: an authorization check that denies
everyone forever without raising anything. `require_role("finance")` was live
in this codebase, gating remittance reconciliation on a role no user can hold.
It looked like delegation and behaved like a lockout.
"""
from __future__ import annotations

import pytest

from app.core.permissions import (
    ROLE_PERMISSIONS,
    ROLES,
    Permission,
    has_permission,
    permissions_for,
)

P = Permission


# ─────────────────────────── the matrix is coherent ──────────────────────────

def test_every_role_is_known():
    assert ROLES == {"viewer", "analyst", "warehouse_staff", "org_admin", "super_admin"}


def test_unknown_role_gets_nothing():
    """Fail closed.

    A role string that is not in the matrix -- from a bad import, a manual SQL
    edit, or a rolled-back deploy that left new role names in the users table
    -- must grant zero access, not fall through to something permissive.
    """
    assert permissions_for("chief_returns_wizard") == frozenset()
    assert has_permission("chief_returns_wizard", P.RETURNS_READ) is False
    assert has_permission("", P.RETURNS_READ) is False


def test_privilege_ladder_is_monotonic():
    """Higher roles must strictly contain lower ones.

    If analyst ever gains a permission org_admin lacks, an admin would have to
    downgrade themselves to do part of their job -- and someone would 'fix'
    that by granting admin rights broadly.
    """
    viewer = permissions_for("viewer")
    analyst = permissions_for("analyst")
    org_admin = permissions_for("org_admin")
    super_admin = permissions_for("super_admin")

    assert viewer < analyst
    assert analyst < org_admin
    assert org_admin < super_admin
    assert permissions_for("warehouse_staff") < org_admin


def test_super_admin_holds_everything():
    all_perms = frozenset().union(*ROLE_PERMISSIONS.values())
    assert permissions_for("super_admin") == all_perms


def test_platform_admin_is_super_admin_only():
    for role in ROLES - {"super_admin"}:
        assert not has_permission(role, P.PLATFORM_ADMIN), role


# ──────────────────────── specific business boundaries ───────────────────────

def test_viewer_cannot_change_anything():
    """A viewer is read-only. Every write permission must be absent."""
    writes = [
        P.RETURNS_CREATE, P.RETURNS_UPDATE, P.RETURNS_APPROVE, P.RETURNS_REJECT,
        P.RETURNS_DELETE, P.RISK_OVERRIDE, P.REMITTANCE_RECONCILE,
        P.ML_CONFIGURE, P.USERS_MANAGE, P.ORG_MANAGE, P.WORKFLOWS_MANAGE,
        P.INTEGRATIONS_MANAGE, P.BILLING_MANAGE,
    ]
    for perm in writes:
        assert not has_permission("viewer", perm), f"viewer should not have {perm}"


def test_warehouse_staff_can_decide_but_not_touch_money():
    """Warehouse staff inspect goods and decide on the evidence in front of
    them; they do not reconcile courier payments or manage billing."""
    assert has_permission("warehouse_staff", P.RETURNS_APPROVE)
    assert has_permission("warehouse_staff", P.RETURNS_REJECT)
    assert not has_permission("warehouse_staff", P.REMITTANCE_RECONCILE)
    assert not has_permission("warehouse_staff", P.BILLING_MANAGE)
    assert not has_permission("warehouse_staff", P.USERS_MANAGE)


def test_analyst_can_score_cod_but_not_reconcile():
    """The behaviour the old broken role check was reaching for.

    `require_role("org_admin", "warehouse_manager", "finance")` intended to
    delegate COD scoring beyond admins. It failed, because those roles do not
    exist. Reconciliation stays admin-only -- but now on purpose.
    """
    assert has_permission("analyst", P.COD_SCORE)
    assert has_permission("analyst", P.REMITTANCE_READ)
    assert not has_permission("analyst", P.REMITTANCE_RECONCILE)
    assert has_permission("org_admin", P.REMITTANCE_RECONCILE)


def test_only_admins_delete_returns():
    for role in ("viewer", "analyst", "warehouse_staff"):
        assert not has_permission(role, P.RETURNS_DELETE), role
    assert has_permission("org_admin", P.RETURNS_DELETE)


def test_risk_override_is_privileged():
    """Overriding a fraud score is a money decision dressed as a data edit."""
    for role in ("viewer", "analyst", "warehouse_staff"):
        assert not has_permission(role, P.RISK_OVERRIDE), role
    assert has_permission("org_admin", P.RISK_OVERRIDE)


# ─────────────────── the guard against the original bug ──────────────────────

def test_no_endpoint_gates_on_an_unassignable_role():
    """THE regression test for this phase.

    An endpoint gated on a role the invite schema cannot assign denies every
    user forever while raising nothing. Two such endpoints were live. This
    walks every `require_role(...)` still in the route layer and asserts each
    named role actually exists.
    """
    import pathlib
    import re

    routes_dir = pathlib.Path(__file__).resolve().parents[2] / "app/api/v1/routes"
    offenders: list[str] = []

    for path in routes_dir.glob("*.py"):
        # Strip comments before scanning. Migration notes legitimately quote
        # the old broken calls (e.g. `# was require_role("...", "finance")`),
        # and matching those would make this test fail on its own
        # documentation rather than on live code.
        code = "\n".join(
            line.split("#", 1)[0] for line in path.read_text().splitlines()
        )
        for call in re.findall(r"require_role\(([^)]*)\)", code):
            for role in re.findall(r'"([^"]+)"', call):
                if role not in ROLES:
                    offenders.append(f"{path.name}: require_role(...{role!r}...)")

    assert not offenders, (
        "Endpoints gated on roles no user can hold -- these deny everyone "
        "silently:\n  " + "\n  ".join(offenders)
    )


def test_require_permission_rejects_unknown_permission_at_import():
    """A typo must break the build, not disable a feature quietly."""
    from app.api.v1.deps import require_permission

    with pytest.raises(ValueError, match="Unknown permission"):
        require_permission("retunrs.raed")          # transposed on purpose

    # And the correct spelling builds fine.
    assert require_permission(P.RETURNS_READ) is not None


def test_permission_strings_are_namespaced():
    """`resource.action` keeps audit logs and future API scopes parseable."""
    all_perms = frozenset().union(*ROLE_PERMISSIONS.values())
    for perm in all_perms:
        assert perm.count(".") == 1, perm
        resource, action = perm.split(".")
        assert resource and action
        assert perm == perm.lower()
