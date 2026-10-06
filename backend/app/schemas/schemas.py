from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.money import MINOR_UNITS, Money


# ── Money ─────────────────────────────────────────────────────────────────────
class MoneyOut(BaseModel):
    """Canonical wire format for every monetary value leaving the API.

    Clients get the exact integer (`minor_units`) for arithmetic and a
    pre-rendered string (`formatted`) for display, so no frontend has to
    reimplement ISO-4217 exponents or Indian digit grouping. `amount` is the
    decimal string for exports and accounting systems.
    """
    minor_units: int
    currency: str
    amount: str
    formatted: str

    @classmethod
    def of(cls, minor_units: int | None, currency: str = "INR") -> "MoneyOut":
        return cls(**Money(int(minor_units or 0), currency).as_dict())


class MoneyIn(BaseModel):
    """Money arriving from a client.

    Decimal, never float -- Pydantic would happily coerce 19.99 into a float
    and lose precision before validation even runs. Callers send major units
    ("1500.50") plus an explicit currency; conversion to minor units happens
    once, at this boundary.
    """
    amount: Decimal = Field(..., description="Major units, e.g. '1500.50'")
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_scalar(cls, data):
        """Accept a bare number as well as the full object.

        Phase 3 changed this field's shape. Merchants with live integrations
        are still POSTing `"order_value": 800`, and returning 422 to them
        would be an outage we caused. A bare scalar is interpreted as major
        units in the org's default currency (INR).

        Note the str() -- routing a JSON float through Decimal(str(x)) keeps
        800.99 as "800.99" instead of 800.9899999999999. Deprecate this path
        once clients have migrated; do not remove it before then.
        """
        if isinstance(data, (int, float, str, Decimal)):
            return {"amount": Decimal(str(data)), "currency": "INR"}
        return data

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, v: str) -> str:
        up = v.upper()
        if up not in MINOR_UNITS:
            raise ValueError(
                f"Unsupported currency {v!r}. Supported: {', '.join(sorted(MINOR_UNITS))}"
            )
        return up

    def to_money(self) -> Money:
        return Money.from_major(self.amount, self.currency)


# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    org_name: str = Field(..., min_length=2, max_length=255)
    platform_type: str = Field(default="shopify")
    # DPDP Act 2023 (s.5-6) requires consent to be free, specific, informed and
    # unambiguous, and requires the Data Fiduciary to be able to PROVE it was
    # given. A silent default would satisfy none of that - the field is
    # required and must be explicitly true.
    accepted_terms: bool = Field(
        ..., description="Must be true. Records acceptance of the Terms of Service and Privacy Policy."
    )
    policy_version: str = Field(
        default="1.0", max_length=20,
        description="Version of the Terms/Privacy Policy shown to the user at registration.",
    )

    @field_validator("accepted_terms")
    @classmethod
    def must_accept(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "You must accept the Terms of Service and Privacy Policy to register."
            )
        return v

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ── Organization ──────────────────────────────────────────────────────────────
class OrgSettingsUpdate(BaseModel):
    risk_threshold: Optional[float] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    auto_approve_below_risk: Optional[float] = None
    notify_on_fraud: Optional[bool] = None
    webhook_url: Optional[str] = None


# ── Return Request ────────────────────────────────────────────────────────────
class ReturnRequestCreate(BaseModel):
    platform_order_id: str = Field(..., max_length=128)
    customer_identifier: str = Field(..., max_length=64)
    sku: str = Field(..., max_length=128)
    item_category: str = Field(..., max_length=100)
    # Decimal, not float: Pydantic would coerce 1499.99 to a float and lose
    # precision before validation runs. Currency defaults to INR so existing
    # API clients keep working unchanged (Phase 3 backward compatibility).
    item_value: Decimal = Field(..., ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _known_currency_rr(cls, v: str) -> str:
        up = v.upper()
        if up not in MINOR_UNITS:
            raise ValueError(f"Unsupported currency {v!r}")
        return up

    origin_pincode: str = Field(..., min_length=6, max_length=6)
    destination_pincode: str = Field(..., min_length=6, max_length=6)

    weight_grams: int = Field(..., gt=0)
    volumetric_weight_grams: int = Field(..., gt=0)

    return_reason_code: str = Field(..., max_length=50)
    courier: str = Field(..., max_length=50)
    payment_mode: str = Field(..., max_length=20)
    fragile: bool = False
    festive: bool = False
    condition: Optional[str] = "good"
    customer_notes: Optional[str] = Field(None, max_length=500)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("origin_pincode", "destination_pincode")
    @classmethod
    def pincode_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Pincode must be 6 numeric digits")
        return v

    @field_validator("payment_mode")
    @classmethod
    def valid_payment_mode(cls, v: str) -> str:
        allowed = {"Prepaid", "COD"}
        if v not in allowed:
            raise ValueError(f"payment_mode must be one of {allowed}")
        return v


class ReturnStatusUpdate(BaseModel):
    """PHASE 12: status was `str` with no validation, so `{"status": "banana"}`
    returned 200 and was stored. Free-text status also silently breaks
    reporting -- reports group by it, workflow rules match on it, the
    dashboard counts it -- so one typo in one integration creates a status
    nobody queries, and those returns vanish from every view while still
    existing in the database.

    Whether the *transition* is legal is checked in the route, not here: the
    schema cannot see the return's current status.
    """
    status: str
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        from app.core.lifecycle import ALL_STATUSES
        value = v.strip().lower()
        if value not in ALL_STATUSES:
            raise ValueError(
                f"{v!r} is not a return status. "
                f"Valid: {', '.join(sorted(ALL_STATUSES))}"
            )
        return value


# ── Pagination ─────────────────────────────────────────────────────────────────
class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── API Keys ──────────────────────────────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=100)


