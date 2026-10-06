"""PHASE 8 — Audit chain integrity.

The property under test is that modifying history is *detectable*. Not
prevented -- someone with write access can rewrite the whole chain -- but not
quietly changeable, which is the realistic insider threat to an audit trail.
"""
from __future__ import annotations

import uuid

import pytest

from app.db import store
from app.services import audit_service
from app.services.audit_service import Category


@pytest.fixture
def org(app_client):
    created = store.create_org({
        "id": str(uuid.uuid4()),
        "name": "Audit Test Org",
        "slug": f"audit-{uuid.uuid4().hex[:8]}",
        "contact_email": f"{uuid.uuid4().hex[:8]}@example.com",
        "platform_type": "shopify",
        "plan_tier": "starter",
        "is_active": True,
        "risk_threshold": 50.0,
        "rate_limit_per_minute": 60,
        "total_returns": 0,
        "total_revenue_saved_minor": 0,
        "currency": "INR",
        "settings": {},
    })
    return created["id"]


def _write_events(org_id: str, n: int = 5) -> None:
    for i in range(n):
        audit_service.record(
            org_id=org_id,
            action="return_approved",
            user_id="user-1",
            category=Category.BUSINESS,
            resource_type="return",
            resource_id=f"RI-{i:04d}",
            detail=f"Approved return {i}",
        )


# ───────────────────────────── chain behaviour ───────────────────────────────

def test_chain_is_valid_when_untouched(org):
    _write_events(org, 5)
    result = audit_service.verify_chain(org)
    assert result["valid"] is True
    assert result["events_checked"] == 5


def test_first_event_has_no_predecessor(org):
    _write_events(org, 1)
    events = store.get_audit_chain(org)
    assert events[0]["prev_hash"] is None
    assert events[0]["event_hash"] is not None


def test_each_event_links_to_the_previous(org):
    _write_events(org, 4)
    events = store.get_audit_chain(org)
    for earlier, later in zip(events, events[1:]):
        assert later["prev_hash"] == earlier["event_hash"]


def test_chains_are_per_org(org, app_client):
    """One org's events must not appear in another's chain.

    Beyond the isolation concern, a shared chain would mean any org's write
    ordering could break another org's verification.
    """
    other = store.create_org({
        "id": str(uuid.uuid4()), "name": "Other Org",
        "slug": f"other-{uuid.uuid4().hex[:8]}",
        "contact_email": f"{uuid.uuid4().hex[:8]}@example.com",
        "platform_type": "shopify", "plan_tier": "starter", "is_active": True,
        "risk_threshold": 50.0, "rate_limit_per_minute": 60,
        "total_returns": 0, "total_revenue_saved_minor": 0,
        "currency": "INR", "settings": {},
    })["id"]

    _write_events(org, 3)
    _write_events(other, 2)

    assert audit_service.verify_chain(org)["events_checked"] == 3
    assert audit_service.verify_chain(other)["events_checked"] == 2
    assert audit_service.verify_chain(org)["valid"] is True
    assert audit_service.verify_chain(other)["valid"] is True


# ──────────────────────────── tamper detection ───────────────────────────────

def test_editing_an_event_is_detected(org):
    """THE test for this phase.

    Someone with database access rewrites history: a rejected return becomes
    an approved one. The row itself now looks perfectly plausible.
    """
    _write_events(org, 5)
    events = store.get_audit_chain(org)
    target = events[2]

    from app.db.models import AuditLog
    from app.db.store import SessionLocal
    with SessionLocal() as db:
        row = db.get(AuditLog, target["id"])
        row.detail = "Approved return 2 (definitely legitimate)"
        row.action = "return_approved"
        db.commit()

    result = audit_service.verify_chain(org)
    assert result["valid"] is False
    assert result["broken_at"]["id"] == target["id"]
    assert result["broken_at"]["position"] == 2
    # Everything before the break is still trustworthy, and the result says so.
    assert result["events_checked"] == 3


def test_deleting_an_event_is_detected(org):
    """Removing a row breaks the link in the row that followed it."""
    _write_events(org, 5)
    events = store.get_audit_chain(org)

    from app.db.models import AuditLog
    from app.db.store import SessionLocal
    with SessionLocal() as db:
        db.delete(db.get(AuditLog, events[1]["id"]))
        db.commit()

    assert audit_service.verify_chain(org)["valid"] is False


def test_recomputing_one_hash_still_breaks_the_next_link(org):
    """The reason chaining beats per-row hashing.

    A tamperer who understands the scheme edits the row *and* recomputes its
    hash. The row is now self-consistent -- but the next row committed to the
    old hash, so the break simply moves one position later.
    """
    _write_events(org, 4)
    events = store.get_audit_chain(org)
    target = events[1]

    from app.db.models import AuditLog
    from app.db.store import SessionLocal
    with SessionLocal() as db:
        row = db.get(AuditLog, target["id"])
        row.detail = "Rewritten"
        row.event_hash = audit_service.compute_hash(row.prev_hash, {
            "id": row.id, "org_id": row.org_id, "user_id": row.user_id,
            "action": row.action, "category": row.category,
            "resource_type": row.resource_type, "resource_id": row.resource_id,
            "detail": row.detail, "changes": row.changes,
            "created_at": row.created_at,
        })
        db.commit()

    result = audit_service.verify_chain(org)
    assert result["valid"] is False
    assert result["broken_at"]["position"] == 2      # the *next* row


# ───────────────────────────── event richness ────────────────────────────────

def test_event_captures_resource_identity(org):
    audit_service.record(
        org_id=org, action="return_rejected", user_id="u1",
        resource_type="return", resource_id="RI-92831",
        detail="Rejected: evidence insufficient",
    )
    event = store.get_audit_chain(org)[-1]
    assert event["resource_type"] == "return"
    assert event["resource_id"] == "RI-92831"


def test_changes_are_recorded_as_structured_data(org):
    """Before/after as JSON, not prose, so 'what was it before' is queryable."""
    audit_service.record(
        org_id=org, action="risk_override", user_id="u1",
        category=Category.ML, resource_type="prediction", resource_id="P-1",
        changes={"fraud_score": {"from": 91.0, "to": 12.0}},
    )
    event = store.get_audit_chain(org)[-1]
    assert event["changes"]["fraud_score"]["from"] == 91.0
    assert event["changes"]["fraud_score"]["to"] == 12.0


def test_categories_separate_concerns(org):
    audit_service.record(org_id=org, action="login_failed", category=Category.SECURITY)
    audit_service.record(org_id=org, action="model_deployed", category=Category.ML)
    audit_service.record(org_id=org, action="data_exported", category=Category.DATA)

    events = store.get_audit_chain(org)
    assert {e["category"] for e in events} >= {"security", "ml", "data"}


def test_unknown_category_is_refused(org):
    with pytest.raises(ValueError, match="Unknown audit category"):
        audit_service.record(org_id=org, action="x", category="whatever")


def test_legacy_writer_also_gets_chained(org):
    """The 34 existing add_audit_log() call sites must gain tamper evidence
    without being individually rewritten."""
    store.add_audit_log({"org_id": org, "user_id": "u1", "action": "legacy_action"})
    events = store.get_audit_chain(org)
    assert events[-1]["event_hash"] is not None
    assert audit_service.verify_chain(org)["valid"] is True
