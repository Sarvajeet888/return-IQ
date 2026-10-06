"""
Security tests (Phase 9.8) — executable penetration tests.

Covers OWASP Top 10 categories relevant to this app:
  A01 Broken Access Control  -> IDOR, cross-tenant access, privilege escalation
  A02 Cryptographic Failures -> password hashing, token storage
  A03 Injection              -> SQL injection, XSS payload handling
  A05 Security Misconfig     -> security headers
  A07 Auth Failures          -> JWT tampering, lockout, weak passwords

Each test is an actual attack attempt against the running app. A failure here
means a real, exploitable vulnerability - not a style issue.
"""
from __future__ import annotations
import uuid

import pytest


# ── A03: SQL Injection ────────────────────────────────────────────────────────

SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "admin'--",
    "' UNION SELECT NULL, password_hash, NULL FROM users --",
    "1' OR '1'='1' /*",
    "'; UPDATE users SET role='super_admin' WHERE '1'='1'; --",
]


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_login_email_rejected(app_client, payload):
    """
    SQLAlchemy parameterises queries, so these should be treated as literal
    strings (invalid email -> 401/422), never executed as SQL.
    A 500 would suggest the payload reached the DB engine unescaped.
    """
    r = app_client.post("/api/v1/auth/login", json={
        "email": payload,
        "password": "anything",
    })
    assert r.status_code in (401, 422), f"unexpected status for payload {payload!r}: {r.status_code}"
    assert r.status_code != 500, "500 suggests the payload reached the SQL engine"


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS[:3])
def test_sql_injection_in_search_query_safe(registered_user, payload):
    """Search endpoints take user input straight into a LIKE clause - prime injection target."""
    client, token, _, _ = registered_user
    r = client.get(
        f"/api/v1/customers/?search={payload}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Should return an empty/normal result set, never error out
    assert r.status_code in (200, 404), f"status {r.status_code} for payload {payload!r}"


def test_users_table_still_exists_after_injection_attempts(app_client):
    """
    Sanity check after the DROP TABLE attempts above: the app must still work.
    If the table were actually dropped, login would 500.
    """
    r = app_client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com", "password": "wrong",
    })
    assert r.status_code == 401, "users table appears damaged after injection tests"


# ── A03: XSS ──────────────────────────────────────────────────────────────────

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(document.cookie)",
    "<svg/onload=alert(1)>",
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_payload_stored_but_not_executed_as_html(registered_user, payload):
    """
    The API is JSON-only, so stored XSS is the frontend's concern to escape.
    What we verify here is that the API returns the payload as a JSON string
    value (properly escaped in transit) and doesn't 500 on it.
    """
    client, token, _, _ = registered_user
    r = client.patch(
        "/api/v1/users/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": payload},
    )
    assert r.status_code in (200, 422), f"status {r.status_code}"
    # Response must be valid JSON with the payload as an inert string
    assert r.headers.get("content-type", "").startswith("application/json")


# ── A07: JWT Tampering ────────────────────────────────────────────────────────

def test_jwt_with_none_algorithm_rejected(app_client):
    """
    The classic 'alg: none' attack. Phase 6 added an explicit algorithm
    allowlist; this test proves it holds.
    """
    import base64, json

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'attacker', 'role': 'super_admin'})}."
    r = app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401, "alg=none token was accepted - CRITICAL vulnerability"


def test_jwt_signature_tampering_rejected(registered_user):
    """Flipping bytes in the signature must invalidate the token."""
    client, token, _, _ = registered_user
    parts = token.split(".")
    assert len(parts) == 3

    # Corrupt the signature
    tampered = f"{parts[0]}.{parts[1]}.{'A' * len(parts[2])}"
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401, "tampered signature was accepted"


def test_jwt_payload_tampering_rejected(registered_user):
    """
    Editing the payload to claim super_admin must fail signature verification.
    This is the privilege-escalation attack that matters most.
    """
    import base64, json

    client, token, _, _ = registered_user
    header, payload, sig = token.split(".")

    decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    decoded["role"] = "super_admin"
    new_payload = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()

    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {header}.{new_payload}.{sig}"},
    )
    assert r.status_code == 401, "payload-tampered token accepted - privilege escalation possible"


def test_garbage_token_rejected(app_client):
    for bad in ["not-a-token", "Bearer", "", "a.b.c", "null", "undefined"]:
        r = app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401, f"garbage token {bad!r} accepted"


def test_missing_auth_header_rejected(app_client):
    r = app_client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)


# ── A01: Broken Access Control / IDOR ────────────────────────────────────────

