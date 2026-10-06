"""SQLAlchemy ORM models — the real, persistent schema behind ReturnIQ."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.core.encryption import EncryptedString


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    contact_email: Mapped[str] = mapped_column(String(320), index=True)
    platform_type: Mapped[str] = mapped_column(String(50), default="shopify")
    plan_tier: Mapped[str] = mapped_column(String(50), default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_threshold: Mapped[float] = mapped_column(Float, default=50.0)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    total_returns: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue_saved_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="org_admin")
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Default Key")
    prefix: Mapped[str] = mapped_column(String(20), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # PHASE 34 — scoping, expiry and usage.
    #
    # Before this, a key granted everything the external API exposed. A key
    # given to a read-only analytics vendor could create returns; a key
    # embedded in a storefront widget, visible to anyone with developer
    # tools, could do the same.
    #
    # Scopes reuse the Phase 6 permission strings rather than a parallel
    # vocabulary: `returns.read` means the same thing whether a person or a
    # key holds it.
    scopes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Keys expire. Without this, a key outlives the integration it was made
    # for, the contractor who configured it, and often the company that
    # received it.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Makes revocation possible. Nobody revokes a key they cannot describe,
    # so an unused key sits active for years because removing it risks
    # breaking an unknown integration.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    merchant_id: Mapped[str] = mapped_column(String(36), index=True)  # backward compat alias of org_id
    platform_order_id: Mapped[str] = mapped_column(String(128))
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_identifier: Mapped[str] = mapped_column(String(64), index=True)
    sku: Mapped[str] = mapped_column(String(128))
    item_category: Mapped[str] = mapped_column(String(100))
    item_value_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    origin_pincode: Mapped[str] = mapped_column(String(6))
    destination_pincode: Mapped[str] = mapped_column(String(6))
    weight_grams: Mapped[int] = mapped_column(Integer)
    volumetric_weight_grams: Mapped[int] = mapped_column(Integer)
    return_reason_code: Mapped[str] = mapped_column(String(50))
    courier: Mapped[str] = mapped_column(String(50))
    payment_mode: Mapped[str] = mapped_column(String(20))
    fragile: Mapped[bool] = mapped_column(Boolean, default=False)
    festive: Mapped[bool] = mapped_column(Boolean, default=False)
    condition: Mapped[str] = mapped_column(String(20), default="good")
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_now)

    prediction: Mapped[Prediction] = relationship(back_populates="return_request", uselist=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    return_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("return_requests.id"), unique=True, index=True
    )
    predicted_cost_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    risk_score: Mapped[float] = mapped_column(Float)
    fraud_score: Mapped[float] = mapped_column(Float)
    damage_probability: Mapped[float] = mapped_column(Float)
    resale_value_estimate_minor: Mapped[int] = mapped_column(BigInteger)
    carbon_footprint_kg: Mapped[float] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float)
    routing_decision: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(50))
    inference_latency_ms: Mapped[float] = mapped_column(Float)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    explainability: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    return_request: Mapped[ReturnRequest] = relationship(back_populates="prediction")
    outcome: Mapped[PredictionOutcome] = relationship(back_populates="prediction", uselist=False)


class PredictionOutcome(Base):
    """
    Ground-truth outcome for a prediction, confirmed after the fact by a
    human (warehouse inspection, finance reconciliation, etc).

    This table exists because fraud_score/damage_probability/predicted_cost
    are currently produced with NO way to ever check if they were right -
    there's no field anywhere that records what actually happened to a
    return. That makes it impossible to (a) measure real-world accuracy of
    the rule-based fraud/damage scores, or (b) ever train a real supervised
    model for them, since supervised training requires labels.

    Nothing writes to this table yet - see the /outcome endpoint in
    returns.py for how it gets populated, and ml/train_fraud_model.py for
    what happens once enough rows exist here.
    """
    __tablename__ = "prediction_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    prediction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("predictions.id"), unique=True, index=True
    )
    # None = not yet reviewed. True/False = confirmed after inspection.
    actual_fraud_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # One of: none, minor, major, total_loss. None = not yet inspected.
    actual_damage_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Real processing/shipping cost once known (vs. predicted_cost_inr at prediction time).
    actual_cost_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # Real resale price if the item was actually resold (vs. resale_value_estimate).
    actual_resale_price_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    prediction: Mapped[Prediction] = relationship(back_populates="outcome")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    # PII encrypted at rest (KI-002). Encrypted columns cannot be searched
    # with SQL LIKE - store.search_customers() filters in Python instead.
    name: Mapped[str] = mapped_column(EncryptedString(200))
    email: Mapped[str] = mapped_column(EncryptedString(320))
    phone: Mapped[str | None] = mapped_column(EncryptedString(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_returns: Mapped[int] = mapped_column(Integer, default=0)
    fraud_score: Mapped[float] = mapped_column(Float, default=0.0)
    clv_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    # Added in Phase 5 migration c7f91a3d2e55. These were present in the
    # database but missing from this model, which silently broke the
    # blacklist feature: store.update_customer() filters updates with
    # hasattr(), so is_blacklisted=True was dropped before it ever reached
    # the DB, and the field never appeared in API responses.
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    pincode: Mapped[str] = mapped_column(String(6))
    state: Mapped[str] = mapped_column(String(100))
    capacity_units: Mapped[int] = mapped_column(Integer, default=0)
    used_units: Mapped[int] = mapped_column(Integer, default=0)
    zones: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AuditLog(Base):
    """Immutable, tamper-evident record of consequential actions.

    PHASE 8. Previously this stored only WHO (user_id), WHAT (action, free-text
    detail) and WHEN. That is enough to skim, and not enough to investigate:
    you could see "return_approved" but not which return, from where, by which
    request, or what the value was before the change.

    Three additions matter beyond extra columns:

    **Category.** Business actions, security events and ML events have
    different audiences and retention needs. A fraud analyst reviewing
    approvals should not have to filter past login failures, and a security
    investigation should not have to filter past model deployments.

    **Resource identity as columns, not prose.** `detail` was free text, so
    "which returns did this user approve last week" required a LIKE query
    against English sentences. resource_type/resource_id make that an index
    lookup, and make the digital return twin (Phase 53) reconstructable.

    **Hash chaining.** Each row commits to the hash of the previous row for
    the same org. Deleting or editing any historical row breaks every
    subsequent link, so tampering is detectable rather than merely
    discouraged. Append-only permissions stop an outsider; the chain also
    catches someone with legitimate database access, which is the realistic
    insider threat for an audit trail.
    """
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    # WHAT, specifically
    category: Mapped[str] = mapped_column(String(16), default="business", index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # WHERE / correlation
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6-safe
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # WHY / what changed
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Tamper evidence
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class RefreshToken(Base):
    """Refresh-token rotation ledger — enables real revocation, unlike the
    old design where issued refresh tokens lived only in the JWT itself and
    could never be invalidated server-side."""
    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class RevokedAccessToken(Base):
    """Explicit logout / forced-revocation denylist for short-lived access
    tokens. Rows are cheap to prune once expires_at passes."""
    __tablename__ = "revoked_access_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Phase 5 Models ────────────────────────────────────────────────────────────

class ConsentRecord(Base):
    """
    Proof that a user accepted the Terms and Privacy Policy.

    DPDP Act 2023 requires a Data Fiduciary to demonstrate that consent was
    obtained - not merely to assert it. That means recording WHO consented,
    to WHICH VERSION of the policy, WHEN, and from WHERE. A boolean column on
    the user row cannot do this: it is overwritten when policies change and
    keeps no history.

    Rows here are append-only. Withdrawal is a new row with granted=False,
    never a mutation of the original.
    """
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(50), default="terms_and_privacy")
    policy_version: Mapped[str] = mapped_column(String(20))
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class PasswordResetToken(Base):
    """Single-use tokens for forgot-password flow.
    Expires after 1 hour; consuming it deletes the row."""
    __tablename__ = "password_reset_tokens"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PortalSession(Base):
    """A customer's scoped access to one return, without an account.

    PHASE 31. Customers do not have ReturnIQ logins and never will — asking a
    shopper to create an account to return a t-shirt is how a portal goes
    unused, and an unused portal generates no data.

    So access is a token bound to one order, for a short window. Only the
    SHA-256 hash is stored: this is a credential, and database read access
    must not become customer-account access.

    `attempt_count` and `last_attempt_at` exist for enumeration defence.
    Lookups are the attack surface — an attacker walks order numbers hoping
    to find one whose contact detail they can guess — and the pattern of
    failed attempts is what reveals it.
    """
    __tablename__ = "portal_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    return_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("return_requests.id"), nullable=True, index=True
    )
    platform_order_id: Mapped[str] = mapped_column(String(100), index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Never store the customer's contact detail here. The order row already
    # has it, and duplicating PII into a token table means two places to
    # secure, two places to purge on a deletion request, and one more place to
    # leak from.
    client_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DecisionOverride(Base):
    """A human disagreeing with the system, recorded as data.

    PHASE 26. Overrides were already captured — as prose in `return_notes`:

        "Overridden to reject: customer has done this before"

    That is fine for audit and useless for improvement. You cannot answer
    "which predictions do humans consistently overturn?" from free text, and
    that question is the entire point of recording overrides.

    Structured here instead, with the model's output and the human's decision
    side by side. Each row is a labelled example: a case where the system was
    wrong, according to someone who could see things it could not.

    That makes this table the closest thing ReturnIQ currently has to real
    training signal — it accumulates from day one of a merchant using the
    product, without waiting for returns to reach their final outcome.
    """
    __tablename__ = "decision_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    return_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("return_requests.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))

    # What the system said, captured at override time. Storing it rather than
    # joining to the prediction means the record survives the model being
    # retrained or a prediction row being superseded -- the comparison must
    # reflect what the human actually saw.
    system_decision: Mapped[str] = mapped_column(String(40))
    system_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    system_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    system_fraud_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # What the human said.
    human_decision: Mapped[str] = mapped_column(String(40), index=True)
    # A category, not prose. Free text cannot be aggregated, and "which kind
    # of mistake does the model make most" is the question worth asking.
    reason_category: Mapped[str] = mapped_column(String(40), index=True)
    reason_detail: Mapped[str] = mapped_column(Text, default="")

    # Features as the human saw them, so a future retrain can reconstruct the
    # case without recomputing history that has since moved on.
    feature_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class AccountToken(Base):
    """Single-use, purpose-scoped tokens for invitation and email verification.

    PHASE 5. Replaces the practice of emailing a reusable temporary password.
    A temp password is a working credential: it sits in the recipient's inbox
    (and their mail provider's servers, and any backup of either) indefinitely,
    and it grants full account access to anyone who reads it. These tokens
    instead grant exactly one action, once, within a short window.

    Only a SHA-256 hash of the token is stored. If the database is ever read
    by an attacker -- a backup leak, a SQL injection, a disgruntled operator --
    stored hashes cannot be replayed as invitations. This is the same reason
    passwords are hashed, applied to a credential that is functionally
    equivalent to one.

    `purpose` is part of the lookup, not just metadata: without it, a token
    issued for email verification could be presented to the invitation
    endpoint to set a password on an account the holder does not own.
    """
    __tablename__ = "account_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)  # invitation | email_verification
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReturnNote(Base):
    """Timeline notes attached to a return — supports full audit trail."""
    __tablename__ = "return_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    return_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("return_requests.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ReturnDocument(Base):
    """Evidence attached to a return: damage photos, invoices, labels.

    PHASE 13. Evidence is the factual basis for a decision that moves money,
    and in a dispute it is what the merchant produces. Three additions make it
    usable for that:

    **content_sha256.** Proves the stored bytes are the bytes that were
    uploaded. Without it, "the customer sent us this photo" is an assertion,
    not evidence -- anyone with storage access could substitute a different
    image and no one could tell.

    **source.** Who produced this: the customer, warehouse staff, or an
    inspector. A damage photo from the customer and one from the receiving
    bay are different kinds of claim, and a fraud analyst comparing them needs
    to know which is which. `is_damage_photo` (a boolean) could not express
    it, and was also the only categorisation available.

    **evidence_type.** A taxonomy rather than one boolean, so the eventual
    computer vision work (Phase 22) can select "customer damage photos" as a
    training population instead of guessing from filenames.
    """
    __tablename__ = "return_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    return_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("return_requests.id"), index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    # Nullable since PHASE 31. Customer-supplied evidence has no staff
    # uploader — the portal is the first path where a real, legitimate row
    # genuinely has no user behind it. NULL here means "the customer", which
    # `source` states explicitly, rather than attributing the upload to
    # whichever staff account happened to be convenient.
    uploaded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # The customer's own account of what happened, when they typed rather
    # than uploaded. Kept on the evidence row so it carries the same
    # provenance, hashing and point-in-time handling as a photograph.
    customer_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(50))  # VERIFIED type, not the client's claim
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(500))
    is_damage_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Phase 13 — provenance and integrity
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="merchant", index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), default="other", index=True)
    declared_file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class WorkflowRule(Base):
    """Auto-approve / auto-reject / escalate rules defined by org admins."""
    __tablename__ = "workflow_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(30))  # auto_approve | auto_reject | escalate | assign
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class FeatureFlag(Base):
    """Per-org feature toggles — enables gradual rollout of Phase 5 features."""
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    flag_name: Mapped[str] = mapped_column(String(100), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CustomerBlacklist(Base):
    """Customers blocked from creating new returns."""
    __tablename__ = "customer_blacklist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    customer_identifier: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blacklisted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SystemSetting(Base):
    """Global system settings (super_admin only)."""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SLATracking(Base):
    """Tracks SLA compliance per return."""
    __tablename__ = "sla_tracking"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    return_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("return_requests.id"), unique=True, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    breached: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)



# ── Merged in from the COD-risk / remittance branch ──────────────────────────

class CODRiskAssessment(Base):
    """
    Pre-shipment Cash-on-Delivery risk score for an order, BEFORE it ships
    and BEFORE any return could exist. This runs earlier in the lifecycle
    than ReturnRequest/Prediction above -- those score a return that has
    already been initiated; this scores an order that hasn't shipped yet,
    so a seller can hold, confirm, or reject high-risk COD orders upfront
    instead of only reacting once they come back as an RTO.

    Rule-based on purpose (see services/cod_risk_service.py docstring):
    there is no labeled fraud/genuine outcome data for pre-shipment orders
    yet. Every row written here becomes a future training example once an
    outcome is known, same pattern as PredictionOutcome for the ML fraud
    model above.
    """
    __tablename__ = "cod_risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    platform_order_id: Mapped[str] = mapped_column(String(128), index=True)
    customer_identifier: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(200))
    delivery_address: Mapped[str] = mapped_column(Text)
    delivery_pincode: Mapped[str] = mapped_column(String(6), index=True)
    order_value_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    risk_score: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(20), index=True)  # low | medium | high
    flags: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(200))
    # None = outcome not yet known. Filled in later once the order actually
    # ships (or is held) and its real result is known -- this is what will
    # eventually let a real ML model be trained, same as PredictionOutcome.
    actual_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class CourierRemittance(Base):
    """
    One line item from a courier's remittance report: what they say they
    paid out for a given order's COD collection, matched against what the
    seller expected to receive.

    "Expected" comes from a matching CODRiskAssessment row when one exists
    (the order was scored pre-shipment) -- see cod_risk_service for that
    table. If no matching assessment is found (order was never scored, or
    predates this feature), expected_amount stays None and the row is
    marked unmatched_no_expected rather than guessed at.
    """
    __tablename__ = "courier_remittances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id"), index=True)
    platform_order_id: Mapped[str] = mapped_column(String(128), index=True)
    courier: Mapped[str] = mapped_column(String(50), index=True)
    awb_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remittance_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    remitted_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    expected_amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discrepancy_amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)  # matched | mismatch | unmatched_no_expected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
