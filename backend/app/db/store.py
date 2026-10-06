"""
Persistent data-access layer, backed by SQLAlchemy + a real database
(Postgres in production, SQLite for local/dev/tests).

The function signatures here are intentionally identical to the old
in-memory version so that routes/ and services/ needed almost no changes -
this module is the only thing that changed underneath them. Every return
value is a plain dict (via `_to_dict`) to keep that compatibility total.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update

from app.core.config import get_settings

logger = logging.getLogger(__name__)
from app.core.money import Money
from app.core.security import generate_api_key, hash_api_key, hash_password
from app.core.cache import cache_invalidate_org
from app.db import models
from app.db.database import SessionLocal, init_db

settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(UTC)


def _to_dict(obj: Any) -> dict | None:
    if obj is None:
        return None
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, Decimal):
            val = float(val)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Demo seed data — only runs once, when DEMO_MODE is on and the DB is empty
# ─────────────────────────────────────────────────────────────────────────────
def seed_if_needed() -> tuple[str, str, str] | None:
    """
    Seed demo data, safely, even when several workers start at once.

    The original implementation did a check-then-act: SELECT for an existing
    org, and INSERT if none was found. Under uvicorn with multiple workers,
    every worker runs this at startup simultaneously, all of them see an empty
    database, and all of them try to insert the same admin user. One wins; the
    rest die on a UNIQUE violation and take the whole worker down with them
    ("Application startup failed. Exiting.").

    There is no way to win that race with a SELECT, so instead we let the
    database's unique constraint arbitrate and treat the resulting
    IntegrityError as "another worker already seeded it" - which is exactly
    what it means.
    """
    from sqlalchemy.exc import IntegrityError

    try:
        return _seed_if_needed_impl()
    except IntegrityError:
        logger.info("Demo seed already performed by another worker - skipping.")
        return None


def _seed_if_needed_impl() -> tuple[str, str, str] | None:
    init_db()
    if not settings.DEMO_MODE:
        return None

    with SessionLocal() as db:
        existing = db.execute(select(models.Org).limit(1)).scalar_one_or_none()
        if existing:
            return None

        org = models.Org(
            name="Demo Store (Sapna Collection)",
            slug="sapna-collection",
            contact_email="admin@sapnacollection.com",
            platform_type="shopify",
            plan_tier="enterprise",
            is_active=True,
            risk_threshold=50.0,
            rate_limit_per_minute=300,
            total_returns=0,
            total_revenue_saved_minor=0,
            currency="INR",
            settings={
                "currency": "INR", "timezone": "Asia/Kolkata",
                "auto_approve_below_risk": 20, "notify_on_fraud": True, "webhook_url": "",
            },
        )
        db.add(org)
        db.flush()

        db.add(models.Warehouse(
            org_id=org.id, name="Mumbai Central Warehouse", city="Mumbai",
            pincode="400001", state="Maharashtra", capacity_units=10000, used_units=3421,
            zones=["receiving", "inspection", "storage", "dispatch"], is_active=True,
        ))

        admin = models.User(
            org_id=org.id, email="admin@sapnacollection.com", full_name="Om Admin",
            password_hash=hash_password("Demo@12345"), role="org_admin", status="active",
            is_verified=True, mfa_enabled=False,
        )
        db.add(admin)
        db.flush()

        customer_names = [
            ("Priya Sharma", "Mumbai"), ("Rahul Verma", "Delhi"),
            ("Sneha Patel", "Ahmedabad"), ("Amit Singh", "Bangalore"),
            ("Kavya Rao", "Hyderabad"), ("Rohit Kumar", "Chennai"),
            ("Anjali Gupta", "Pune"), ("Vikram Mehta", "Kolkata"),
        ]
        customer_ids = []
        for name, city in customer_names:
            c = models.Customer(
                org_id=org.id, name=name, city=city,
                email=f"{name.lower().replace(' ', '.')}@example.com",
                phone=f"+91{random.randint(7000000000, 9999999999)}",
                total_orders=random.randint(5, 80), total_returns=random.randint(0, 12),
                fraud_score=round(random.uniform(0, 40), 1), clv_minor=Money.from_major(f"{random.uniform(2000, 85000):.2f}", "INR").minor_units, currency="INR",
                risk_level=random.choice(["low", "low", "medium", "high"]),
                joined_at=_now() - timedelta(days=random.randint(30, 730)),
            )
            db.add(c)
            db.flush()
            customer_ids.append(c.id)

        categories = ["apparel", "electronics", "footwear", "accessories", "furniture", "books"]
        couriers = ["BlueDart", "Delhivery", "DTDC", "Ekart", "XpressBees", "Shadowfax"]
        reasons = ["size_issue", "damaged", "not_as_described", "wrong_item", "quality_issue", "change_of_mind"]
        decisions = ["accept", "accept", "accept", "charge_return_fee", "refund_and_keep", "reject"]
        skus = ["TSHIRT-L-RED", "JEANS-32-BLU", "SAREE-SILK-GRN", "PHONE-CASE-BLK",
                "SHOES-NK-42", "KURTA-M-WHT", "LAPTOP-BAG-BLK", "WATCH-CASIO-BLK"]
        origin_pincodes = ["400001", "560001", "110001", "700001", "500001", "600001"]
        dest_pincodes = ["411001", "380001", "302001", "530001", "201301", "641001"]

        total_revenue_saved_minor = 0
        for i in range(40):
            # Built from formatted strings, not floats: Money.from_major()
            # rejects float on purpose, so seed data goes through the same
            # exact path as production data.
            val = round(random.uniform(199, 8999), 2)
            cost = round(random.uniform(40, val * 0.7), 2)
            val_money = Money.from_major(f"{val:.2f}", "INR")
            cost_money = Money.from_major(f"{cost:.2f}", "INR")
            resale_money = Money.from_major(f"{val * random.uniform(0.3, 0.8):.2f}", "INR")
            risk = round(random.uniform(5, 90), 1)
            dec = random.choice(decisions)
            created = _now() - timedelta(days=random.randint(0, 90))
            cid = random.choice(customer_ids) if customer_ids else None

            ret = models.ReturnRequest(
                org_id=org.id, merchant_id=org.id, platform_order_id=f"ORD-{10000 + i}",
                customer_id=cid, customer_identifier=f"cust_hash_{i % len(customer_ids)}",
                sku=random.choice(skus), item_category=random.choice(categories),
                item_value_minor=val_money.minor_units, currency="INR",
                origin_pincode=random.choice(origin_pincodes), destination_pincode=random.choice(dest_pincodes),
                weight_grams=random.randint(100, 2000), volumetric_weight_grams=random.randint(150, 2500),
                return_reason_code=random.choice(reasons), courier=random.choice(couriers),
                payment_mode=random.choice(["Prepaid", "Prepaid", "COD"]),
                fragile=random.random() > 0.8, festive=random.random() > 0.85,
                condition=random.choice(["like_new", "good", "good", "fair", "damaged"]),
                status=random.choice(["prediction_done", "approved", "refunded", "in_transit"]),
                raw_payload={}, created_at=created,
            )
            db.add(ret)
            db.flush()

            if dec in ("refund_and_keep", "reject"):
                total_revenue_saved_minor += cost_money.minor_units

            db.add(models.Prediction(
                return_request_id=ret.id, predicted_cost_minor=cost_money.minor_units,
                currency="INR", risk_score=risk,
                fraud_score=round(random.uniform(0, 60), 1), routing_decision=dec,
                damage_probability=round(random.uniform(0.0, 0.9), 2),
                resale_value_estimate_minor=resale_money.minor_units,
                carbon_footprint_kg=round(random.uniform(0.5, 8.0), 2),
                confidence_score=round(random.uniform(0.75, 0.99), 3),
                model_version="cost_xgb_v1.0.0", inference_latency_ms=round(random.uniform(3, 25), 2),
                feature_snapshot={}, explainability={}, created_at=created,
            ))

        org.total_returns = 40
        org.total_revenue_saved_minor = total_revenue_saved_minor

        raw_key, prefix = generate_api_key()
        key_hash = hash_api_key(raw_key, settings.API_KEY_HASH_PEPPER)
        db.add(models.ApiKey(key_hash=key_hash, org_id=org.id, name="Default Key", prefix=prefix, is_active=True))

        db.commit()
        return org.id, admin.id, raw_key


# ─────────────────────────────────────────────────────────────────────────────
# Orgs
# ─────────────────────────────────────────────────────────────────────────────
def get_org(org_id: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.Org, org_id))


def get_org_by_email(email: str) -> dict | None:
    with SessionLocal() as db:
        row = db.execute(select(models.Org).where(models.Org.contact_email == email)).scalar_one_or_none()
        return _to_dict(row)


def create_org(data: dict) -> dict:
    with SessionLocal() as db:
        org = models.Org(
            name=data["name"], slug=data.get("slug", ""), contact_email=data["contact_email"],
            platform_type=data.get("platform_type", "shopify"), plan_tier=data.get("plan_tier", "free"),
            is_active=data.get("is_active", True), risk_threshold=data.get("risk_threshold", 50.0),
            rate_limit_per_minute=data.get("rate_limit_per_minute", 60),
            settings=data.get("settings", {}),
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        return _to_dict(org)


def update_org(org_id: str, updates: dict) -> dict | None:
    with SessionLocal() as db:
        org = db.get(models.Org, org_id)
        if not org:
            return None
        for k, v in updates.items():
            setattr(org, k, v)
        db.commit()
        db.refresh(org)
        return _to_dict(org)


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────
def get_user(user_id: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.User, user_id))


def get_user_by_email(email: str) -> dict | None:
    with SessionLocal() as db:
        row = db.execute(select(models.User).where(models.User.email == email.lower())).scalar_one_or_none()
        return _to_dict(row)


def create_user(data: dict) -> dict:
    with SessionLocal() as db:
        user = models.User(
            org_id=data["org_id"], email=data["email"].lower(), full_name=data["full_name"],
            password_hash=data["password_hash"], role=data.get("role", "org_admin"),
            status=data.get("status", "active"), is_verified=data.get("is_verified", True),
            avatar_url=data.get("avatar_url", ""), mfa_enabled=data.get("mfa_enabled", False),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return _to_dict(user)


def get_users_for_org(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(models.User).where(models.User.org_id == org_id)).scalars().all()
        return [_to_dict(r) for r in rows]


def update_user(user_id: str, updates: dict) -> dict | None:
    with SessionLocal() as db:
        user = db.get(models.User, user_id)
        if not user:
            return None
        for k, v in updates.items():
            if hasattr(user, k):
                setattr(user, k, v)
        db.commit()
        db.refresh(user)
        return _to_dict(user)


# ─────────────────────────────────────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────────────────────────────────────
def get_api_key_record(key_hash: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.ApiKey, key_hash))


def store_api_key(key_hash: str, record: dict) -> None:
    with SessionLocal() as db:
        db.merge(models.ApiKey(
            key_hash=key_hash, org_id=record["org_id"], name=record.get("name", "Default Key"),
            prefix=record.get("prefix", ""), is_active=record.get("is_active", True),
        ))
        db.commit()


def get_org_api_keys(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(models.ApiKey).where(models.ApiKey.org_id == org_id)).scalars().all()
        return [_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Returns
# ─────────────────────────────────────────────────────────────────────────────
def store_return(data: dict) -> dict:
    with SessionLocal() as db:
        existing = db.get(models.ReturnRequest, data.get("id")) if data.get("id") else None
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            db.commit()
            db.refresh(existing)
            result = _to_dict(existing)
        else:
            ret = models.ReturnRequest(**{k: v for k, v in data.items() if hasattr(models.ReturnRequest, k)})
            db.add(ret)
            db.commit()
            db.refresh(ret)
            result = _to_dict(ret)

    # PHASE 39: invalidate here, not at each of the seven call sites that
    # write a return (ai_ux, portal x2, return_mgmt x2, returns x2).
    #
    # cache.py's cache_invalidate_org() existed and was correct, but nothing
    # in the codebase ever called it -- verified by grep before this change:
    # the only match for the function name was its own definition. Wiring
    # invalidation into every call site individually is exactly the kind of
    # thing a future eighth call site forgets. This is the one place every
    # write to a return already passes through, so it is the one place that
    # cannot be skipped by a new code path added later -- the same reasoning
    # as routing legacy audit calls through Phase 8's hash chain.
    org_id = result.get("org_id")
    if org_id:
        cache_invalidate_org(org_id)

    return result


def get_return_by_id(return_id: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.ReturnRequest, return_id))


def get_returns_for_org(org_id: str, filters: dict | None = None) -> list[dict]:
    """List an org's returns, newest first, with optional filtering.

    `status` and `category` are pushed into the SQL WHERE clause. `decision`
    is applied afterward in Python, since routing_decision lives on the
    related Prediction row, not on ReturnRequest itself - that's the one
    filter that can't be a single indexed query.
    """
    with SessionLocal() as db:
        q = select(models.ReturnRequest).where(
            (models.ReturnRequest.org_id == org_id) | (models.ReturnRequest.merchant_id == org_id)
        )
        if filters:
            if filters.get("status"):
                q = q.where(models.ReturnRequest.status == filters["status"])
            if filters.get("category"):
                q = q.where(models.ReturnRequest.item_category == filters["category"])
        rows = db.execute(q.order_by(models.ReturnRequest.created_at.desc())).scalars().all()
        results = [_to_dict(r) for r in rows]

        if filters and filters.get("decision"):
            ids = [r["id"] for r in results]
            preds = db.execute(
                select(models.Prediction).where(models.Prediction.return_request_id.in_(ids))
            ).scalars().all()
            decision_by_return = {p.return_request_id: p.routing_decision for p in preds}
            results = [r for r in results if decision_by_return.get(r["id"]) == filters["decision"]]
        return results


def store_prediction(data: dict) -> dict:
    with SessionLocal() as db:
        existing = db.execute(
            select(models.Prediction).where(models.Prediction.return_request_id == data["return_request_id"])
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            db.commit()
            db.refresh(existing)
            return _to_dict(existing)
        pred = models.Prediction(**{k: v for k, v in data.items() if hasattr(models.Prediction, k)})
        db.add(pred)
        db.commit()
        db.refresh(pred)
        return _to_dict(pred)


def get_prediction(return_id: str, org_id: str) -> dict | None:
    """Fetch a return's prediction, scoped to the owning organization.

    PHASE 4: org_id is mandatory and has no default. Predictions have no
    org_id column of their own, so isolation is enforced by joining through
    ReturnRequest -- the row is only visible if the parent return belongs to
    the caller's org. Making the parameter required means a new endpoint that
    forgets it fails at import/call time rather than silently leaking.
    """
    with SessionLocal() as db:
        row = db.execute(
            select(models.Prediction)
            .join(
                models.ReturnRequest,
                models.ReturnRequest.id == models.Prediction.return_request_id,
            )
            .where(
                models.Prediction.return_request_id == return_id,
                models.ReturnRequest.org_id == org_id,
            )
        ).scalar_one_or_none()
        return _to_dict(row)


def upsert_prediction_outcome(prediction_id: str, data: dict) -> dict:
    """
    Record (or update) the confirmed real-world outcome for a prediction.
    One outcome row per prediction - resubmitting overwrites the previous
    confirmation rather than creating duplicates, since the current known
    state is what training/evaluation should read.
    """
    with SessionLocal() as db:
        existing = db.execute(
            select(models.PredictionOutcome).where(models.PredictionOutcome.prediction_id == prediction_id)
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            db.commit()
            db.refresh(existing)
            return _to_dict(existing)
        outcome = models.PredictionOutcome(
            prediction_id=prediction_id,
            **{k: v for k, v in data.items() if hasattr(models.PredictionOutcome, k)},
        )
        db.add(outcome)
        db.commit()
        db.refresh(outcome)
        return _to_dict(outcome)


def count_labeled_outcomes(field: str = "actual_fraud_confirmed") -> int:
    """
    How many prediction_outcomes rows have a non-null value for the given
    field. Used to answer "do we have enough labels yet to train a real
    model" - see ml/train_fraud_model.py's threshold check.
    """
    col = getattr(models.PredictionOutcome, field)
    with SessionLocal() as db:
        return db.execute(
            select(func.count()).select_from(models.PredictionOutcome).where(col.is_not(None))
        ).scalar_one()


def count_customer_returns(customer_identifier: str, org_id: str) -> int:
    with SessionLocal() as db:
        return db.execute(
            select(func.count()).select_from(models.ReturnRequest).where(
                models.ReturnRequest.customer_identifier == customer_identifier,
                (models.ReturnRequest.org_id == org_id) | (models.ReturnRequest.merchant_id == org_id),
            )
        ).scalar_one()


def count_org_returns(org_id: str) -> int:
    with SessionLocal() as db:
        return db.execute(
            select(func.count()).select_from(models.ReturnRequest).where(
                (models.ReturnRequest.org_id == org_id) | (models.ReturnRequest.merchant_id == org_id)
            )
        ).scalar_one()


# ─────────────────────────────────────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────────────────────────────────────
def get_customers_for_org(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(models.Customer).where(models.Customer.org_id == org_id)).scalars().all()
        return [_to_dict(r) for r in rows]


def get_customer(customer_id: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.Customer, customer_id))


def store_customer(data: dict) -> dict:
    with SessionLocal() as db:
        cid = data.get("id")
        if cid:
            existing = db.get(models.Customer, cid)
            if existing:
                for k, v in data.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                db.commit()
                db.refresh(existing)
                return _to_dict(existing)
        c = models.Customer(**{k: v for k, v in data.items() if k != "id" and hasattr(models.Customer, k)})
        db.add(c)
        db.commit()
        db.refresh(c)
        return _to_dict(c)


# ─────────────────────────────────────────────────────────────────────────────
# Warehouses
# ─────────────────────────────────────────────────────────────────────────────
def get_warehouses_for_org(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(models.Warehouse).where(models.Warehouse.org_id == org_id)).scalars().all()
        return [_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────
def add_notification(data: dict) -> None:
    with SessionLocal() as db:
        db.add(models.Notification(**{k: v for k, v in data.items() if hasattr(models.Notification, k)}))
        db.commit()


def get_notifications_for_org(org_id: str, limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Notification).where(models.Notification.org_id == org_id)
            .order_by(models.Notification.created_at.desc()).limit(limit)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Audit logs
# ─────────────────────────────────────────────────────────────────────────────
def add_audit_log(data: dict) -> None:
    """Legacy entry point, retained so the 34 existing call sites keep working.

    Now routes through the hash chain, so every existing audit write becomes
    tamper-evident without touching those call sites. New code should call
    audit_service.record(), which also captures category, resource identity
    and correlation ID.
    """
    append_audit_event(data)


def append_audit_event(data: dict) -> None:
    """Append one event to an org's tamper-evident audit chain.

    The whole read-tail-then-insert runs inside a single transaction. Two
    concurrent writes that both read the same tail would otherwise commit to
    the same prev_hash, forking the chain -- and verification would report
    tampering that never happened, which is worse than useless because it
    trains people to ignore the alarm.

    `with_for_update()` takes a row lock on the current tail so the second
    writer waits. On SQLite this is a no-op (writes are already serialized);
    on Postgres it is what makes this correct.
    """
    from app.services.audit_service import compute_hash

    with SessionLocal() as db:
        try:
            tail = db.execute(
                select(models.AuditLog)
                .where(models.AuditLog.org_id == data["org_id"])
                .order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
        except Exception:  # noqa: BLE001
            # SQLite raises on FOR UPDATE in some configurations. Fall back to
            # the unlocked read; SQLite serializes writers anyway.
            tail = db.execute(
                select(models.AuditLog)
                .where(models.AuditLog.org_id == data["org_id"])
                .order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
                .limit(1)
            ).scalar_one_or_none()

        event = models.AuditLog(
            **{k: v for k, v in data.items() if hasattr(models.AuditLog, k)}
        )
        # Populate defaults now: the hash must cover the values that are
        # actually stored, and SQLAlchemy would not apply column defaults
        # until flush -- hashing before that would commit to None for id and
        # created_at, and verification would fail on every row.
        event.id = event.id or str(uuid.uuid4())
        event.created_at = event.created_at or _now()

        event.prev_hash = tail.event_hash if tail else None
        event.event_hash = compute_hash(event.prev_hash, {
            "id": event.id,
            "org_id": event.org_id,
            "user_id": event.user_id,
            "action": event.action,
            "category": event.category or "business",
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "detail": event.detail or "",
            "changes": event.changes,
            "created_at": event.created_at,
        })
        # category has a column default, but the hash above already committed
        # to "business" if it was unset -- so set it explicitly to keep the
        # stored row and the hashed payload identical.
        event.category = event.category or "business"

        db.add(event)
        db.commit()


def get_audit_chain(org_id: str, limit: int | None = None) -> list[dict]:
    """Audit events in chain order (oldest first), for verification."""
    with SessionLocal() as db:
        stmt = (
            select(models.AuditLog)
            .where(models.AuditLog.org_id == org_id)
            .order_by(models.AuditLog.created_at.asc(), models.AuditLog.id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return [_to_dict(r) for r in db.execute(stmt).scalars().all()]


def get_audit_logs(org_id: str, limit: int = 50) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.AuditLog).where(models.AuditLog.org_id == org_id)
            .order_by(models.AuditLog.created_at.desc()).limit(limit)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Login attempts / account lockout
# ─────────────────────────────────────────────────────────────────────────────
def record_login_attempt(email: str, success: bool) -> None:
    with SessionLocal() as db:
        db.add(models.LoginAttempt(email=email.lower(), success=success))
        db.commit()


def is_account_locked(email: str) -> bool:
    """True if this email has >= MAX_LOGIN_ATTEMPTS failed logins within
    the trailing LOCKOUT_DURATION_MINUTES window. The window is a rolling
    lookback (now - duration), not a fixed lockout timestamp, so it clears
    itself automatically once enough time passes without a new failure."""
    with SessionLocal() as db:
        cutoff = _now() - timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
        count = db.execute(
            select(func.count()).select_from(models.LoginAttempt).where(
                models.LoginAttempt.email == email.lower(),
                models.LoginAttempt.success.is_(False),
                models.LoginAttempt.created_at > cutoff,
            )
        ).scalar_one()
        return count >= settings.MAX_LOGIN_ATTEMPTS


# ─────────────────────────────────────────────────────────────────────────────
# Refresh-token rotation & revocation
# ─────────────────────────────────────────────────────────────────────────────
def create_refresh_token_record(jti: str, user_id: str, expires_at: datetime) -> None:
    with SessionLocal() as db:
        db.add(models.RefreshToken(jti=jti, user_id=user_id, expires_at=expires_at))
        db.commit()


def get_refresh_token_record(jti: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.RefreshToken, jti))


def rotate_refresh_token(old_jti: str, new_jti: str) -> None:
    """Mark old_jti as replaced by new_jti (normal refresh flow). Distinct
    from revoke_all_refresh_tokens_for_user below: rotation is the expected
    outcome of every successful /auth/refresh call, while revocation is
    only for suspected token theft or an explicit password change."""
    with SessionLocal() as db:
        old = db.get(models.RefreshToken, old_jti)
        if old:
            old.revoked_at = _now()
            old.replaced_by = new_jti
        db.commit()


def revoke_all_refresh_tokens_for_user(user_id: str) -> None:
    """Called on suspected token-replay (reuse of an already-rotated
    refresh token) or on password change — kills every active session."""
    with SessionLocal() as db:
        rows = db.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.user_id == user_id, models.RefreshToken.revoked_at.is_(None)
            )
        ).scalars().all()
        for r in rows:
            r.revoked_at = _now()
        db.commit()


def revoke_access_token(jti: str, expires_at: datetime) -> None:
    with SessionLocal() as db:
        db.merge(models.RevokedAccessToken(jti=jti, expires_at=expires_at))
        db.commit()


def is_access_token_revoked(jti: str) -> bool:
    with SessionLocal() as db:
        return db.get(models.RevokedAccessToken, jti) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard analytics
# ─────────────────────────────────────────────────────────────────────────────
def get_predictions_for_returns(return_ids: list[str], org_id: str) -> dict[str, dict]:
    """
    Fetch predictions for many returns in ONE query, keyed by return_request_id.

    Phase 11 performance fix. get_dashboard_stats() previously called
    get_prediction() inside a loop over every return - each call opened its
    own SessionLocal() and issued its own SELECT, so a dashboard load cost
    N+11 database round trips.

    Measured on a 1-vCPU box with ~130 returns: 174ms and 5.7 req/s, versus
    23ms for the ML scoring endpoint that actually runs a model. The
    dashboard was the slowest endpoint in the product while doing the least
    interesting work.

    PHASE 4: also org-scoped. A batch fetch is exactly where a leak would be
    least visible -- the caller passes a list of IDs and gets a dict back, so
    a foreign row would blend into legitimate results rather than standing out.
    """
    if not return_ids:
        return {}
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Prediction)
            .join(
                models.ReturnRequest,
                models.ReturnRequest.id == models.Prediction.return_request_id,
            )
            .where(
                models.Prediction.return_request_id.in_(return_ids),
                models.ReturnRequest.org_id == org_id,
            )
        ).scalars().all()
        return {r.return_request_id: _to_dict(r) for r in rows}


def get_dashboard_stats(org_id: str) -> dict:
    """Aggregate an org's returns for the dashboard.

    PHASE 9: instrumented because this was historically the slowest endpoint
    in the product (an N+1 over predictions, since fixed) and is the first
    place to look when the dashboard feels slow again.
    """
    all_returns = get_returns_for_org(org_id)
    total = len(all_returns)
    # Single batched query instead of one per return (see above).
    preds_by_return = get_predictions_for_returns([r["id"] for r in all_returns], org_id)
    decisions: dict[str, int] = {}
    # Money accumulates as int paise. Risk/fraud/carbon stay float -- they are
    # measurements, not currency, and averaging them is meaningful.
    # Currency comes from the org, never hardcoded -- Phase 43 depends on this.
    _org = get_org(org_id) or {}
    currency = _org.get("currency") or "INR"

    total_cost_minor = 0
    revenue_saved_minor = 0
    total_risk = total_fraud = total_carbon = 0.0
    pred_count = 0
    category_breakdown: dict[str, int] = {}
    courier_breakdown: dict[str, int] = {}
    monthly_trend: dict[str, int] = {}

    for r in all_returns:
        cat = r.get("item_category", "other")
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
        courier = r.get("courier", "other")
        courier_breakdown[courier] = courier_breakdown.get(courier, 0) + 1
        month = (r.get("created_at") or "")[:7]
        if month:
            monthly_trend[month] = monthly_trend.get(month, 0) + 1

        pred = preds_by_return.get(r["id"])
        if pred:
            d = pred.get("routing_decision", "unknown")
            decisions[d] = decisions.get(d, 0) + 1
            total_cost_minor += int(pred.get("predicted_cost_minor") or 0)
            total_risk += pred.get("risk_score", 0)
            total_fraud += pred.get("fraud_score", 0)
            total_carbon += pred.get("carbon_footprint_kg", 0)
            pred_count += 1
            if d in ("refund_and_keep", "reject"):
                revenue_saved_minor += int(pred.get("predicted_cost_minor") or 0)

    recent = [
        {**r, "prediction": preds_by_return.get(r["id"])}
        for r in all_returns[:10]
    ]

    sorted_trend = [{"month": k, "count": v} for k, v in sorted(monthly_trend.items())[-6:]]

    return {
        "total_returns": total,
        "decisions": decisions,
        # Money leaves the backend in the Money wire format -- minor_units is
        # the exact value, "formatted" saves every client reimplementing
        # currency exponents and grouping.
        "avg_predicted_cost": Money(
            total_cost_minor // pred_count if pred_count else 0, currency
        ).as_dict(),
        "avg_risk_score": round(total_risk / pred_count, 2) if pred_count else 0,
        "avg_fraud_score": round(total_fraud / pred_count, 2) if pred_count else 0,
        "total_carbon_kg": round(total_carbon, 2),
        "revenue_saved": Money(revenue_saved_minor, currency).as_dict(),
        "category_breakdown": [{"name": k, "value": v} for k, v in category_breakdown.items()],
        "courier_breakdown": [{"name": k, "value": v} for k, v in courier_breakdown.items()],
        "monthly_trend": sorted_trend,
        "recent_returns": recent,
        "kpis": {
            # Phase 11 audit: three KPIs here were fabricated constants
            # presented to users as measurements.
            #
            #   return_rate            = total / (total * 8) -> always 12.5%,
            #                            regardless of any input
            #   avg_processing_time_hrs = hardcoded 2.4
            #   customer_satisfaction   = hardcoded 4.6
            #
            # None was computed from data. return_rate is now omitted entirely
            # because the merchant's total order count is not something this
            # system knows - a return rate needs a denominator we don't have.
            # The other two are returned as None with an explicit reason, so
            # the UI can show "not measured" rather than an invented figure.
            "auto_approval_rate": round((decisions.get("accept", 0) / max(total, 1)) * 100, 1),
            "fraud_flagged": decisions.get("reject", 0),
            "avg_processing_time_hrs": None,
            "customer_satisfaction": None,
            "unavailable_metrics": {
                "return_rate": "Requires total order count, which ReturnIQ does not receive.",
                "avg_processing_time_hrs": "Requires status-change timestamps; not yet recorded.",
                "customer_satisfaction": "No CSAT data is collected by this system.",
            },
        }
    }


def get_analytics_data(org_id: str) -> dict:
    stats = get_dashboard_stats(org_id)
    all_returns = get_returns_for_org(org_id)
    # Same batched fetch as the dashboard - this function had the identical
    # N+1 pattern, and because it also calls get_dashboard_stats() it was
    # paying that cost twice per request.
    preds_by_return = get_predictions_for_returns([r["id"] for r in all_returns], org_id)

    reason_breakdown: dict[str, int] = {}
    value_buckets: dict[str, int] = {"0-500": 0, "500-2000": 0, "2000-5000": 0, "5000+": 0}
    risk_distribution = {"low (0-30)": 0, "medium (30-60)": 0, "high (60-80)": 0, "critical (80+)": 0}

    for r in all_returns:
        reason = r.get("return_reason_code", "other")
        reason_breakdown[reason] = reason_breakdown.get(reason, 0) + 1
        # Buckets are in rupees; compare in paise to avoid a float round-trip.
        val = int(r.get("item_value_minor") or 0) / 100
        if val < 500:
            value_buckets["0-500"] += 1
        elif val < 2000:
            value_buckets["500-2000"] += 1
        elif val < 5000:
            value_buckets["2000-5000"] += 1
        else:
            value_buckets["5000+"] += 1

        pred = preds_by_return.get(r["id"])
        if pred:
            risk = pred.get("risk_score", 0)
            if risk < 30:
                risk_distribution["low (0-30)"] += 1
            elif risk < 60:
                risk_distribution["medium (30-60)"] += 1
            elif risk < 80:
                risk_distribution["high (60-80)"] += 1
            else:
                risk_distribution["critical (80+)"] += 1

    return {
        **stats,
        "reason_breakdown": [{"name": k, "value": v} for k, v in reason_breakdown.items()],
        "value_buckets": [{"range": k, "count": v} for k, v in value_buckets.items()],
        "risk_distribution": [{"level": k, "count": v} for k, v in risk_distribution.items()],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Module-level demo constants (kept for backward compatibility with any code
# that imports DEMO_ORG_ID etc. directly). These are populated lazily on
# first access via get_demo_credentials(), since seeding now requires a live
# DB connection and shouldn't happen at import time.
# ─────────────────────────────────────────────────────────────────────────────
_demo_cache: dict[str, str] | None = None


def get_demo_credentials() -> dict[str, str] | None:
    global _demo_cache
    if _demo_cache is not None:
        return _demo_cache
    seeded = seed_if_needed()
    if seeded:
        org_id, user_id, raw_key = seeded
        _demo_cache = {"org_id": org_id, "user_id": user_id, "api_key": raw_key}
        return _demo_cache
    # DB already seeded from a previous run — look up the demo org instead.
    org = get_org_by_email("admin@sapnacollection.com")
    if org:
        user = get_user_by_email("admin@sapnacollection.com")
        _demo_cache = {"org_id": org["id"], "user_id": user["id"] if user else "", "api_key": ""}
        return _demo_cache
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Password reset
# ─────────────────────────────────────────────────────────────────────────────
def create_password_reset_token(token: str, user_id: str, expires_at) -> None:
    with SessionLocal() as db:
        db.add(models.PasswordResetToken(token=token, user_id=user_id, expires_at=expires_at))
        db.commit()


def get_password_reset_token(token: str) -> dict | None:
    with SessionLocal() as db:
        return _to_dict(db.get(models.PasswordResetToken, token))


def consume_password_reset_token(token: str) -> None:
    with SessionLocal() as db:
        row = db.get(models.PasswordResetToken, token)
        if row:
            row.used = True
            db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Account tokens (invitation / email verification)
# ─────────────────────────────────────────────────────────────────────────────
def create_account_token(token_hash: str, user_id: str, purpose: str, expires_at) -> None:
    with SessionLocal() as db:
        db.add(models.AccountToken(
            token_hash=token_hash, user_id=user_id,
            purpose=purpose, expires_at=expires_at,
        ))
        db.commit()


def invalidate_account_tokens(user_id: str, purpose: str) -> int:
    """Burn every outstanding token of this purpose for this user.

    Called before issuing a new one, so that reissuing an invitation actually
    revokes the previous link rather than leaving two live.
    """
    with SessionLocal() as db:
        result = db.execute(
            update(models.AccountToken)
            .where(
                models.AccountToken.user_id == user_id,
                models.AccountToken.purpose == purpose,
                models.AccountToken.used_at.is_(None),
            )
            .values(used_at=_now())
        )
        db.commit()
        return result.rowcount or 0


def consume_account_token(token_hash: str, purpose: str, now) -> str | None:
    """Atomically validate and burn a token; return the user_id or None.

    This is a single conditional UPDATE, not a SELECT followed by an UPDATE.
    With a read-then-write, two requests presenting the same invitation token
    simultaneously would both pass the validity check before either marked it
    used -- so one token would set two passwords. The database decides the
    winner here: `used_at IS NULL` is part of the UPDATE predicate, so exactly
    one statement can match.
    """
    with SessionLocal() as db:
        result = db.execute(
            update(models.AccountToken)
            .where(
                models.AccountToken.token_hash == token_hash,
                models.AccountToken.purpose == purpose,
                models.AccountToken.used_at.is_(None),
                models.AccountToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(models.AccountToken.user_id)
        )
        row = result.first()
        db.commit()
        return row[0] if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Return notes & documents
# ─────────────────────────────────────────────────────────────────────────────
def add_return_note(data: dict) -> dict:
    with SessionLocal() as db:
        note = models.ReturnNote(**{k: v for k, v in data.items() if hasattr(models.ReturnNote, k)})
        db.add(note)
        db.commit()
        db.refresh(note)
        return _to_dict(note)


def get_return_notes(return_request_id: str, org_id: str) -> list[dict]:
    """PHASE 4: tenant-scoped via join through ReturnRequest."""
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnNote)
            .join(
                models.ReturnRequest,
                models.ReturnRequest.id == models.ReturnNote.return_request_id,
            )
            .where(
                models.ReturnNote.return_request_id == return_request_id,
                models.ReturnRequest.org_id == org_id,
            )
            .order_by(models.ReturnNote.created_at.asc())
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def store_return_document(data: dict) -> dict:
    with SessionLocal() as db:
        doc = models.ReturnDocument(**{k: v for k, v in data.items() if hasattr(models.ReturnDocument, k)})
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return _to_dict(doc)


def touch_api_key(key_hash: str) -> None:
    """Record that a key was used.

    PHASE 34. Best-effort and never raises: a failure to record usage must not
    fail the request it is describing. An integration going down because the
    analytics write failed would be a worse outcome than a stale timestamp.
    """
    try:
        with SessionLocal() as db:
            row = db.get(models.ApiKey, key_hash)
            if row:
                row.last_used_at = _now()
                db.commit()
    except Exception:  # noqa: BLE001 -- see docstring
        logger.exception("Could not record API key usage")


def find_order_for_portal(org_id: str, platform_order_id: str) -> dict | None:
    """Look up one order within one merchant.

    PHASE 31. org_id is mandatory and is NOT supplied by the customer — it
    comes from the merchant's portal subdomain or embed key. Order IDs are
    unique per merchant, not globally: ORD-1001 may exist at fifty merchants,
    and a lookup without a tenant would return whichever row the database
    happened to find first.
    """
    with SessionLocal() as db:
        row = db.execute(
            select(models.ReturnRequest).where(
                models.ReturnRequest.platform_order_id == platform_order_id,
                models.ReturnRequest.org_id == org_id,
            ).order_by(models.ReturnRequest.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        return _to_dict(row)


def create_portal_session(data: dict) -> None:
    with SessionLocal() as db:
        db.add(models.PortalSession(
            **{k: v for k, v in data.items() if hasattr(models.PortalSession, k)}
        ))
        db.commit()


def get_portal_session(token_hash: str, now) -> dict | None:
    """Resolve a portal token, or None.

    Expiry and revocation are part of the query rather than checked
    afterwards. A caller who forgets the follow-up check would otherwise get a
    valid-looking session object for an expired token — and that caller is a
    public endpoint.
    """
    with SessionLocal() as db:
        row = db.execute(
            select(models.PortalSession).where(
                models.PortalSession.token_hash == token_hash,
                models.PortalSession.expires_at > now,
                models.PortalSession.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        return _to_dict(row)


def revoke_portal_session(token_hash: str, now) -> None:
    with SessionLocal() as db:
        row = db.get(models.PortalSession, token_hash)
        if row and row.revoked_at is None:
            row.revoked_at = now
            db.commit()


def bind_portal_session_to_return(token_hash: str, return_request_id: str) -> None:
    """Attach a session to the return it created.

    Bound once. A session that could be rebound would let one lookup be reused
    to attach evidence to a different return.
    """
    with SessionLocal() as db:
        row = db.get(models.PortalSession, token_hash)
        if row and row.return_request_id is None:
            row.return_request_id = return_request_id
            db.commit()


def record_decision_override(data: dict) -> dict:
    """PHASE 26. Persist a human decision alongside what the system advised."""
    with SessionLocal() as db:
        row = models.DecisionOverride(
            **{k: v for k, v in data.items() if hasattr(models.DecisionOverride, k)}
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def get_overrides_for_org(org_id: str, *, disagreements_only: bool = False) -> list[dict]:
    """Recorded decisions for this org, newest first.

    `disagreements_only` exists for review workflows, but training should use
    the full set. A model evaluated only on cases where humans disagreed is
    evaluated on a biased sample and will look far worse than it is.
    """
    with SessionLocal() as db:
        stmt = select(models.DecisionOverride).where(
            models.DecisionOverride.org_id == org_id
        )
        if disagreements_only:
            stmt = stmt.where(
                models.DecisionOverride.system_decision
                != models.DecisionOverride.human_decision
            )
        rows = db.execute(
            stmt.order_by(models.DecisionOverride.created_at.desc()).limit(1000)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def count_overrides(org_id: str) -> dict:
    """Agreement rate — how often the system's recommendation is accepted.

    The single most useful number about whether the intelligence layer is
    trusted, and it needs no outcome labels to compute.
    """
    with SessionLocal() as db:
        total = db.execute(
            select(func.count()).select_from(models.DecisionOverride).where(
                models.DecisionOverride.org_id == org_id
            )
        ).scalar_one()
        disagreements = db.execute(
            select(func.count()).select_from(models.DecisionOverride).where(
                models.DecisionOverride.org_id == org_id,
                models.DecisionOverride.system_decision
                != models.DecisionOverride.human_decision,
            )
        ).scalar_one()
    return {
        "total_decisions": total,
        "disagreements": disagreements,
        "agreement_rate": round(1 - disagreements / total, 4) if total else None,
    }


def get_returns_for_customer(customer_identifier: str, org_id: str) -> list[dict]:
    """This customer's returns within this org.

    PHASE 23. org_id is mandatory (Phase 4): a customer identifier may recur
    across merchants — the same phone number shops at more than one shop —
    and matching across tenants would leak one merchant's customer behaviour
    into another's review screen.
    """
    if not customer_identifier:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnRequest).where(
                models.ReturnRequest.customer_identifier == customer_identifier,
                models.ReturnRequest.org_id == org_id,
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def get_returns_for_sku(sku: str, org_id: str) -> list[dict]:
    """This SKU's return history within this org.

    Capped, because a high-volume SKU could have tens of thousands of returns
    and this runs on a page load. The features derived from it — damage rate,
    return count — are stable well before that limit.
    """
    if not sku:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnRequest)
            .where(
                models.ReturnRequest.sku == sku,
                models.ReturnRequest.org_id == org_id,
            )
            .order_by(models.ReturnRequest.created_at.desc())
            .limit(500)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def get_documents_by_hash(org_id: str, content_sha256: str) -> list[dict]:
    """Every document in this org with the same content hash.

    PHASE 13. Org-scoped, and that scoping is a design decision rather than
    only an isolation rule: cross-tenant matching would be a far stronger
    fraud signal (a serial returner hits many merchants), but it would mean
    one merchant's evidence informing another merchant's decision. That is
    Phase 54 (network intelligence), where it needs a privacy-preserving
    design and customer consent -- not something to acquire quietly here.
    """
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnDocument).where(
                models.ReturnDocument.org_id == org_id,
                models.ReturnDocument.content_sha256 == content_sha256,
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def get_return_documents(return_request_id: str, org_id: str) -> list[dict]:
    """PHASE 4: tenant-scoped via join through ReturnRequest.

    Documents are customer-uploaded evidence images -- among the most
    sensitive data in the product. An unscoped read here would expose one
    merchant's customer photographs to another.
    """
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnDocument)
            .join(
                models.ReturnRequest,
                models.ReturnRequest.id == models.ReturnDocument.return_request_id,
            )
            .where(
                models.ReturnDocument.return_request_id == return_request_id,
                models.ReturnRequest.org_id == org_id,
            )
            .order_by(models.ReturnDocument.created_at.asc())
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def delete_return_document(doc_id: str, org_id: str) -> bool:
    with SessionLocal() as db:
        doc = db.get(models.ReturnDocument, doc_id)
        if not doc or doc.org_id != org_id:
            return False
        db.delete(doc)
        db.commit()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Workflow rules
# ─────────────────────────────────────────────────────────────────────────────
def get_workflow_rules(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.WorkflowRule)
            .where(models.WorkflowRule.org_id == org_id)
            .order_by(models.WorkflowRule.priority.asc())
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def create_workflow_rule(data: dict) -> dict:
    with SessionLocal() as db:
        rule = models.WorkflowRule(**{k: v for k, v in data.items() if hasattr(models.WorkflowRule, k)})
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return _to_dict(rule)


def update_workflow_rule(rule_id: str, org_id: str, updates: dict) -> dict | None:
    with SessionLocal() as db:
        rule = db.get(models.WorkflowRule, rule_id)
        if not rule or rule.org_id != org_id:
            return None
        for k, v in updates.items():
            if hasattr(rule, k):
                setattr(rule, k, v)
        db.commit()
        db.refresh(rule)
        return _to_dict(rule)


def delete_workflow_rule(rule_id: str, org_id: str) -> bool:
    with SessionLocal() as db:
        rule = db.get(models.WorkflowRule, rule_id)
        if not rule or rule.org_id != org_id:
            return False
        db.delete(rule)
        db.commit()
        return True


def increment_rule_triggered(rule_id: str) -> None:
    with SessionLocal() as db:
        rule = db.get(models.WorkflowRule, rule_id)
        if rule:
            rule.triggered_count = (rule.triggered_count or 0) + 1
            db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Feature flags
# ─────────────────────────────────────────────────────────────────────────────
def get_feature_flags(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.FeatureFlag).where(models.FeatureFlag.org_id == org_id)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def set_feature_flag(org_id: str, flag_name: str, enabled: bool) -> dict:
    with SessionLocal() as db:
        existing = db.execute(
            select(models.FeatureFlag).where(
                models.FeatureFlag.org_id == org_id,
                models.FeatureFlag.flag_name == flag_name,
            )
        ).scalar_one_or_none()
        if existing:
            existing.enabled = enabled
            db.commit()
            db.refresh(existing)
            return _to_dict(existing)
        flag = models.FeatureFlag(org_id=org_id, flag_name=flag_name, enabled=enabled)
        db.add(flag)
        db.commit()
        db.refresh(flag)
        return _to_dict(flag)


def is_feature_enabled(org_id: str, flag_name: str) -> bool:
    with SessionLocal() as db:
        row = db.execute(
            select(models.FeatureFlag).where(
                models.FeatureFlag.org_id == org_id,
                models.FeatureFlag.flag_name == flag_name,
            )
        ).scalar_one_or_none()
        return bool(row and row.enabled)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Customer extensions
# ─────────────────────────────────────────────────────────────────────────────
def update_customer(customer_id: str, updates: dict) -> dict | None:
    with SessionLocal() as db:
        c = db.get(models.Customer, customer_id)
        if not c:
            return None
        for k, v in updates.items():
            if hasattr(c, k):
                setattr(c, k, v)
        db.commit()
        db.refresh(c)
        return _to_dict(c)


def search_customers(org_id: str, query: str, limit: int = 20) -> list[dict]:
    """
    Search customers by name or email.

    Filters in Python rather than SQL because name/email are encrypted at rest
    (see core/encryption.py). Fernet uses a random IV, so identical plaintext
    produces different ciphertext every time - a SQL LIKE against the stored
    value can never match. That is the property that makes the encryption
    sound, and the reason this cannot be pushed into the database.

    Cost: O(n) over the org's customers per search. Acceptable at a few
    thousand customers; past roughly 50,000 this needs a blind index - a
    separate deterministic HMAC column used only for equality lookup. Tracked
    in the architecture debt register.
    """
    q = query.lower().strip()
    if not q:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Customer).where(models.Customer.org_id == org_id)
        ).scalars().all()

        matches = []
        for r in rows:
            # Attribute access decrypts via the TypeDecorator.
            name = (r.name or "").lower()
            email = (r.email or "").lower()
            if q in name or q in email:
                matches.append(_to_dict(r))
                if len(matches) >= limit:
                    break
        return matches



def add_customer_to_blacklist(org_id: str, customer_identifier: str, reason: str, user_id: str) -> dict:
    with SessionLocal() as db:
        existing = db.execute(
            select(models.CustomerBlacklist).where(
                models.CustomerBlacklist.org_id == org_id,
                models.CustomerBlacklist.customer_identifier == customer_identifier,
            )
        ).scalar_one_or_none()
        if existing:
            return _to_dict(existing)
        entry = models.CustomerBlacklist(
            org_id=org_id, customer_identifier=customer_identifier,
            reason=reason, blacklisted_by=user_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return _to_dict(entry)


def is_customer_blacklisted(org_id: str, customer_identifier: str) -> bool:
    with SessionLocal() as db:
        row = db.execute(
            select(models.CustomerBlacklist).where(
                models.CustomerBlacklist.org_id == org_id,
                models.CustomerBlacklist.customer_identifier == customer_identifier,
            )
        ).scalar_one_or_none()
        return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Notifications mark-read
# ─────────────────────────────────────────────────────────────────────────────
def mark_notifications_read(org_id: str, notification_ids: list[str]) -> int:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Notification).where(
                models.Notification.org_id == org_id,
                models.Notification.id.in_(notification_ids),
            )
        ).scalars().all()
        for row in rows:
            row.read = True
        db.commit()
        return len(rows)


def get_unread_notification_count(org_id: str) -> int:
    with SessionLocal() as db:
        return db.execute(
            select(func.count()).select_from(models.Notification).where(
                models.Notification.org_id == org_id,
                models.Notification.read.is_(False),
            )
        ).scalar_one()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — System settings (super_admin)
# ─────────────────────────────────────────────────────────────────────────────
def get_system_settings() -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(models.SystemSetting)).scalars().all()
        return [_to_dict(r) for r in rows]


def set_system_setting(key: str, value, user_id: str) -> dict:
    with SessionLocal() as db:
        row = db.get(models.SystemSetting, key)
        if row:
            row.value = value
            row.updated_by = user_id
            db.commit()
            db.refresh(row)
            return _to_dict(row)
        setting = models.SystemSetting(key=key, value=value, updated_by=user_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return _to_dict(setting)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — SLA Tracking
# ─────────────────────────────────────────────────────────────────────────────
def create_sla_record(data: dict) -> dict:
    with SessionLocal() as db:
        sla = models.SLATracking(**{k: v for k, v in data.items() if hasattr(models.SLATracking, k)})
        db.add(sla)
        db.commit()
        db.refresh(sla)
        return _to_dict(sla)


def get_sla_for_return(return_request_id: str, org_id: str) -> dict | None:
    """PHASE 4: tenant-scoped via join through ReturnRequest."""
    with SessionLocal() as db:
        row = db.execute(
            select(models.SLATracking)
            .join(
                models.ReturnRequest,
                models.ReturnRequest.id == models.SLATracking.return_request_id,
            )
            .where(
                models.SLATracking.return_request_id == return_request_id,
                models.ReturnRequest.org_id == org_id,
            )
        ).scalar_one_or_none()
        return _to_dict(row)


def get_breached_slas(org_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.SLATracking).where(
                models.SLATracking.org_id == org_id,
                models.SLATracking.breached.is_(True),
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def delete_user(user_id: str) -> bool:
    with SessionLocal() as db:
        u = db.get(models.User, user_id)
        if not u:
            return False
        db.delete(u)
        db.commit()
        return True


# Alias: store_user maps to create_user for consistent naming in Phase 5
def store_user(data: dict) -> dict:
    """Create or update a user record. Wraps create_user for Phase 5 invite flow."""
    return create_user(data)


# ── Consent records (DPDP Act 2023) ──────────────────────────────────────────

def record_consent(data: dict) -> dict:
    """
    Append a consent record. Append-only by design: withdrawal is a new row
    with granted=False, never a mutation, so the history stays auditable.
    """
    with SessionLocal() as db:
        rec = models.ConsentRecord(
            **{k: v for k, v in data.items() if hasattr(models.ConsentRecord, k)}
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)


def get_consent_history(user_id: str) -> list[dict]:
    """Full consent history for a user - satisfies the DPDP right of access."""
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ConsentRecord)
            .where(models.ConsentRecord.user_id == user_id)
            .order_by(models.ConsentRecord.created_at.desc())
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def has_valid_consent(user_id: str, consent_type: str = "terms_and_privacy") -> bool:
    """True if the most recent record for this consent type granted it."""
    with SessionLocal() as db:
        row = db.execute(
            select(models.ConsentRecord)
            .where(
                models.ConsentRecord.user_id == user_id,
                models.ConsentRecord.consent_type == consent_type,
            )
            .order_by(models.ConsentRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return bool(row and row.granted)



# ─────────────────────────────────────────────────────────────────────────────
# COD risk & courier remittance (merged from the parallel feature branch)
# ─────────────────────────────────────────────────────────────────────────────

def create_cod_risk_assessment(data: dict) -> dict:
    with SessionLocal() as db:
        row = models.CODRiskAssessment(
            **{k: v for k, v in data.items() if hasattr(models.CODRiskAssessment, k)}
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def get_cod_risk_assessment_by_order_id(org_id: str, platform_order_id: str) -> dict | None:
    """Most recent COD risk assessment for a given order, if this order
    was scored pre-shipment. Used by remittance reconciliation to know
    what amount the seller actually expected the courier to collect/pay."""
    with SessionLocal() as db:
        row = db.execute(
            select(models.CODRiskAssessment)
            .where(
                models.CODRiskAssessment.org_id == org_id,
                models.CODRiskAssessment.platform_order_id == platform_order_id,
            )
            .order_by(models.CODRiskAssessment.created_at.desc())
        ).scalars().first()
        return _to_dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Courier Remittance Reconciliation
# ─────────────────────────────────────────────────────────────────────────────


def get_cod_risk_assessments_for_org(org_id: str, limit: int = 100) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.CODRiskAssessment)
            .where(models.CODRiskAssessment.org_id == org_id)
            .order_by(models.CODRiskAssessment.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def create_courier_remittance(data: dict) -> dict:
    with SessionLocal() as db:
        row = models.CourierRemittance(
            **{k: v for k, v in data.items() if hasattr(models.CourierRemittance, k)}
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def get_remittances_for_org(
    org_id: str,
    status: str | None = None,
    courier: str | None = None,
    limit: int = 200,
) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(models.CourierRemittance).where(models.CourierRemittance.org_id == org_id)
        if status:
            stmt = stmt.where(models.CourierRemittance.status == status)
        if courier:
            stmt = stmt.where(models.CourierRemittance.courier == courier)
        rows = db.execute(
            stmt.order_by(models.CourierRemittance.created_at.desc()).limit(limit)
        ).scalars().all()
        return [_to_dict(r) for r in rows]


def get_customer_by_phone(org_id: str, phone: str) -> dict | None:
    """Look up a customer by phone within an org. Returns None for
    first-time customers -- that itself is a signal the scoring service uses."""
    with SessionLocal() as db:
        row = db.execute(
            select(models.Customer).where(
                models.Customer.org_id == org_id,
                models.Customer.phone == phone,
            )
        ).scalars().first()
        return _to_dict(row) if row else None


def get_pincode_fraud_stats(org_id: str, pincode: str) -> dict:
    """
    Real historical fraud-score stats for returns shipped to this pincode,
    for this org. Used by COD risk scoring to judge whether a pincode is
    actually high-risk -- based on this org's own return history, not a
    hardcoded guess.
    """
    with SessionLocal() as db:
        rows = db.execute(
            select(models.Prediction.fraud_score)
            .join(models.ReturnRequest, models.ReturnRequest.id == models.Prediction.return_request_id)
            .where(
                (models.ReturnRequest.org_id == org_id) | (models.ReturnRequest.merchant_id == org_id),
                models.ReturnRequest.destination_pincode == pincode,
            )
        ).scalars().all()
        count = len(rows)
        avg_fraud_score = (sum(rows) / count) if count else 0.0
        return {"sample_count": count, "avg_fraud_score": round(avg_fraud_score, 2)}


def get_recent_names_at_address(org_id: str, address: str, limit: int = 20) -> list[str]:
    """Distinct customer names that have had a COD order scored against
    this exact delivery address before. Used to catch the same address
    being used by many different "customers" -- a common fraud-ring pattern."""
    with SessionLocal() as db:
        rows = db.execute(
            select(models.CODRiskAssessment.customer_name)
            .where(
                models.CODRiskAssessment.org_id == org_id,
                models.CODRiskAssessment.delivery_address == address,
            )
            .distinct()
            .limit(limit)
        ).scalars().all()
        return list(rows)
