"""
COD Risk Service — pre-shipment fraud/RTO scoring.

Scores a Cash-on-Delivery order BEFORE it ships, so a seller can hold,
call to confirm, or ship as normal. This runs earlier in the order
lifecycle than ml_service.score_return() above: that function scores a
RETURN after it's already been initiated; this scores an ORDER before it
has even shipped, using signals that predict whether it'll become a
fraud/RTO case at all.

Deliberately rule-based, not ML, for the same reason PredictionOutcome
exists for the return-fraud model: there is no labeled pre-shipment
outcome data yet. Every assessment this writes to cod_risk_assessments
becomes a future training example once ml/train_fraud_model.py (or an
equivalent) has enough labeled rows to train on -- see actual_outcome on
the CODRiskAssessment model.
"""
from __future__ import annotations

from decimal import Decimal

from app.core.money import Money
from app.db import store

# Tunable weights. Treat these as a business decision, not just an
# engineering one -- review with the team before changing in production.
WEIGHT_EXISTING_CUSTOMER_RISK = {"low": 0.0, "medium": 20.0, "high": 40.0}
WEIGHT_REPEAT_RETURNS_PER_INCIDENT = 8.0
WEIGHT_REPEAT_RETURNS_CAP = 30.0
WEIGHT_HIGH_RISK_PINCODE = 25.0
WEIGHT_NEW_CUSTOMER_HIGH_VALUE = 20.0
WEIGHT_VALUE_SPIKE_VS_AVERAGE = 15.0
WEIGHT_SHARED_ADDRESS_MULTIPLE_NAMES = 25.0
WEIGHT_COMPOUNDING_BONUS = 15.0

NEW_CUSTOMER_HIGH_VALUE_THRESHOLD_INR = 2000.0
VALUE_SPIKE_MULTIPLIER = 3.0
SHARED_ADDRESS_NAME_THRESHOLD = 2

LOW_BAND_MAX = 30.0
MEDIUM_BAND_MAX = 60.0

# A pincode is judged high-risk from THIS ORG'S OWN real return history --
# actual fraud_score values already computed by ml_service for past returns
# shipped there -- never a hardcoded/guessed list. PINCODE_MIN_SAMPLE_SIZE
# guards against judging a pincode risky off just one or two returns.
PINCODE_MIN_SAMPLE_SIZE = 3
PINCODE_HIGH_RISK_FRAUD_SCORE_THRESHOLD = 40.0


def _threshold(major_inr: float, currency: str) -> Money:
    """Business thresholds are configured in major units.

    They are currently INR-denominated constants; when a non-INR org appears
    these must become per-org configuration (Phase 32) rather than a silently
    converted number. Converting at the comparison keeps that decision visible
    instead of burying an implicit FX assumption in a constant.
    """
    return Money.from_major(f"{major_inr:.2f}", currency)


