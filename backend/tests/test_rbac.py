"""RBAC: org-scoped access + role-gated endpoints."""
from __future__ import annotations
import uuid


def test_org_admin_can_update_settings(registered_user):
    client, token, _, _ = registered_user
    r = client.patch(
        "/api/v1/org/settings",
        json={"risk_threshold": 42.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["risk_threshold"] == 42.0


def test_cannot_access_another_orgs_return(app_client):
    # org A creates a return
    email_a = f"a_{uuid.uuid4().hex[:8]}@example.com"
    ra = app_client.post("/api/v1/auth/register", json={
        "full_name": "Org A", "email": email_a, "password": "TestPass123",
        "org_name": "Org A Co", "platform_type": "shopify", "accepted_terms": True,
    })
    token_a = ra.json()["access_token"]

    payload = {
        "platform_order_id": "ORD-RBAC-1", "customer_identifier": "cust_rbac_1",
        "sku": "TSHIRT-L-RED", "item_category": "apparel", "item_value": 999.0,
        "origin_pincode": "400001", "destination_pincode": "411001",
        "weight_grams": 300, "volumetric_weight_grams": 400,
        "return_reason_code": "size_issue", "courier": "Delhivery", "payment_mode": "COD",
        "fragile": False, "festive": False, "condition": "good",
    }
    rc = app_client.post("/api/v1/returns", json=payload, headers={"Authorization": f"Bearer {token_a}"})
    assert rc.status_code == 201
    return_id = rc.json()["id"]

    # org B tries to read org A's return
    email_b = f"b_{uuid.uuid4().hex[:8]}@example.com"
    rb = app_client.post("/api/v1/auth/register", json={
        "full_name": "Org B", "email": email_b, "password": "TestPass123",
        "org_name": "Org B Co", "platform_type": "shopify", "accepted_terms": True,
    })
    token_b = rb.json()["access_token"]

    r = app_client.get(f"/api/v1/returns/{return_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 404, "a user must never be able to read another org's data"


def test_invalid_api_key_rejected(app_client):
    r = app_client.get("/api/v1/ext/returns", headers={"X-API-Key": "rl_live_totally_bogus_key"})
    assert r.status_code == 401
