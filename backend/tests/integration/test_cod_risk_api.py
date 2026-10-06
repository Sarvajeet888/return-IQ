"""
Integration tests for the COD Risk API (pre-shipment fraud/RTO scoring).
Uses the real app, real (temp SQLite) DB, and real auth flow - not mocks.
"""
from __future__ import annotations


def test_score_requires_auth(app_client):
    r = app_client.post("/api/v1/cod-risk/score", json={
        "platform_order_id": "ORD-1", "customer_phone": "9876500000",
        "customer_name": "Test", "delivery_address": "1 Test St",
        "delivery_pincode": "500001", "order_value": 1000,
    })
    assert r.status_code == 401


def test_score_first_time_customer_low_value_is_low_risk(registered_user):
    client, token, email, password = registered_user
    r = client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": "ORD-100",
            "customer_phone": "9876500010",
            "customer_name": "Clean Customer",
            "delivery_address": "22 Quiet Lane, Hyderabad",
            "delivery_pincode": "500032",
            "order_value": 800,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["risk_band"] == "low"
    assert body["platform_order_id"] == "ORD-100"
    assert "assessment_id" in body


def test_score_high_risk_pincode_and_high_value_is_flagged(registered_user):
    client, token, email, password = registered_user
    headers = {"Authorization": f"Bearer {token}"}
    risky_pincode = "600042"

    # Build REAL return history at this pincode through the actual returns
    # pipeline, so the pincode-risk signal reflects genuine past fraud
    # scores -- not a hardcoded/fabricated list of "risky" pincodes.
    # Same repeat customer + COD + festive + change_of_mind on a
    # high-value item reliably trips several real fraud-score signals at
    # once (see _compute_fraud_score in ml_service.py).
    for i in range(9):
        r = client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "platform_order_id": f"HIST-{i}",
                "customer_identifier": "repeat_offender@example.com",
                "sku": "SKU-1", "item_category": "Electronics", "item_value": 6000,
                "origin_pincode": "500001", "destination_pincode": risky_pincode,
                "weight_grams": 500, "volumetric_weight_grams": 500,
                "return_reason_code": "change_of_mind", "courier": "Delhivery",
                "payment_mode": "COD", "fragile": False, "festive": True,
            },
        )
        assert r.status_code == 201, r.text

    r = client.post(
        "/api/v1/cod-risk/score",
        headers=headers,
        json={
            "platform_order_id": "ORD-101",
            "customer_phone": "9999911111",
            "customer_name": "Unknown Buyer",
            "delivery_address": "99 New Colony, Delhi",
            "delivery_pincode": risky_pincode,
            "order_value": 4500,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    codes = [f["code"] for f in body["flags"]]
    assert "HIGH_RISK_PINCODE" in codes
    assert "NEW_CUSTOMER_HIGH_VALUE_COD" in codes
    assert body["risk_band"] == "high"


def test_score_rejects_invalid_pincode(registered_user):
    client, token, email, password = registered_user
    r = client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": "ORD-102",
            "customer_phone": "9876500011",
            "customer_name": "Test",
            "delivery_address": "1 Test St",
            "delivery_pincode": "ABCDE1",  # not digits
            "order_value": 500,
        },
    )
    assert r.status_code == 422


def test_shared_address_multiple_names_flagged_across_real_requests(registered_user):
    """Two different 'customers' ordering to the same address should trip
    the fraud-ring signal on the second request - this exercises the real
    DB round-trip (create_cod_risk_assessment -> get_recent_names_at_address),
    not a mock."""
    client, token, email, password = registered_user
    shared_address = "7 Shared Address Test Lane, Mumbai"

    r1 = client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": "ORD-200", "customer_phone": "9111100001",
            "customer_name": "First Name", "delivery_address": shared_address,
            "delivery_pincode": "400001", "order_value": 500,
        },
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": "ORD-201", "customer_phone": "9111100002",
            "customer_name": "Second Name", "delivery_address": shared_address,
            "delivery_pincode": "400001", "order_value": 500,
        },
    )
    assert r2.status_code == 200
    codes = [f["code"] for f in r2.json()["flags"]]
    assert "SHARED_ADDRESS_MULTIPLE_NAMES" in codes


def test_list_assessments_returns_recent_scores(registered_user):
    client, token, email, password = registered_user
    client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": "ORD-300", "customer_phone": "9222200001",
            "customer_name": "List Test", "delivery_address": "5 List Ave",
            "delivery_pincode": "600001", "order_value": 500,
        },
    )
    r = client.get("/api/v1/cod-risk/assessments", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = r.json()
    assert any(i["platform_order_id"] == "ORD-300" for i in items)