def score_cod_order(
    org_id: str,
    platform_order_id: str,
    customer_phone: str,
    customer_name: str,
    delivery_address: str,
    delivery_pincode: str,
    order_value: Money,
) -> dict:
    flags: list[dict] = []

    existing_customer = store.get_customer_by_phone(org_id, customer_phone)

    # Blacklisted is a hard override, decided elsewhere in ReturnIQ by a
    # human -- it should never be diluted into "medium, maybe ship it" just
    # because other signals happen to be low. Short-circuit immediately.
    if existing_customer and existing_customer.get("is_blacklisted"):
        flags = [{
            "code": "CUSTOMER_BLACKLISTED",
            "description": "This customer is blacklisted in ReturnIQ.",
            "points": 100.0,
        }]
        assessment = store.create_cod_risk_assessment({
            "org_id": org_id,
            "platform_order_id": platform_order_id,
            "customer_identifier": customer_phone,
            "customer_name": customer_name,
            "delivery_address": delivery_address,
            "delivery_pincode": delivery_pincode,
            "order_value_minor": order_value.minor_units,
            "currency": order_value.currency,
            "risk_score": 100.0,
            "risk_band": "high",
            "flags": flags,
            "recommendation": "Hold for manual review before shipping.",
        })
        return {
            "assessment_id": assessment["id"],
            "platform_order_id": platform_order_id,
            "risk_score": 100.0,
            "risk_band": "high",
            "flags": flags,
            "recommendation": "Hold for manual review before shipping.",
        }

    # --- Rule 1: reuse this customer's EXISTING risk profile, if any -----
    # ReturnIQ already tracks risk_level per customer from their return
    # history -- no need to recompute that here. (Blacklist is already
    # handled above as a hard override, so we won't reach this branch for
    # a blacklisted customer.)
    if existing_customer:
        existing_risk = existing_customer.get("risk_level", "low")
        pts = WEIGHT_EXISTING_CUSTOMER_RISK.get(existing_risk, 0.0)
        if pts > 0:
            flags.append({
                "code": "EXISTING_CUSTOMER_RISK_LEVEL",
                "description": f"Customer's existing ReturnIQ risk level is '{existing_risk}'.",
                "points": pts,
            })

        total_returns = existing_customer.get("total_returns", 0) or 0
        if total_returns > 0:
            pts = min(total_returns * WEIGHT_REPEAT_RETURNS_PER_INCIDENT, WEIGHT_REPEAT_RETURNS_CAP)
            flags.append({
                "code": "REPEAT_RETURN_HISTORY",
                "description": f"Customer has {total_returns} past return(s) on record.",
                "points": pts,
            })

    # --- Rule 2: pincode has a real history of high-fraud-score returns ---
    # Computed from this org's own past returns to this exact pincode --
    # never a hardcoded list. Requires a minimum sample size so a pincode
    # with just 1-2 past returns doesn't get judged off noise.
    pincode_stats = store.get_pincode_fraud_stats(org_id, delivery_pincode)
    if (
        pincode_stats["sample_count"] >= PINCODE_MIN_SAMPLE_SIZE
        and pincode_stats["avg_fraud_score"] >= PINCODE_HIGH_RISK_FRAUD_SCORE_THRESHOLD
    ):
        flags.append({
            "code": "HIGH_RISK_PINCODE",
            "description": (
                f"Pincode {delivery_pincode} has an average fraud score of "
                f"{pincode_stats['avg_fraud_score']:.0f}/100 across "
                f"{pincode_stats['sample_count']} past returns for this org."
            ),
            "points": WEIGHT_HIGH_RISK_PINCODE,
        })

    # --- Rule 3: brand-new customer + high-value COD ---------------------
    if not existing_customer and order_value >= _threshold(
            NEW_CUSTOMER_HIGH_VALUE_THRESHOLD_INR, order_value.currency):
        flags.append({
            "code": "NEW_CUSTOMER_HIGH_VALUE_COD",
            "description": (
                f"First-time customer placing a COD order of {order_value.format()}, "
                f"above the \u20b9{NEW_CUSTOMER_HIGH_VALUE_THRESHOLD_INR:.0f} threshold."
            ),
            "points": WEIGHT_NEW_CUSTOMER_HIGH_VALUE,
        })

    # --- Rule 4: order value is a big spike vs this customer's usual CLV --
    if existing_customer:
        clv = Money(int(existing_customer.get("clv_minor") or 0),
                    existing_customer.get("currency") or order_value.currency)
        total_orders = existing_customer.get("total_orders", 0) or 0
        if total_orders > 0 and clv > 0:
            # Integer division on paise: an average is a derived figure, and
            # rounding it down by at most one paisa cannot flip a 3x spike test.
            avg_order_value = Money(clv.minor_units // total_orders, clv.currency)
            if not avg_order_value.is_zero() and order_value >= avg_order_value * Decimal(str(VALUE_SPIKE_MULTIPLIER)):
                flags.append({
                    "code": "ORDER_VALUE_SPIKE",
                    "description": (
                        f"Order value {order_value.format()} is over {VALUE_SPIKE_MULTIPLIER:.0f}x "
                        f"this customer's average ({avg_order_value.format()})."
                    ),
                    "points": WEIGHT_VALUE_SPIKE_VS_AVERAGE,
                })

    # --- Rule 5: same delivery address, multiple different customer names
    recent_names = store.get_recent_names_at_address(org_id, delivery_address)
    distinct_names = set(recent_names) | {customer_name}
    if len(distinct_names) >= SHARED_ADDRESS_NAME_THRESHOLD:
        flags.append({
            "code": "SHARED_ADDRESS_MULTIPLE_NAMES",
            "description": (
                f"{len(distinct_names)} different customer names have ordered to "
                f"this same address -- possible fraud ring."
            ),
            "points": WEIGHT_SHARED_ADDRESS_MULTIPLE_NAMES,
        })

    # --- Rule 6: compounding -- multiple independent signals together ----
    if len(flags) >= 2:
        flags.append({
            "code": "MULTIPLE_SIGNALS_COMPOUNDING",
            "description": f"{len(flags)} independent risk signals triggered together on the same order.",
            "points": WEIGHT_COMPOUNDING_BONUS,
        })

    risk_score = min(sum(f["points"] for f in flags), 100.0)

    if risk_score <= LOW_BAND_MAX:
        risk_band, recommendation = "low", "Ship as normal."
    elif risk_score < MEDIUM_BAND_MAX:
        risk_band, recommendation = "medium", "Consider a confirmation call before shipping."
    else:
        risk_band, recommendation = "high", "Hold for manual review before shipping."

    assessment = store.create_cod_risk_assessment({
        "org_id": org_id,
        "platform_order_id": platform_order_id,
        "customer_identifier": customer_phone,
        "customer_name": customer_name,
        "delivery_address": delivery_address,
        "delivery_pincode": delivery_pincode,
        "order_value_minor": order_value.minor_units,
            "currency": order_value.currency,
        "risk_score": risk_score,
        "risk_band": risk_band,
        "flags": flags,
        "recommendation": recommendation,
    })

    return {
        "assessment_id": assessment["id"],
        "platform_order_id": platform_order_id,
        "risk_score": risk_score,
        "risk_band": risk_band,
        "flags": flags,
        "recommendation": recommendation,
    }
