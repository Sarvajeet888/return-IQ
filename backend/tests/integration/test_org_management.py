"""
Organisation member management tests (Phase 9 — closes coverage gap #2).

Role changes and member removal are access-control operations: getting them
wrong means either a user keeps privileges they shouldn't, or an admin can
tamper with an org they don't belong to. They deserve the same rigour the
auth module got.
"""
from __future__ import annotations
import uuid

import pytest


def _org(client, label="orgmgmt"):
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={
        "full_name": f"Admin {label}", "email": email, "password": "TestPass123",
        "org_name": f"Org {uuid.uuid4().hex[:6]}", "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"], email


def _invite(client, admin_token, role="analyst"):
    """Invite a member, accept the invitation, log in.

    PHASE 5: invitation no longer returns a working password. The full
    journey is invite -> accept with a one-time token -> sign in, which is
    what a real user does, so exercising it here is more faithful than the
    previous shortcut.
    """
    email = f"member_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/org/members/invite",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"email": email, "full_name": "Team Member", "role": role})
    assert r.status_code == 200, r.text
    token = r.json()["invitation_token"]

    password = "MemberPass123"
    accepted = client.post("/api/v1/auth/accept-invitation",
                           json={"token": token, "password": password})
    assert accepted.status_code == 200, accepted.text

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["user"]["id"], email, password


# ── Role management ──────────────────────────────────────────────────────────

def test_admin_can_change_member_role(app_client):
    token, _ = _org(app_client, "rolechange")
    h = {"Authorization": f"Bearer {token}"}
    member_id, email, _ = _invite(app_client, token, role="viewer")

    r = app_client.patch(f"/api/v1/org/members/{member_id}/role",
                         headers=h, json={"role": "org_admin"})
    assert r.status_code == 200, r.text
    assert r.json()["message"].endswith("org_admin")


def test_role_change_actually_takes_effect(app_client):
    """
    The endpoint returning 200 isn't enough - the new role must be live on
    the member's next login. A role update that doesn't persist is worse
    than one that errors, because nobody notices.
    """
    token, _ = _org(app_client, "roleeffect")
    h = {"Authorization": f"Bearer {token}"}
    member_id, email, password = _invite(app_client, token, role="viewer")

    app_client.patch(f"/api/v1/org/members/{member_id}/role",
                     headers=h, json={"role": "analyst"})

    login = app_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.json()["user"]["role"] == "analyst", "role change did not persist"


def test_admin_cannot_change_own_role(app_client):
    """Prevents an admin locking themselves out or self-escalating."""
    token, email = _org(app_client, "selfrole")
    h = {"Authorization": f"Bearer {token}"}

    # NOTE: /auth/me returns user fields flattened at the top level,
    # whereas /auth/login nests them under "user". Documented in
    # test_api_shape_consistency below.
    my_id = app_client.get("/api/v1/auth/me", headers=h).json()["id"]

    r = app_client.patch(f"/api/v1/org/members/{my_id}/role",
                         headers=h, json={"role": "viewer"})
    assert r.status_code == 400, "admin was allowed to change their own role"


def test_cannot_change_role_of_member_in_another_org(app_client):
    """Cross-tenant access control on a privileged operation."""
    token_a, _ = _org(app_client, "orgA")
    token_b, _ = _org(app_client, "orgB")
    member_id, _, _ = _invite(app_client, token_a, role="viewer")

    r = app_client.patch(f"/api/v1/org/members/{member_id}/role",
                         headers={"Authorization": f"Bearer {token_b}"},
                         json={"role": "org_admin"})
    assert r.status_code == 404, (
        "CROSS-TENANT PRIVILEGE ESCALATION: org B changed a role in org A"
    )


@pytest.mark.parametrize("bad_role", ["super_admin", "root", "administrator", "", "ORG_ADMIN"])
def test_invalid_role_rejected(app_client, bad_role):
    """
    super_admin especially must not be assignable through the org endpoint -
    that would be a privilege escalation path out of the tenant.
    """
    token, _ = _org(app_client, "badrole")
    h = {"Authorization": f"Bearer {token}"}
    member_id, _, _ = _invite(app_client, token)

    r = app_client.patch(f"/api/v1/org/members/{member_id}/role",
                         headers=h, json={"role": bad_role})
    assert r.status_code == 422, f"invalid role {bad_role!r} was accepted"