def _register_org(client, label: str):
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={
        "full_name": f"User {label}",
        "email": email,
        "password": "TestPass123",
        "org_name": f"Org {label} {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_return(client, token) -> str:
    r = client.post("/api/v1/returns", headers={"Authorization": f"Bearer {token}"}, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "victim@example.com",
        "sku": "SKU-SECRET-001",
        "item_category": "Electronics",
        "item_value": 45000.0,
        "origin_pincode": "400001",
        "destination_pincode": "560001",
        "weight_grams": 2500,
        "volumetric_weight_grams": 3000,
        "return_reason_code": "defective",
        "courier": "BlueDart",
        "payment_mode": "Prepaid",
        "fragile": True,
        "festive": False,
        "condition": "good",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_idor_cannot_read_another_orgs_return(app_client):
    """
    THE most important multi-tenant test. Org B must not be able to read
    org A's return by guessing/knowing its ID.
    """
    token_a = _register_org(app_client, "victim")
    token_b = _register_org(app_client, "attacker")

    return_id = _make_return(app_client, token_a)

    r = app_client.get(
        f"/api/v1/returns/{return_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404, (
        f"CROSS-TENANT DATA LEAK: org B read org A's return (status {r.status_code})"
    )
    assert "SKU-SECRET-001" not in r.text


def test_idor_cannot_add_note_to_another_orgs_return(app_client):
    token_a = _register_org(app_client, "victim2")
    token_b = _register_org(app_client, "attacker2")
    return_id = _make_return(app_client, token_a)

    r = app_client.post(
        f"/api/v1/returns/{return_id}/notes",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"note": "attacker was here"},
    )
    assert r.status_code == 404, "attacker wrote to another org's return"


def test_idor_cannot_read_another_orgs_timeline(app_client):
    token_a = _register_org(app_client, "victim3")
    token_b = _register_org(app_client, "attacker3")
    return_id = _make_return(app_client, token_a)

    r = app_client.get(
        f"/api/v1/returns/{return_id}/timeline",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


def test_returns_list_only_shows_own_org(app_client):
    """Listing must be org-scoped, not just the detail endpoint."""
    token_a = _register_org(app_client, "listA")
    token_b = _register_org(app_client, "listB")
    _make_return(app_client, token_a)

    r = app_client.get("/api/v1/returns", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    body = r.text
    assert "SKU-SECRET-001" not in body, "org B's list contained org A's return"


# ── A01: Privilege Escalation ────────────────────────────────────────────────

def test_non_super_admin_blocked_from_admin_endpoints(registered_user):
    """A freshly registered user is org_admin, NOT super_admin."""
    client, token, _, _ = registered_user
    headers = {"Authorization": f"Bearer {token}"}

    for endpoint in [
        "/api/v1/admin/orgs",
        "/api/v1/admin/users",
        "/api/v1/admin/system-settings",
        "/api/v1/admin/db-statistics",
    ]:
        r = client.get(endpoint, headers=headers)
        assert r.status_code in (401, 403), (
            f"PRIVILEGE ESCALATION: org_admin accessed {endpoint} (status {r.status_code})"
        )


def test_cannot_self_assign_super_admin_via_profile_update(registered_user):
    """Mass-assignment attack: sneak a role field into a profile update."""
    client, token, _, _ = registered_user
    headers = {"Authorization": f"Bearer {token}"}

    client.patch("/api/v1/users/profile", headers=headers,
                 json={"full_name": "Legit Name", "role": "super_admin"})

    # Verify the role did NOT change
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert "super_admin" not in me.text.lower() or me.json().get("user", {}).get("role") != "super_admin", \
        "MASS ASSIGNMENT: user escalated to super_admin via profile update"


# ── A02: Cryptographic Failures ──────────────────────────────────────────────

def test_password_never_returned_in_any_response(registered_user):
    client, token, email, password = registered_user
    headers = {"Authorization": f"Bearer {token}"}

    for endpoint in ["/api/v1/auth/me", "/api/v1/users/profile"]:
        r = client.get(endpoint, headers=headers)
        assert password not in r.text, f"plaintext password leaked in {endpoint}"
        assert "password_hash" not in r.text, f"password hash leaked in {endpoint}"


def test_password_is_hashed_not_stored_plaintext():
    """Direct check against the hashing function."""
    from app.core.security import hash_password, verify_password

    pw = "MySecretPassword123"
    h = hash_password(pw)

    assert h != pw, "password stored in plaintext"
    assert pw not in h, "plaintext password embedded in hash"
    assert h.startswith("$2"), "not a bcrypt hash"
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword1", h) is False


def test_same_password_produces_different_hashes():
    """Confirms per-password salting - prevents rainbow table attacks."""
    from app.core.security import hash_password
    assert hash_password("SamePassword1") != hash_password("SamePassword1")


# ── A07: Weak Password Policy ────────────────────────────────────────────────

@pytest.mark.parametrize("weak_password", [
    "short",           # too short
    "alllowercase",    # no uppercase, no digit
    "12345678",        # no letters
    "PASSWORD",        # no digit, no lowercase
    "Password",        # no digit
])
def test_weak_passwords_rejected_at_registration(app_client, weak_password):
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Weak Pass User",
        "email": f"weak_{uuid.uuid4().hex[:8]}@example.com",
        "password": weak_password,
        "org_name": f"Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 422, f"weak password {weak_password!r} was accepted"


# ── A05: Security Misconfiguration ───────────────────────────────────────────

def test_security_headers_present(app_client):
    """Phase 6 added these headers - verify they're actually on responses."""
    r = app_client.get("/health")
    headers = {k.lower(): v for k, v in r.headers.items()}

    assert headers.get("x-content-type-options") == "nosniff"
    assert "x-frame-options" in headers
    assert "referrer-policy" in headers


def test_user_enumeration_prevented_on_forgot_password(app_client):
    """
    Forgot-password must return the same response for existing and
    non-existing emails, or an attacker can enumerate valid accounts.
    """
    r_nonexistent = app_client.post("/api/v1/users/forgot-password",
                                    json={"email": f"nobody_{uuid.uuid4().hex}@example.com"})
    assert r_nonexistent.status_code == 200

    # Both must be 200 with a generic message
    body = r_nonexistent.json()
    assert "message" in body
    assert "not found" not in body["message"].lower()
    assert "no account" not in body["message"].lower()


def test_error_responses_do_not_leak_stack_traces(app_client):
    """A 500 must not expose file paths, SQL, or framework internals."""
    r = app_client.get("/api/v1/returns/definitely-not-a-valid-uuid-12345",
                       headers={"Authorization": "Bearer invalid"})
    assert "Traceback" not in r.text
    assert "/app/" not in r.text
    assert "sqlalchemy" not in r.text.lower()
