"""PHASE 31 — customer return portal.

These are the only unauthenticated routes in ReturnIQ that touch customer
data, so most of these tests are about what the portal REFUSES to do.
"""
from __future__ import annotations

import uuid

import pytest

from app.services import portal_service


# ─────────────────── contact matching (the access control) ───────────────────

def test_phone_numbers_match_across_formats():
    """Customers type their number differently from however the merchant's
    platform stored it. Comparing raw strings would reject the legitimate
    customer while doing nothing to stop an attacker, who only needs one
    format to work."""
    stored = "9876543210"
    for typed in ("+91 98765 43210", "09876543210", "9876543210", "+919876543210"):
        assert portal_service.contact_matches(typed, stored), typed


def test_a_different_number_does_not_match():
    assert portal_service.contact_matches("9876543211", "9876543210") is False


def test_email_matching_is_case_insensitive():
    assert portal_service.contact_matches("OM@Example.COM", "om@example.com")


def test_an_empty_contact_never_matches():
    """Otherwise a blank submission would authenticate against an order with
    no stored contact detail."""
    assert portal_service.contact_matches("", "9876543210") is False
    assert portal_service.contact_matches("9876543210", "") is False
    assert portal_service.contact_matches("", "") is False


def test_a_short_number_is_not_padded_into_a_match():
    assert portal_service.contact_matches("3210", "9876543210") is False


# ───────────────────────── enumeration defence ───────────────────────────────

def test_a_missing_order_and_a_wrong_contact_return_identical_responses():
    """THE security property of this phase.

    Distinguishing them turns the endpoint into an order-number oracle: an
    attacker learns which references are real without ever guessing a contact
    detail, then focuses effort on those.
    """
    order = {"platform_order_id": "ORD-1", "customer_identifier": "9876543210"}

    missing = portal_service.build_lookup_response(None, "9876543210")
    wrong_contact = portal_service.build_lookup_response(order, "9999999999")

    assert missing.as_dict() == wrong_contact.as_dict()
    assert missing.found is False
    assert missing.token is None


def test_a_correct_lookup_issues_a_token():
    order = {"platform_order_id": "ORD-1", "customer_identifier": "9876543210"}
    result = portal_service.build_lookup_response(order, "+91 98765 43210")

    assert result.found is True
    assert result.token
    assert len(result.token) >= 40
    assert result.expires_at


def test_tokens_are_unpredictable_and_unique():
    """Not derived from the order ID. A derived token is guessable by anyone
    who knows the derivation, and the derivation always leaks eventually."""
    tokens = {portal_service.issue_portal_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 40 for t in tokens)


def test_only_the_token_hash_would_be_stored():
    raw = portal_service.issue_portal_token()
    hashed = portal_service.hash_portal_token(raw)
    assert hashed != raw
    assert len(hashed) == 64


# ──────────────────────────── data minimisation ──────────────────────────────

def test_the_lookup_response_excludes_personal_data():
    """The customer already knows their own name and address — showing it back
    adds nothing they need and everything an attacker wants."""
    order = {
        "platform_order_id": "ORD-1",
        "customer_identifier": "9876543210",
        "sku": "TSHIRT-L-RED",
        "item_category": "apparel",
        "created_at": "2026-07-01T10:00:00",
        "item_value": {"formatted": "₹1,499.00"},
        # None of the following may appear in the response.
        "destination_pincode": "411001",
        "org_id": "org-secret",
        "id": "internal-uuid",
    }
    minimised = portal_service.minimise_order(order)

    assert minimised["item"] == "TSHIRT-L-RED"
    assert "customer_identifier" not in minimised
    assert "destination_pincode" not in minimised
    assert "org_id" not in minimised
    assert "id" not in minimised


def test_the_response_never_carries_risk_or_cost_signals():
    """A customer who can see their own fraud score learns precisely which
    behaviour to avoid next time, which degrades the signal for every merchant
    on the platform."""
    order = {
        "platform_order_id": "ORD-1", "customer_identifier": "9876543210",
        "sku": "S1", "fraud_score": 82, "risk_score": 70,
        "predicted_cost_minor": 45000,
    }
    minimised = portal_service.minimise_order(order)

    for leaked in ("fraud_score", "risk_score", "predicted_cost_minor"):
        assert leaked not in minimised


