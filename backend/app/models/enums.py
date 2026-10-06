from __future__ import annotations

import enum


# ── Auth / Users ──────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    WAREHOUSE_MANAGER = "warehouse_manager"
    INVENTORY_MANAGER = "inventory_manager"
    FINANCE = "finance"
    SUPPORT = "support"
    COURIER = "courier"
    EMPLOYEE = "employee"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


# ── Organization ──────────────────────────────────────────────────────────────
class PlanTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class PlatformType(str, enum.Enum):
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"
    MAGENTO = "magento"
    UNICOMMERCE = "unicommerce"
    CUSTOM = "custom"
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    MEESHO = "meesho"


# ── Returns ───────────────────────────────────────────────────────────────────
class ReturnStatus(str, enum.Enum):
    INITIATED = "initiated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    INSPECTED = "inspected"
    REFUNDED = "refunded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RoutingDecision(str, enum.Enum):
    ACCEPT = "accept"
    CHARGE_RETURN_FEE = "charge_return_fee"
    REFUND_AND_KEEP = "refund_and_keep"
    REJECT = "reject"
    ESCALATE = "escalate"
    MANUAL_REVIEW = "manual_review"


class ReturnCondition(str, enum.Enum):
    UNOPENED = "unopened"
    LIKE_NEW = "like_new"
    GOOD = "good"
    FAIR = "fair"
    DAMAGED = "damaged"
    UNUSABLE = "unusable"


# ── Warehouse / Inventory ─────────────────────────────────────────────────────
class WarehouseZoneType(str, enum.Enum):
    RECEIVING = "receiving"
    INSPECTION = "inspection"
    STORAGE = "storage"
    REFURBISHMENT = "refurbishment"
    DISPOSAL = "disposal"
    DISPATCH = "dispatch"


class InventoryDisposition(str, enum.Enum):
    RESELL = "resell"
    REFURBISH = "refurbish"
    DONATE = "donate"
    RECYCLE = "recycle"
    DESTROY = "destroy"
    RETURN_TO_VENDOR = "return_to_vendor"


# ── Payments ─────────────────────────────────────────────────────────────────
class PaymentMode(str, enum.Enum):
    PREPAID = "Prepaid"
    COD = "COD"
    WALLET = "wallet"
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"


class RefundStatus(str, enum.Enum):
    PENDING = "pending"
    INITIATED = "initiated"
    PROCESSED = "processed"
    FAILED = "failed"
    REVERSED = "reversed"


# ── Notifications ─────────────────────────────────────────────────────────────
class NotificationType(str, enum.Enum):
    RETURN_APPROVED = "return_approved"
    RETURN_REJECTED = "return_rejected"
    RETURN_RECEIVED = "return_received"
    REFUND_INITIATED = "refund_initiated"
    FRAUD_ALERT = "fraud_alert"
    SYSTEM_ALERT = "system_alert"
    WEEKLY_REPORT = "weekly_report"


# ── Audit ─────────────────────────────────────────────────────────────────────
class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    API_KEY_GENERATED = "api_key_generated"
    PERMISSION_CHANGE = "permission_change"
    BULK_ACTION = "bulk_action"