def test_viewer_cannot_change_roles(app_client):
    """Only org_admin+ may manage roles."""
    token, _ = _org(app_client, "viewerrole")
    _, viewer_email, viewer_pw = _invite(app_client, token, role="viewer")
    target_id, _, _ = _invite(app_client, token, role="viewer")

    viewer_token = app_client.post("/api/v1/auth/login", json={
        "email": viewer_email, "password": viewer_pw,
    }).json()["access_token"]

    r = app_client.patch(f"/api/v1/org/members/{target_id}/role",
                         headers={"Authorization": f"Bearer {viewer_token}"},
                         json={"role": "org_admin"})
    assert r.status_code == 403, "PRIVILEGE ESCALATION: viewer changed a role"


# ── Member removal ───────────────────────────────────────────────────────────

def test_admin_can_remove_member(app_client):
    token, _ = _org(app_client, "remove")
    h = {"Authorization": f"Bearer {token}"}
    member_id, _, _ = _invite(app_client, token)

    r = app_client.delete(f"/api/v1/org/members/{member_id}", headers=h)
    assert r.status_code == 200, r.text


def test_removed_member_cannot_login(app_client):
    """Removal must actually revoke access, not just flip a flag in a list view."""
    token, _ = _org(app_client, "removelogin")
    h = {"Authorization": f"Bearer {token}"}
    member_id, email, password = _invite(app_client, token)

    app_client.delete(f"/api/v1/org/members/{member_id}", headers=h)

    r = app_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code in (401, 403), (
        f"removed member could still log in (status {r.status_code})"
    )


def test_admin_cannot_remove_self(app_client):
    token, _ = _org(app_client, "removeself")
    h = {"Authorization": f"Bearer {token}"}
    my_id = app_client.get("/api/v1/auth/me", headers=h).json()["id"]

    r = app_client.delete(f"/api/v1/org/members/{my_id}", headers=h)
    assert r.status_code == 400, "admin removed themselves - org could be orphaned"


