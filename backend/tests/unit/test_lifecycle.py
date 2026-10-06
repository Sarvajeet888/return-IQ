"""PHASE 12 — return lifecycle.

Because the transition map is data rather than branching code, these tests can
check *every* pair of states exhaustively, not only the paths someone thought
to write down.
"""
from __future__ import annotations

import itertools
import uuid

import pytest

from app.core.lifecycle import (
    ALL_STATUSES,
    TERMINAL_STATUSES,
    TRANSITIONS,
    InvalidTransition,
    ReturnStatus as S,
    can_transition,
    is_terminal,
    next_statuses,
    validate_transition,
)


# ───────────────────────── the map is internally sound ───────────────────────

def test_every_target_is_a_known_status():
    """A transition to a status that does not exist is a dead end that only
    shows up when a user reaches it."""
    for source, targets in TRANSITIONS.items():
        for target in targets:
            assert target in ALL_STATUSES, f"{source} -> {target} is not a real status"


def test_every_status_has_an_entry():
    for status in ALL_STATUSES:
        assert status in TRANSITIONS, f"{status} has no transition rules"


def test_terminal_statuses_have_no_exits():
    for status in TERMINAL_STATUSES:
        assert TRANSITIONS[status] == frozenset()
        assert is_terminal(status)


def test_no_status_transitions_to_itself():
    for source, targets in TRANSITIONS.items():
        assert source not in targets, f"{source} -> {source} should not be a transition"


def test_every_non_terminal_status_can_reach_a_terminal_one():
    """A return that can never be closed is an operational dead end: it sits
    in someone's queue forever with no action that resolves it."""
    for start in ALL_STATUSES - TERMINAL_STATUSES:
        seen, frontier = set(), [start]
        while frontier:
            node = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            frontier.extend(TRANSITIONS[node])
        assert seen & TERMINAL_STATUSES, f"{start} can never reach a terminal state"


# ──────────────────────────── the money scenario ─────────────────────────────

def test_refunded_cannot_go_back_to_pending():
    """THE test for this phase.

    Verified against the running API before the fix: PATCH status to
    "refunded", then to "pending", both returned 200. Money has left the
    merchant's account, and the return is back in the queue to be approved and
    refunded a second time.
    """
    assert not can_transition(S.REFUNDED, S.PENDING)
    with pytest.raises(InvalidTransition):
        validate_transition(S.REFUNDED, S.PENDING)


def test_refunded_cannot_be_re_approved():
    assert not can_transition(S.REFUNDED, S.APPROVED)


def test_closed_cannot_be_reopened_as_an_ordinary_status_change():
    """The example from the roadmap: CLOSED -> PICKUP_SCHEDULED."""
    with pytest.raises(InvalidTransition, match="final"):
        validate_transition(S.CLOSED, S.PICKUP_SCHEDULED)


def test_a_return_cannot_skip_physical_reality():
    """Nothing can be inspected before it has been received."""
    assert not can_transition(S.APPROVED, S.INSPECTION)
    assert not can_transition(S.PICKUP_SCHEDULED, S.RECEIVED)
    assert not can_transition(S.IN_TRANSIT, S.INSPECTION)


def test_the_happy_path_works_end_to_end():
    path = [
        S.PENDING, S.PREDICTION_DONE, S.UNDER_REVIEW, S.APPROVED,
        S.PICKUP_SCHEDULED, S.IN_TRANSIT, S.RECEIVED, S.INSPECTION,
        S.REFUNDED, S.CLOSED,
    ]
    for current, target in zip(path, path[1:]):
        validate_transition(current, target)      # must not raise


def test_legitimate_exceptions_are_permitted():
    # Refund-and-keep: reverse shipping costs more than the item is worth.
    assert can_transition(S.APPROVED, S.REFUNDED)
    # Courier loses the parcel: resolves as a refund, not an inspection that
    # will never happen.
    assert can_transition(S.IN_TRANSIT, S.REFUNDED)
    # A customer disputes a rejection; support reopens the review.
    assert can_transition(S.REJECTED, S.UNDER_REVIEW)


