"""Returns scoring endpoint: happy path, pagination, and API-key auth."""
from __future__ import annotations


VALID_PAYLOAD = {
    "platform_order_id": "ORD-SCORE-1", "customer_identifier": "cust_score_1",
    "sku": "TSHIRT-L-RED", "item_category": "apparel", "item_value": 1499.0,
    "origin_pincode": "400001", "destination_pincode": "411001",
    "weight_grams": 300, "volumetric_weight_grams": 400,
    "return_reason_code": "size_issue", "courier": "Delhivery", "payment_mode": "COD",
    "fragile": False, "festive": False, "condition": "good",
}


def test_create_return_scores_and_persists(registered_user):
    client, token, _, _ = registered_user
    r = client.post("/api/v1/returns", json=VALID_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "prediction_done"
    pred = body["prediction"]
    for field in ("predicted_cost_minor", "currency", "risk_score", "fraud_score", "routing_decision"):
        assert field in pred

    # persisted - fetch it back
    r2 = client.get(f"/api/v1/returns/{body['id']}", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["prediction"] is not None


def test_list_returns_pagination(registered_user):
    client, token, _, _ = registered_user
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(3):
        payload = {**VALID_PAYLOAD, "platform_order_id": f"ORD-PAGE-{i}", "customer_identifier": f"cust_page_{i}"}
        client.post("/api/v1/returns", json=payload, headers=headers)

    r = client.get("/api/v1/returns?page=1&page_size=2", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert body["total"] >= 3


def test_invalid_pincode_rejected(registered_user):
    client, token, _, _ = registered_user
    bad = {**VALID_PAYLOAD, "origin_pincode": "abc123"}
    r = client.post("/api/v1/returns", json=bad, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