def test_cannot_remove_member_from_another_org(app_client):
    token_a, _ = _org(app_client, "remA")
    token_b, _ = _org(app_client, "remB")
    member_id, _, _ = _invite(app_client, token_a)

    r = app_client.delete(f"/api/v1/org/members/{member_id}",
                          headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 404, "CROSS-TENANT: org B removed a member from org A"


def test_remove_nonexistent_member_returns_404(app_client):
    token, _ = _org(app_client, "remnone")
    r = app_client.delete(f"/api/v1/org/members/{uuid.uuid4()}",
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


# ── Invited member permissions ───────────────────────────────────────────────

def test_invited_analyst_can_read_returns(app_client):
    token, _ = _org(app_client, "analystread")
    _, email, password = _invite(app_client, token, role="analyst")

    analyst_token = app_client.post("/api/v1/auth/login", json={
        "email": email, "password": password}).json()["access_token"]

    r = app_client.get("/api/v1/returns", headers={"Authorization": f"Bearer {analyst_token}"})
    assert r.status_code == 200


def test_invited_member_scoped_to_inviting_org(app_client):
    """An invited member must see their org's data, and only their org's."""
    token_a, _ = _org(app_client, "scopeA")
    token_b, _ = _org(app_client, "scopeB")

    # Org A creates a return
    app_client.post("/api/v1/returns", headers={"Authorization": f"Bearer {token_a}"}, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "c@example.com", "sku": "SKU-ORGA-SECRET",
        "item_category": "Electronics", "item_value": 1000.0,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "weight_grams": 1000, "volumetric_weight_grams": 1200,
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False, "condition": "good",
    })

    # Org B invites a member
    _, email, password = _invite(app_client, token_b, role="analyst")
    member_token = app_client.post("/api/v1/auth/login", json={
        "email": email, "password": password}).json()["access_token"]

    r = app_client.get("/api/v1/returns", headers={"Authorization": f"Bearer {member_token}"})
    assert "SKU-ORGA-SECRET" not in r.text, "invited member saw another org's data"


# ── Branding & feature flags ─────────────────────────────────────────────────

def test_admin_can_update_branding(app_client):
    token, _ = _org(app_client, "branding")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.patch("/api/v1/org/branding", headers=h, json={
        "logo_url": "https://cdn.example.com/logo.png",
        "primary_color": "#6366f1",
        "company_website": "https://example.com",
    })
    assert r.status_code == 200, r.text
    assert r.json()["branding"]["primary_color"] == "#6366f1"


def test_viewer_cannot_update_branding(app_client):
    token, _ = _org(app_client, "brandviewer")
    _, email, password = _invite(app_client, token, role="viewer")
    viewer_token = app_client.post("/api/v1/auth/login", json={
        "email": email, "password": password}).json()["access_token"]

    r = app_client.patch("/api/v1/org/branding",
                         headers={"Authorization": f"Bearer {viewer_token}"},
                         json={"primary_color": "#000000"})
    assert r.status_code == 403


def test_feature_flag_set_and_read_back(app_client):
    token, _ = _org(app_client, "flags")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.put("/api/v1/org/feature-flags/beta_dashboard",
                       headers=h, json={"enabled": True})
    assert r.status_code == 200, r.text

    r = app_client.get("/api/v1/org/feature-flags", headers=h)
    assert r.status_code == 200
    flags = {f["flag_name"]: f["enabled"] for f in r.json()}
    assert flags.get("beta_dashboard") is True


def test_feature_flags_are_org_scoped(app_client):
    token_a, _ = _org(app_client, "flagA")
    token_b, _ = _org(app_client, "flagB")

    app_client.put("/api/v1/org/feature-flags/secret_feature",
                   headers={"Authorization": f"Bearer {token_a}"}, json={"enabled": True})

    r = app_client.get("/api/v1/org/feature-flags",
                       headers={"Authorization": f"Bearer {token_b}"})
    names = {f["flag_name"] for f in r.json()}
    assert "secret_feature" not in names, "org B saw org A's feature flags"


def test_toggling_flag_twice_updates_not_duplicates(app_client):
    """Setting the same flag again must update the row, not insert a second one."""
    token, _ = _org(app_client, "flagtoggle")
    h = {"Authorization": f"Bearer {token}"}

    app_client.put("/api/v1/org/feature-flags/toggle_me", headers=h, json={"enabled": True})
    app_client.put("/api/v1/org/feature-flags/toggle_me", headers=h, json={"enabled": False})

    flags = app_client.get("/api/v1/org/feature-flags", headers=h).json()
    matching = [f for f in flags if f["flag_name"] == "toggle_me"]
    assert len(matching) == 1, f"duplicate flag rows created: {len(matching)}"
    assert matching[0]["enabled"] is False


# ── API shape consistency (documents a real inconsistency) ───────────────────

def test_me_and_login_expose_the_same_user_fields(app_client):
    """
    /auth/login returns the user nested under "user"; /auth/me returns the
    same fields flattened at the top level. That inconsistency is a papercut
    for API consumers - this test documents the current contract so a future
    change to either endpoint is a deliberate decision, not an accident.
    """
    token, email = _org(app_client, "shape")
    login = app_client.post("/api/v1/auth/login",
                            json={"email": email, "password": "TestPass123"}).json()
    me = app_client.get("/api/v1/auth/me",
                        headers={"Authorization": f"Bearer {token}"}).json()

    # login nests, /me flattens
    assert "user" in login, "/auth/login no longer nests the user object"
    assert "user" not in me, "/auth/me now nests - update API_GUIDE.md and clients"

    # Whatever the shape, the same core fields must be present in both
    for field in ["id", "email", "full_name", "role"]:
        assert field in login["user"], f"/auth/login user missing {field}"
        assert field in me, f"/auth/me missing {field}"
        assert login["user"][field] == me[field], f"{field} differs between endpoints"