# ──────────────────────────── exhaustive coverage ────────────────────────────

def test_all_status_pairs_are_decided():
    """Every ordered pair either transitions or does not — no crashes, no
    ambiguity. This is the payoff of expressing the lifecycle as data."""
    for a, b in itertools.product(ALL_STATUSES, repeat=2):
        assert isinstance(can_transition(a, b), bool)


def test_terminal_states_reject_every_target():
    for terminal, target in itertools.product(TERMINAL_STATUSES, ALL_STATUSES):
        assert not can_transition(terminal, target)


# ──────────────────────── unknown and legacy input ───────────────────────────

def test_unknown_target_is_rejected_by_name():
    with pytest.raises(InvalidTransition, match="not a return status"):
        validate_transition(S.PENDING, "banana")


def test_legacy_garbage_status_fails_closed_without_crashing():
    """Rows written before this phase may hold arbitrary strings — "banana"
    was demonstrably storable. Listing them must not crash a page."""
    assert can_transition("banana", S.CLOSED) is False
    assert next_statuses("banana") == []
    with pytest.raises(InvalidTransition, match="unrecognised status"):
        validate_transition("banana", S.CLOSED)


def test_same_status_is_refused_with_a_clear_message():
    with pytest.raises(InvalidTransition, match="already"):
        validate_transition(S.APPROVED, S.APPROVED)


def test_error_messages_name_what_is_allowed():
    """A bare 'invalid transition' forces the reader to go find the source,
    and the reader is often an integration partner who cannot."""
    with pytest.raises(InvalidTransition) as exc:
        validate_transition(S.RECEIVED, S.PENDING)
    assert "inspection" in str(exc.value)


# ──────────────────────────────── HTTP layer ─────────────────────────────────

@pytest.fixture
def authed_return(app_client):
    email = f"lc_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Lifecycle Tester", "email": email, "password": "LifePass123",
        "org_name": f"LC Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    rr = app_client.post("/api/v1/returns", headers=headers, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "c1", "sku": "S1", "item_category": "apparel",
        "item_value": "1000.00", "origin_pincode": "400001",
        "destination_pincode": "411001", "weight_grams": 500,
        "volumetric_weight_grams": 600, "return_reason_code": "damaged",
        "courier": "Delhivery", "payment_mode": "COD",
        "fragile": False, "festive": False, "condition": "good",
    })
    assert rr.status_code in (200, 201), rr.text
    return app_client, headers, rr.json()["id"]


def test_api_rejects_a_nonsense_status(authed_return):
    client, headers, return_id = authed_return
    r = client.patch(f"/api/v1/returns/{return_id}/status",
                     headers=headers, json={"status": "banana"})
    assert r.status_code == 422        # schema rejects it before the route


def test_api_rejects_an_illegal_transition(authed_return):
    """End-to-end proof of the money scenario."""
    client, headers, return_id = authed_return

    ok = client.patch(f"/api/v1/returns/{return_id}/status",
                      headers=headers, json={"status": "approved"})
    assert ok.status_code == 200

    ok = client.patch(f"/api/v1/returns/{return_id}/status",
                      headers=headers, json={"status": "refunded"})
    assert ok.status_code == 200

    # The transition that used to return 200 and silently reopen a paid refund.
    bad = client.patch(f"/api/v1/returns/{return_id}/status",
                       headers=headers, json={"status": "pending"})
    assert bad.status_code == 409
    assert "refunded" in bad.json()["detail"]


def test_api_exposes_allowed_transitions(authed_return):
    client, headers, return_id = authed_return
    r = client.get(f"/api/v1/returns/{return_id}/transitions", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["is_terminal"] is False
    assert "approved" in body["allowed_transitions"]
    assert "closed" not in body["allowed_transitions"]
