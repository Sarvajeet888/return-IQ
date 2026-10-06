"""
Integration tests for the Courier Remittance Reconciliation API.
Uses the real app, real (temp SQLite) DB, and real auth flow - not mocks.
"""
from __future__ import annotations

import io


def _score_order(client, token, order_id, value, phone="9876500099"):
    """Helper: score a COD order first, so it becomes the 'expected' amount
    remittance reconciliation will match against."""
    r = client.post(
        "/api/v1/cod-risk/score",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform_order_id": order_id, "customer_phone": phone,
            "customer_name": "Remit Test", "delivery_address": "1 Remit St",
            "delivery_pincode": "500001", "order_value": value,
        },
    )
    assert r.status_code == 200
    return r.json()


def test_ingest_requires_auth(app_client):
    r = app_client.post("/api/v1/remittance/ingest", json={"lines": []})
    assert r.status_code == 401


def test_matched_remittance_after_scoring_order(registered_user):
    client, token, email, password = registered_user
    _score_order(client, token, "ORD-R1", 1200.0)

    r = client.post(
        "/api/v1/remittance/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"lines": [{
            "platform_order_id": "ORD-R1", "courier": "Delhivery",
            "remitted_amount": 1200.0, "remittance_date": "2026-08-01",
        }]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] == 1
    assert body["results"][0]["status"] == "matched"


def test_mismatched_remittance_is_flagged(registered_user):
    client, token, email, password = registered_user
    _score_order(client, token, "ORD-R2", 1000.0)

    r = client.post(
        "/api/v1/remittance/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"lines": [{
            "platform_order_id": "ORD-R2", "courier": "BlueDart",
            "remitted_amount": 700.0, "remittance_date": "2026-08-01",
        }]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mismatched"] == 1
    assert body["results"][0]["discrepancy_amount"]["minor_units"] == -30000
    assert body["results"][0]["discrepancy_amount"]["formatted"] == "-\u20b9300.00"


def test_order_never_scored_is_unmatched(registered_user):
    client, token, email, password = registered_user
    r = client.post(
        "/api/v1/remittance/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"lines": [{
            "platform_order_id": "ORD-NEVER-SCORED", "courier": "Ekart",
            "remitted_amount": 400.0, "remittance_date": "2026-08-01",
        }]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unmatched_no_expected"] == 1
    assert body["results"][0]["expected_amount"] is None


def test_csv_upload_reconciles_correctly(registered_user):
    client, token, email, password = registered_user
    _score_order(client, token, "ORD-CSV1", 900.0)
    _score_order(client, token, "ORD-CSV2", 500.0, phone="9876500100")

    csv_content = (
        "platform_order_id,courier,remitted_amount,remittance_date,awb_number\n"
        "ORD-CSV1,Xpressbees,900.0,2026-08-02,AWB123\n"
        "ORD-CSV2,Xpressbees,350.0,2026-08-02,AWB124\n"
    )
    r = client.post(
        "/api/v1/remittance/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("remittance.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total_lines"] == 2
    assert body["matched"] == 1
    assert body["mismatched"] == 1


def test_csv_upload_rejects_missing_columns(registered_user):
    client, token, email, password = registered_user
    bad_csv = "order_id,amount\nORD-1,500\n"  # wrong column names
    r = client.post(
        "/api/v1/remittance/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bad.csv", io.BytesIO(bad_csv.encode()), "text/csv")},
    )
    assert r.status_code == 400


def test_csv_upload_rejects_wrong_file_type(registered_user):
    client, token, email, password = registered_user
    r = client.post(
        "/api/v1/remittance/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")},
    )
    assert r.status_code == 400


def test_summary_and_mismatch_drilldown(registered_user):
    client, token, email, password = registered_user
    _score_order(client, token, "ORD-SUM1", 1000.0)
    client.post(
        "/api/v1/remittance/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"lines": [{
            "platform_order_id": "ORD-SUM1", "courier": "Shadowfax",
            "remitted_amount": 600.0, "remittance_date": "2026-08-01",
        }]},
    )

    summary = client.get("/api/v1/remittance/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary.status_code == 200
    assert summary.json()["total_discrepancy"]["minor_units"] <= -39500  # -Rs 400 + Rs 5 tolerance

    mismatches = client.get("/api/v1/remittance/mismatches", headers={"Authorization": f"Bearer {token}"})
    assert mismatches.status_code == 200
    assert any(m["platform_order_id"] == "ORD-SUM1" for m in mismatches.json())