def test_contact_details_are_masked_for_confirmation():
    assert portal_service.mask_contact("9876543210").endswith("3210")
    assert "9876" not in portal_service.mask_contact("9876543210")

    masked_email = portal_service.mask_contact("omp@example.com")
    assert masked_email.startswith("o")
    assert masked_email.endswith("@example.com")
    assert "omp@" not in masked_email


# ───────────────────────────── end-to-end flow ───────────────────────────────

@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Portal endpoints are rate limited hard, and every test here shares one
    client IP. Without resetting between tests they exhaust the budget and
    fail with 429 — a real control firing on a test artefact.

    The limit itself is asserted deliberately in
    `test_the_lookup_endpoint_is_rate_limited`, rather than being silently
    disabled everywhere.
    """
    from app.core.rate_limit import limiter
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 -- in-memory backends may not implement it
        storage = getattr(limiter, "_storage", None) or getattr(
            getattr(limiter, "limiter", None), "storage", None
        )
        if storage is not None and hasattr(storage, "storage"):
            storage.storage.clear()
    yield


def test_the_lookup_endpoint_is_rate_limited(app_client):
    """Enumeration defence.

    Order references are merchant-chosen and frequently sequential, so an
    unthrottled lookup walks a merchant's entire order book. Ten a minute is
    generous for a human typing their own order number and useless for a
    script.
    """
    org_header = {"X-ReturnIQ-Org": str(uuid.uuid4())}
    statuses = [
        app_client.post(
            "/api/v1/portal/lookup", headers=org_header,
            json={"order_reference": f"ORD-{i}", "contact": "9876543210"},
        ).status_code
        for i in range(25)
    ]
    assert 429 in statuses, "the lookup endpoint is not rate limited"


@pytest.fixture
def merchant_order(app_client):
    """A merchant with one order, ready for a customer to return."""
    email = f"portal_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Portal Merchant", "email": email, "password": "PortalPass123",
        "org_name": f"Portal Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    org_id = r.json()["user"]["org_id"]
    headers = {"Authorization": f"Bearer {token}"}

    order_ref = f"ORD-{uuid.uuid4().hex[:8]}"
    rr = app_client.post("/api/v1/returns", headers=headers, json={
        "platform_order_id": order_ref,
        "customer_identifier": "9876543210",
        "sku": "TSHIRT-L-RED", "item_category": "apparel",
        "item_value": "1499.00", "origin_pincode": "400001",
        "destination_pincode": "411001", "weight_grams": 300,
        "volumetric_weight_grams": 350, "return_reason_code": "size_issue",
        "courier": "Delhivery", "payment_mode": "COD",
        "fragile": False, "festive": False, "condition": "good",
    })
    assert rr.status_code in (200, 201), rr.text
    return app_client, org_id, order_ref


def test_a_customer_can_look_up_their_own_order(merchant_order):
    client, org_id, order_ref = merchant_order
    r = client.post("/api/v1/portal/lookup",
                    headers={"X-ReturnIQ-Org": org_id},
                    json={"order_reference": order_ref, "contact": "+91 98765 43210"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] is True
    assert body["access_token"]
    assert body["order"]["item"] == "TSHIRT-L-RED"


def test_a_wrong_contact_detail_reveals_nothing(merchant_order):
    client, org_id, order_ref = merchant_order
    r = client.post("/api/v1/portal/lookup",
                    headers={"X-ReturnIQ-Org": org_id},
                    json={"order_reference": order_ref, "contact": "9999999999"})
    body = r.json()
    assert body["found"] is False
    assert body["access_token"] is None
    assert body["order"] is None


def test_a_lookup_without_a_merchant_is_refused(merchant_order):
    """org_id comes from the merchant's embed configuration, never from the
    customer. A customer-controlled org would let anyone query any merchant's
    orders by changing a header."""
    client, _org_id, order_ref = merchant_order
    r = client.post("/api/v1/portal/lookup",
                    json={"order_reference": order_ref, "contact": "9876543210"})
    assert r.status_code == 400


def test_an_order_from_another_merchant_is_not_found(merchant_order):
    """Order references are unique per merchant, not globally. ORD-1001 may
    exist at fifty merchants."""
    client, _org_id, order_ref = merchant_order
    r = client.post("/api/v1/portal/lookup",
                    headers={"X-ReturnIQ-Org": str(uuid.uuid4())},
                    json={"order_reference": order_ref, "contact": "9876543210"})
    assert r.json()["found"] is False


def test_the_full_return_journey(merchant_order):
    """Lookup -> create -> track. This is the flywheel: every step produces a
    labelled row the synthetic dataset does not have."""
    client, org_id, order_ref = merchant_order
    org_header = {"X-ReturnIQ-Org": org_id}

    lookup = client.post("/api/v1/portal/lookup", headers=org_header,
                         json={"order_reference": order_ref, "contact": "9876543210"})
    token = lookup.json()["access_token"]

    created = client.post(
        "/api/v1/portal/returns",
        headers={**org_header, "X-Portal-Token": token},
        json={"reason_code": "damaged",
              "comment": "The sleeve was torn when the parcel arrived."},
    )
    assert created.status_code == 201, created.text
    return_id = created.json()["return_id"]

    tracked = client.get(
        f"/api/v1/portal/returns/{return_id}/status",
        headers={**org_header, "X-Portal-Token": token},
    )
    assert tracked.status_code == 200
    assert "reviewing" in tracked.json()["status"].lower()


def test_creating_a_return_requires_a_session_token(merchant_order):
    client, org_id, _order_ref = merchant_order
    r = client.post("/api/v1/portal/returns",
                    headers={"X-ReturnIQ-Org": org_id},
                    json={"reason_code": "damaged"})
    assert r.status_code == 401


def test_an_invalid_token_is_refused(merchant_order):
    client, org_id, _order_ref = merchant_order
    r = client.post("/api/v1/portal/returns",
                    headers={"X-ReturnIQ-Org": org_id, "X-Portal-Token": "x" * 43},
                    json={"reason_code": "damaged"})
    assert r.status_code == 401


def test_a_session_cannot_start_two_returns(merchant_order):
    """One lookup, one return. Otherwise a single session could be replayed to
    file repeated claims against the same order."""
    client, org_id, order_ref = merchant_order
    org_header = {"X-ReturnIQ-Org": org_id}

    token = client.post("/api/v1/portal/lookup", headers=org_header,
                        json={"order_reference": order_ref,
                              "contact": "9876543210"}).json()["access_token"]
    auth = {**org_header, "X-Portal-Token": token}

    first = client.post("/api/v1/portal/returns", headers=auth,
                        json={"reason_code": "damaged"})
    assert first.status_code == 201

    second = client.post("/api/v1/portal/returns", headers=auth,
                         json={"reason_code": "size_issue"})
    assert second.status_code == 409


def test_tracking_another_returns_id_is_refused(merchant_order):
    """The session is bound to one return. Without this check, any valid
    session could read any return in the merchant's account by id."""
    client, org_id, order_ref = merchant_order
    org_header = {"X-ReturnIQ-Org": org_id}

    token = client.post("/api/v1/portal/lookup", headers=org_header,
                        json={"order_reference": order_ref,
                              "contact": "9876543210"}).json()["access_token"]
    auth = {**org_header, "X-Portal-Token": token}
    client.post("/api/v1/portal/returns", headers=auth, json={"reason_code": "damaged"})

    r = client.get(f"/api/v1/portal/returns/{uuid.uuid4()}/status", headers=auth)
    assert r.status_code == 401


def test_tracking_exposes_no_internal_signals(merchant_order):
    """A customer needs to know where their return is — not the fraud score,
    the predicted cost, or the disposition recommendation."""
    client, org_id, order_ref = merchant_order
    org_header = {"X-ReturnIQ-Org": org_id}

    token = client.post("/api/v1/portal/lookup", headers=org_header,
                        json={"order_reference": order_ref,
                              "contact": "9876543210"}).json()["access_token"]
    auth = {**org_header, "X-Portal-Token": token}
    return_id = client.post("/api/v1/portal/returns", headers=auth,
                            json={"reason_code": "damaged"}).json()["return_id"]

    body = client.get(f"/api/v1/portal/returns/{return_id}/status", headers=auth).json()
    text = str(body).lower()
    for leaked in ("fraud", "risk_score", "predicted", "org_id", "9876543210"):
        assert leaked not in text, leaked
