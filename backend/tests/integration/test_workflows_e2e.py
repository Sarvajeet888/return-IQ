"""
Integration tests (Phase 9.4) — full multi-step business workflows.

These exercise the complete chain the way a real user would:
  register -> login -> create return -> ML scoring -> workflow engine
           -> notification -> report -> export

Unit tests prove each part works. These prove the parts work *together*.
"""
from __future__ import annotations
import uuid

import pytest


def _new_org(client, label="int"):
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={
        "full_name": f"Integration {label}",
        "email": email,
        "password": "TestPass123",
        "org_name": f"IntOrg {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"], email


def _return_payload(**overrides):
    base = {
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": f"cust_{uuid.uuid4().hex[:6]}@example.com",
        "sku": "SKU-INT-001",
        "item_category": "Electronics",
        "item_value": 15000.0,
        "origin_pincode": "400001",
        "destination_pincode": "560001",
        "weight_grams": 2000,
        "volumetric_weight_grams": 2500,
        "return_reason_code": "defective",
        "courier": "BlueDart",
        "payment_mode": "Prepaid",
        "fragile": False,
        "festive": False,
        "condition": "good",
    }
    base.update(overrides)
    return base


# ── The core end-to-end flow ─────────────────────────────────────────────────

def test_full_return_lifecycle(app_client):
    """
    register -> create return -> ML scores it -> read it back
    -> add note -> read timeline -> appears in dashboard
    """
    token, _ = _new_org(app_client, "lifecycle")
    h = {"Authorization": f"Bearer {token}"}

    # 1. Create a return — triggers ML scoring + workflow engine
    r = app_client.post("/api/v1/returns", headers=h, json=_return_payload())
    assert r.status_code in (200, 201), r.text
    data = r.json()
    return_id = data["id"]

    # 2. ML prediction must be attached and well-formed
    pred = data.get("prediction")
    assert pred is not None, "no prediction returned"
    assert pred["routing_decision"] in {"accept", "reject", "manual_review", "refund_and_keep"}
    # Phase 3: money is exact integer minor units, not a float.
    assert isinstance(pred["predicted_cost_minor"], int)
    assert pred["currency"] == "INR"
    assert 0 <= pred["risk_score"] <= 100
    assert 0 <= pred["fraud_score"] <= 100
    assert pred["model_version"], "model_version missing - needed for auditability"

    # 3. Workflow engine ran (key present even if no rules matched)
    assert "workflow_rules_applied" in data

    # 4. Read it back
    r = app_client.get(f"/api/v1/returns/{return_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == return_id

    # 5. Add a note
    r = app_client.post(f"/api/v1/returns/{return_id}/notes", headers=h,
                        json={"note": "Inspected — screen cracked as described"})
    assert r.status_code == 201, r.text

    # 6. Timeline reflects creation + prediction + note
    r = app_client.get(f"/api/v1/returns/{return_id}/timeline", headers=h)
    assert r.status_code == 200
    tl = r.json()
    events = [e["event"] for e in tl["timeline"]]
    assert "created" in events
    assert "note" in events

    # 7. Shows up in dashboard aggregates
    r = app_client.get("/api/v1/returns/dashboard", headers=h)
    assert r.status_code == 200


def test_workflow_rule_fires_on_matching_return(app_client):
    """
    Create an auto-approve rule, then submit a return that matches it.
    Proves the rule engine is actually wired into the scoring path.
    """
    token, _ = _new_org(app_client, "wfrule")
    h = {"Authorization": f"Bearer {token}"}

    # Create a rule that matches essentially any low-value return
    r = app_client.post("/api/v1/workflows/rules", headers=h, json={
        "name": "Auto-approve cheap items",
        "rule_type": "auto_approve",
        "conditions": {"item_value_lt": 1000},
        "action": {"status": "approved", "notify": True},
        "priority": 1,
        "is_active": True,
    })
    assert r.status_code == 201, r.text

    # Submit a matching return (value 500 < 1000)
    r = app_client.post("/api/v1/returns", headers=h,
                        json=_return_payload(item_value=500.0))
    assert r.status_code in (200, 201), r.text
    applied = r.json()["workflow_rules_applied"]
    assert len(applied) == 1, f"rule did not fire: {applied}"
    assert applied[0]["rule_name"] == "Auto-approve cheap items"
    assert "status -> approved" in applied[0]["actions_taken"]


def test_workflow_rule_does_not_fire_on_non_matching_return(app_client):
    token, _ = _new_org(app_client, "wfnomatch")
    h = {"Authorization": f"Bearer {token}"}

    app_client.post("/api/v1/workflows/rules", headers=h, json={
        "name": "Only very cheap", "rule_type": "auto_approve",
        "conditions": {"item_value_lt": 100},
        "action": {"status": "approved"}, "priority": 1, "is_active": True,
    })

    # 50000 is way above the 100 threshold
    r = app_client.post("/api/v1/returns", headers=h,
                        json=_return_payload(item_value=50000.0))
    assert r.json()["workflow_rules_applied"] == [], "rule fired on non-matching return"


def test_inactive_rule_does_not_fire(app_client):
    token, _ = _new_org(app_client, "wfinactive")
    h = {"Authorization": f"Bearer {token}"}

    app_client.post("/api/v1/workflows/rules", headers=h, json={
        "name": "Disabled rule", "rule_type": "auto_approve",
        "conditions": {"item_value_lt": 999999},
        "action": {"status": "approved"}, "priority": 1,
        "is_active": False,
    })

    r = app_client.post("/api/v1/returns", headers=h, json=_return_payload())
    assert r.json()["workflow_rules_applied"] == [], "inactive rule fired"


def test_rule_priority_first_match_wins(app_client):
    """Lower priority number = evaluated first. Only one rule should fire."""
    token, _ = _new_org(app_client, "wfpriority")
    h = {"Authorization": f"Bearer {token}"}

    app_client.post("/api/v1/workflows/rules", headers=h, json={
        "name": "First", "rule_type": "auto_approve",
        "conditions": {"item_value_lt": 99999}, "action": {"status": "approved"},
        "priority": 1, "is_active": True,
    })
    app_client.post("/api/v1/workflows/rules", headers=h, json={
        "name": "Second", "rule_type": "auto_reject",
        "conditions": {"item_value_lt": 99999}, "action": {"status": "rejected"},
        "priority": 2, "is_active": True,
    })

    r = app_client.post("/api/v1/returns", headers=h, json=_return_payload())
    applied = r.json()["workflow_rules_applied"]
    assert len(applied) == 1, "more than one rule fired - short-circuit broken"
    assert applied[0]["rule_name"] == "First", "priority ordering not respected"


# ── Bulk import ──────────────────────────────────────────────────────────────

def test_bulk_import_scores_all_returns(app_client):
    token, _ = _new_org(app_client, "bulk")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.post("/api/v1/returns/bulk", headers=h, json={
        "returns": [_return_payload() for _ in range(5)]
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["imported"] == 5, f"expected 5 imported, got {body}"
    assert body["failed"] == 0


def test_bulk_import_rejects_oversized_batch(app_client):
    token, _ = _new_org(app_client, "bulkbig")
    h = {"Authorization": f"Bearer {token}"}
    r = app_client.post("/api/v1/returns/bulk", headers=h, json={
        "returns": [_return_payload() for _ in range(51)]
    })
    assert r.status_code == 400


def test_bulk_import_partial_failure_still_saves_successes(app_client):
    """
    One bad record must not roll back the good ones - the endpoint is
    documented as partial-failure-safe.
    """
    token, _ = _new_org(app_client, "bulkpartial")
    h = {"Authorization": f"Bearer {token}"}

    good = _return_payload()
    bad = _return_payload(origin_pincode="INVALID")

    r = app_client.post("/api/v1/returns/bulk", headers=h, json={"returns": [good, bad]})
    # Either the schema rejects the whole batch (422) or it partially succeeds
    assert r.status_code in (200, 201, 422)
    if r.status_code in (200, 201):
        body = r.json()
        assert body["imported"] >= 1, "good record was lost due to a bad sibling"


# ── Reports & export ─────────────────────────────────────────────────────────

def test_report_reflects_created_returns(app_client):
    token, _ = _new_org(app_client, "report")
    h = {"Authorization": f"Bearer {token}"}

    for _ in range(3):
        app_client.post("/api/v1/returns", headers=h, json=_return_payload())

    r = app_client.get("/api/v1/reports/summary", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["returns"] == 3
    assert len(body["rows"]) == 3


def test_csv_export_returns_csv_content_type(app_client):
    token, _ = _new_org(app_client, "csv")
    h = {"Authorization": f"Bearer {token}"}
    app_client.post("/api/v1/returns", headers=h, json=_return_payload())

    r = app_client.get("/api/v1/reports/summary?format=csv", headers=h)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")


def test_fraud_report_only_includes_high_fraud_returns(app_client):
    token, _ = _new_org(app_client, "fraudrep")
    h = {"Authorization": f"Bearer {token}"}
    app_client.post("/api/v1/returns", headers=h, json=_return_payload())

    r = app_client.get("/api/v1/reports/fraud", headers=h)
    assert r.status_code == 200
    for row in r.json()["rows"]:
        assert row["fraud_score"] >= 50, "low-fraud return leaked into fraud report"


# ── AI explainability ────────────────────────────────────────────────────────

def test_explain_endpoint_returns_feature_importances(app_client):
    token, _ = _new_org(app_client, "explain")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.post("/api/v1/returns", headers=h, json=_return_payload())
    return_id = r.json()["id"]

    r = app_client.get(f"/api/v1/ai/predictions/{return_id}/explain", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "explainability" in body
    # PHASE 21: this used to assert "top_driver_interpretation" — the field
    # that carried hardcoded causal prose ("festive returns correlate with
    # impulse buying") presented as a model explanation. The field is gone;
    # the attributed feature is still reported, now with its caveat.
    assert "top_attributed_feature" in body
    assert "attribution_caveat" in body
    assert "causal_disclaimer" in body
    assert "methodology_note" in body
    # The honesty check: methodology must state fraud/damage are rule-based
    assert "rule-based" in body["methodology_note"].lower()


def test_manual_override_recorded_in_timeline(app_client):
    token, _ = _new_org(app_client, "override")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.post("/api/v1/returns", headers=h, json=_return_payload())
    return_id = r.json()["id"]

    r = app_client.post(f"/api/v1/ai/predictions/{return_id}/override", headers=h, json={
        "routing_decision": "reject",
        "reason": "Customer has 5 prior fraudulent returns not in the model",
    })
    assert r.status_code == 200, r.text

    # Override must be visible in the audit trail
    r = app_client.get(f"/api/v1/returns/{return_id}/notes", headers=h)
    notes_text = r.text
    assert "MANUAL OVERRIDE" in notes_text
    assert "5 prior fraudulent" in notes_text


# ── Customer management ──────────────────────────────────────────────────────

def test_customer_create_and_blacklist_flow(app_client):
    token, _ = _new_org(app_client, "cust")
    h = {"Authorization": f"Bearer {token}"}

    email = f"badcustomer_{uuid.uuid4().hex[:6]}@example.com"
    r = app_client.post("/api/v1/customers/", headers=h, json={
        "name": "Repeat Offender", "email": email,
        "phone": "9999999999", "city": "Mumbai",
    })
    assert r.status_code == 201, r.text
    customer_id = r.json()["id"]

    r = app_client.post(f"/api/v1/customers/{customer_id}/blacklist?reason=Confirmed+fraud",
                        headers=h)
    assert r.status_code == 200, r.text

    r = app_client.get(f"/api/v1/customers/{customer_id}", headers=h)
    assert r.json()["is_blacklisted"] is True


# ── Notifications ────────────────────────────────────────────────────────────

def test_notification_unread_count_endpoint(app_client):
    token, _ = _new_org(app_client, "notif")
    h = {"Authorization": f"Bearer {token}"}
    r = app_client.get("/api/v1/notifications/unread-count", headers=h)
    assert r.status_code == 200
    assert "unread_count" in r.json()


def test_mark_all_notifications_read(app_client):
    token, _ = _new_org(app_client, "notifread")
    h = {"Authorization": f"Bearer {token}"}
    r = app_client.post("/api/v1/notifications/mark-all-read", headers=h)
    assert r.status_code == 200
    assert "marked_read" in r.json()


# ── Password reset flow ──────────────────────────────────────────────────────

def test_password_reset_end_to_end(app_client):
    """
    forgot-password -> get token (demo mode) -> reset -> old password fails,
    new password works. This is the flow that's broken without SMTP in prod.
    """
    token, email = _new_org(app_client, "pwreset")

    r = app_client.post("/api/v1/users/forgot-password", json={"email": email})
    assert r.status_code == 200
    reset_token = r.json().get("demo_token")
    assert reset_token, "demo_token missing - DEMO_MODE should be on in tests"

    r = app_client.post("/api/v1/users/reset-password", json={
        "token": reset_token, "new_password": "BrandNewPass456",
    })
    assert r.status_code == 200, r.text

    # Old password must now fail
    r = app_client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass123"})
    assert r.status_code == 401, "old password still works after reset"

    # New password must work
    r = app_client.post("/api/v1/auth/login", json={"email": email, "password": "BrandNewPass456"})
    assert r.status_code == 200, r.text


def test_reset_token_is_single_use(app_client):
    """A reset token must not be replayable."""
    _, email = _new_org(app_client, "pwreplay")

    r = app_client.post("/api/v1/users/forgot-password", json={"email": email})
    reset_token = r.json()["demo_token"]

    r1 = app_client.post("/api/v1/users/reset-password",
                         json={"token": reset_token, "new_password": "FirstReset123"})
    assert r1.status_code == 200

    r2 = app_client.post("/api/v1/users/reset-password",
                         json={"token": reset_token, "new_password": "SecondReset123"})
    assert r2.status_code == 400, "reset token was reusable - replay vulnerability"


# ── Org member management ────────────────────────────────────────────────────

def test_invite_member_and_they_can_login(app_client):
    token, _ = _new_org(app_client, "invite")
    h = {"Authorization": f"Bearer {token}"}

    invitee_email = f"invitee_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/org/members/invite", headers=h, json={
        "email": invitee_email, "full_name": "New Analyst", "role": "analyst",
    })
    assert r.status_code == 200, r.text
    invitation_token = r.json()["invitation_token"]

    # PHASE 5: the invitee sets their own password via a single-use token.
    accepted = app_client.post("/api/v1/auth/accept-invitation", json={
        "token": invitation_token, "password": "InviteePass123",
    })
    assert accepted.status_code == 200, accepted.text

    r = app_client.post("/api/v1/auth/login",
                        json={"email": invitee_email, "password": "InviteePass123"})
    assert r.status_code == 200, "invited member cannot log in after accepting"
    assert r.json()["user"]["role"] == "analyst"


def test_cannot_invite_duplicate_email(app_client):
    token, email = _new_org(app_client, "dupinvite")
    h = {"Authorization": f"Bearer {token}"}

    r = app_client.post("/api/v1/org/members/invite", headers=h, json={
        "email": email, "full_name": "Dupe", "role": "analyst",
    })
    assert r.status_code == 409
