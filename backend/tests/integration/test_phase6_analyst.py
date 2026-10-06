"""PHASE 6 — end-to-end proof of the authorization fix.

Before this phase, /cod-risk/score was gated on
`require_role("org_admin", "warehouse_manager", "finance")`. Neither
warehouse_manager nor finance is assignable by the invite schema, so the
endpoint was org_admin-only in practice while appearing delegable -- an
analyst got a flat 403 with no indication the role list was broken.

This walks the whole journey (register admin -> invite analyst -> accept
invitation -> log in -> score) rather than asserting on the permission
matrix, because the matrix being right is not the same as the wiring being
right.
"""
import uuid

def test_analyst_can_score_cod_after_phase6(app_client):
    email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Admin", "email": email, "password": "AdminPass123",
        "org_name": f"Org {uuid.uuid4().hex[:6]}", "platform_type": "shopify",
        "accepted_terms": True})
    admin = r.json()["access_token"]

    member = f"analyst_{uuid.uuid4().hex[:8]}@example.com"
    inv = app_client.post("/api/v1/org/members/invite",
        headers={"Authorization": f"Bearer {admin}"},
        json={"email": member, "full_name": "An Analyst", "role": "analyst"})
    tok = inv.json()["invitation_token"]
    app_client.post("/api/v1/auth/accept-invitation",
                    json={"token": tok, "password": "AnalystPass123"})
    login = app_client.post("/api/v1/auth/login",
                            json={"email": member, "password": "AnalystPass123"})
    at = login.json()["access_token"]

    score = app_client.post("/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {at}"},
        json={"platform_order_id": "ORD-X1", "customer_phone": "9876500001",
              "customer_name": "Cust", "delivery_address": "1 St",
              "delivery_pincode": "500001", "order_value": 800})
    assert score.status_code == 200, score.text
    assert score.json()["risk_band"] in {"low", "medium", "high"}