# ── Customers ─────────────────────────────────────────────────────────────────
class CustomerCreate(BaseModel):
    name: str = Field(..., max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    city: Optional[str] = None


# ── Prediction outcomes (ground-truth labels, Phase 4.7/4.8 groundwork) ────────
_VALID_DAMAGE_GRADES = {"none", "minor", "major", "total_loss"}


class PredictionOutcomeSubmit(BaseModel):
    actual_fraud_confirmed: Optional[bool] = None
    actual_damage_grade: Optional[str] = None
    actual_cost: Optional[MoneyIn] = None
    actual_resale_price: Optional[MoneyIn] = None
    notes: Optional[str] = None

    @field_validator("actual_damage_grade")
    @classmethod
    def _validate_damage_grade(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_DAMAGE_GRADES:
            raise ValueError(f"actual_damage_grade must be one of {sorted(_VALID_DAMAGE_GRADES)}")
        return v


# ── Phase 5: User Profile ──────────────────────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── Phase 5: Org / Members ────────────────────────────────────────────────────
class AcceptInvitationRequest(BaseModel):
    """PHASE 5: the invitee sets their own password using a single-use token."""
    token: str = Field(..., min_length=20, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=128)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    role: str = Field(default="analyst")

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        allowed = {"org_admin", "analyst", "warehouse_staff", "viewer"}
        if v not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v


class UpdateMemberRoleRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        allowed = {"org_admin", "analyst", "warehouse_staff", "viewer"}
        if v not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v


class OrgBrandingUpdate(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    company_website: Optional[str] = None


# ── Phase 5: Notifications ────────────────────────────────────────────────────
class NotificationMarkRead(BaseModel):
    notification_ids: list[str]


# ── Phase 5: Workflow Rules ───────────────────────────────────────────────────
class WorkflowRuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    rule_type: str  # auto_approve | auto_reject | escalate | assign
    conditions: dict[str, Any]  # e.g. {"risk_score_lt": 20, "item_value_lt": 500}
    action: dict[str, Any]  # e.g. {"status": "approved", "notify": True}
    priority: int = Field(default=0, ge=0)
    is_active: bool = True


class WorkflowRuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[dict[str, Any]] = None
    action: Optional[dict[str, Any]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


# ── Phase 5: Admin ────────────────────────────────────────────────────────────
class FeatureFlagUpdate(BaseModel):
    enabled: bool


class SystemSettingUpdate(BaseModel):
    value: Any


# ── Phase 5: Reporting ────────────────────────────────────────────────────────
class ReportRequest(BaseModel):
    report_type: str  # summary | fraud | carbon | customer
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    format: str = Field(default="json")  # json | csv


# ── Phase 5: Return management extensions ─────────────────────────────────────
class ReturnNoteAdd(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)


class BulkReturnImport(BaseModel):
    returns: list[ReturnRequestCreate]


# ── Phase 5: Customer extensions ──────────────────────────────────────────────
class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = None
    city: Optional[str] = None
    risk_level: Optional[str] = None
    is_blacklisted: Optional[bool] = None


class CustomerNote(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)


# ── COD risk & remittance schemas (merged from the feature branch) ───────────

class CODRiskFlagOut(BaseModel):
    code: str
    description: str
    points: float


class CODRiskScoreRequest(BaseModel):
    """What a seller's order-management system sends us right before shipping."""
    platform_order_id: str = Field(..., min_length=1, max_length=128)
    customer_phone: str = Field(..., min_length=6, max_length=20)
    customer_name: str = Field(..., min_length=1, max_length=200)
    delivery_address: str = Field(..., min_length=1)
    delivery_pincode: str = Field(..., min_length=6, max_length=6)
    order_value: MoneyIn

    @field_validator("delivery_pincode")
    @classmethod
    def pincode_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("delivery_pincode must be 6 digits")
        return v


class CODRiskScoreResponse(BaseModel):
    assessment_id: str
    platform_order_id: str
    risk_score: float
    risk_band: str
    flags: list[CODRiskFlagOut]
    recommendation: str


# ── Courier Remittance Reconciliation ──────────────────────────────────────────


class RemittanceLineIn(BaseModel):
    """One row of a courier's remittance report."""
    platform_order_id: str = Field(..., min_length=1, max_length=128)
    courier: str = Field(..., max_length=50)
    awb_number: Optional[str] = Field(None, max_length=64)
    remittance_date: str = Field(..., description="YYYY-MM-DD")
    remitted_amount: MoneyIn


class RemittanceLineOut(BaseModel):
    id: str
    platform_order_id: str
    courier: str
    awb_number: Optional[str]
    remittance_date: str
    remitted_amount: MoneyOut
    expected_amount: Optional[MoneyOut]
    discrepancy_amount: Optional[MoneyOut]
    status: str


class RemittanceIngestRequest(BaseModel):
    lines: list[RemittanceLineIn] = Field(..., min_length=1, max_length=5000)


class RemittanceIngestResponse(BaseModel):
    total_lines: int
    matched: int
    mismatched: int
    unmatched_no_expected: int
    results: list[RemittanceLineOut]


class RemittanceSummaryByCourier(BaseModel):
    courier: str
    total_expected: float
    total_remitted: float
    total_discrepancy: float
    mismatch_count: int
    unmatched_count: int


class RemittanceSummaryResponse(BaseModel):
    by_courier: list[RemittanceSummaryByCourier]
    total_expected: float
    total_remitted: float
    total_discrepancy: float
