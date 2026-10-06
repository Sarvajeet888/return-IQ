"""
Enterprise AI/ML Service — multi-model platform built on top of the original XGBoost predictor.
Adds: fraud detection, damage scoring, resale estimation, carbon footprint, confidence scoring.
"""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from app.core.tracing import span
from app.ml.explainability import explain_rule_score
from app.services import intelligence_engine
from app.models.enums import RoutingDecision


@lru_cache(maxsize=1)
def get_predictor():
    from ml.predict import ReverseLogisticsPredictor
    return ReverseLogisticsPredictor()


# ── Original routing logic preserved exactly ──────────────────────────────────
def _derive_routing(
    risk_score: float, predicted_cost: float,
    item_value: float, risk_threshold: float,
    fraud_score: float,
) -> RoutingDecision:
    if fraud_score >= 75:
        return RoutingDecision.REJECT
    if risk_score >= risk_threshold:
        return RoutingDecision.REJECT
    if predicted_cost > item_value * 0.6:
        return RoutingDecision.REFUND_AND_KEEP
    if risk_score >= risk_threshold * 0.6:
        return RoutingDecision.CHARGE_RETURN_FEE
    return RoutingDecision.ACCEPT


# ── Fraud Detection Model (rule-based + heuristic, production would be separate model) ──
def _compute_fraud_score(  # -> (score, fired_rules)
    customer_return_rate: float,
    payment_mode: str,
    return_reason: str,
    item_value: float,
    fragile: bool,
    festive: bool,
) -> float:
    # PHASE 21: each rule records what it contributed and why.
    #
    # This score is arithmetic we wrote, so it can be explained EXACTLY --
    # every point accounted for. It was previously surfaced with the same
    # approximate model-attribution treatment as the ML cost prediction,
    # which gave up a perfect explanation in favour of a vague one.
    fired: list[tuple[str, float, str]] = []
    score = 0.0

    if customer_return_rate > 0.4:
        score += 35
        fired.append(("Customer return history", 35,
                      f"This customer returns {customer_return_rate:.0%} of orders (above 40%)"))
    elif customer_return_rate > 0.25:
        score += 20
        fired.append(("Customer return history", 20,
                      f"This customer returns {customer_return_rate:.0%} of orders (above 25%)"))

    if payment_mode == "COD":
        score += 15
        fired.append(("Payment method", 15, "Paid cash on delivery"))

    if return_reason in ("not_as_described", "wrong_item"):
        score += 10
        fired.append(("Return reason", 10, f"Reason given: {return_reason}"))

    if festive:
        score += 8
        fired.append(("Festive period", 8, "Ordered during a festive sales window"))

    if item_value > 5000 and return_reason == "change_of_mind":
        score += 20
        fired.append(("High-value change of mind", 20,
                      f"Item over Rs 5,000 returned as change of mind"))

    if customer_return_rate > 0.5 and item_value > 3000:
        score += 15
        fired.append(("High-value frequent returner", 15,
                      f"Return rate above 50% combined with an item over Rs 3,000"))

    final = round(min(score, 100), 2)

    # If the cap bit, say so rather than leaving the parts summing to more
    # than the whole -- a silent remainder makes an explanation look complete
    # when it is not.
    if score > 100:
        fired.append(("Score capped at 100", 100 - score,
                      f"Rules totalled {score:.0f}; the score is capped at 100"))

    return final, fired


# ── Damage Detection (heuristic — production uses CV model) ──
def _compute_damage_probability(return_reason: str, condition: str | None, fragile: bool) -> float:
    base = 0.0
    if return_reason == "damaged":
        base = 0.85
    elif return_reason == "defective":
        base = 0.70
    elif return_reason == "quality_issue":
        base = 0.45
    elif return_reason == "not_as_described":
        base = 0.20
    else:
        base = 0.10

    if condition == "damaged":
        base = max(base, 0.80)
    elif condition == "fair":
        base = max(base, 0.30)

    if fragile:
        base = min(base + 0.10, 1.0)

    return round(base, 3)


_CATEGORY_DEPRECIATION = {
    "Electronics": 0.80,
    "Fashion": 0.70,
    "Beauty": 0.55,
    "Sports": 0.85,
    "Home": 0.90,
    "Books": 0.95,
}


def _estimate_resale_value(item_value: float, damage_prob: float, condition: str | None, category: str | None = None) -> float:
    multiplier = 0.7
    if condition == "unopened":
        multiplier = 0.90
    elif condition == "like_new":
        multiplier = 0.80
    elif condition == "good":
        multiplier = 0.65
    elif condition == "fair":
        multiplier = 0.40
    elif condition == "damaged":
        multiplier = 0.15
    multiplier *= (1 - damage_prob * 0.5)
    multiplier *= _CATEGORY_DEPRECIATION.get(category, 0.75)
    return round(item_value * max(multiplier, 0.05), 2)


_COURIER_EMISSION_FACTOR = {
    "BlueDart": 0.00028,
    "Delhivery": 0.00021,
    "DTDC": 0.00021,
    "Ekart": 0.00019,
    "Shadowfax": 0.00019,
    "Xpressbees": 0.00021,
}
_DEFAULT_EMISSION_FACTOR = 0.00021


def _compute_carbon_footprint(distance_km: int, weight_kg: float, courier: str) -> float:
    factor = _COURIER_EMISSION_FACTOR.get(courier, _DEFAULT_EMISSION_FACTOR)
    return round(distance_km * weight_kg * factor, 3)


# ── Main scoring function — ENHANCED original ─────────────────────────────────
# Ceiling on any confidence this system reports, while the cost model is
# trained on synthetic data. Raise it only when predictions have been measured
# against real returns -- and change this constant, not the call site, so the
# reason stays attached to the number.
_MODEL_CONFIDENCE_CEILING: float = 0.35


def score_return(features: dict, item_value: float, risk_threshold: float, condition: str | None = "good") -> dict:
    predictor = get_predictor()
    # PHASE 9: ML inference is the most likely cause of a slow scoring
    # request, and the one hardest to guess at from an access log.
    with span("ml.inference", model=getattr(predictor, "model_version", "unknown")):
        result = predictor.predict_with_explanation(features)
    predicted_cost = result["predicted_cost_inr"]
    top_drivers = result["top_drivers"]
    latency_ms = result["inference_latency_ms"]

    # Original risk score logic preserved
    cost_to_value_ratio = min(predicted_cost / max(item_value, 1), 1.0)
    customer_return_rate = features.get("customer_return_rate", 0)
    merchant_return_rate = features.get("merchant_return_rate", 0)
    risk_score = round(min(max(
        cost_to_value_ratio * 40
        + customer_return_rate * 100 * 0.35
        + merchant_return_rate * 100 * 0.10,
        0
    ), 100), 2)

    # NEW: extended AI scores
    fraud_score, fraud_contributions = _compute_fraud_score(
        customer_return_rate=customer_return_rate,
        payment_mode=features.get("payment_mode", "Prepaid"),
        return_reason=features.get("return_reason", ""),
        item_value=item_value,
        fragile=bool(features.get("fragile", 0)),
        festive=bool(features.get("festive", 0)),
    )

    damage_prob = _compute_damage_probability(
        return_reason=features.get("return_reason", ""),
        condition=condition,
        fragile=bool(features.get("fragile", 0)),
    )

    resale_value = _estimate_resale_value(item_value, damage_prob, condition, category=features.get("category"))

    carbon = _compute_carbon_footprint(
        distance_km=features.get("distance_km", 100),
        weight_kg=features.get("chargeable_weight", 0.5),
        courier=features.get("courier", ""),
    )

    # PHASE 14 — confidence.
    #
    # This previously read:
    #   confidence = min(0.85 + (risk_score < 80)*0.1 + (item_value < 5000)*0.04, 0.99)
    # with the comment "based on model R2=0.999".
    #
    # Three problems. It never consulted the model. It could take only four
    # values, with a cliff at item_value 5000 that means nothing (Rs 4,999
    # reported 0.99, Rs 5,001 reported 0.95). And the R2 it invoked comes from
    # a model trained on synthetic data whose labels derive from the
    # generator's own parameters -- see data/DATASET_ASSESSMENT.md.
    #
    # Reporting 0.99 on that basis is the most misleading number the system
    # produces, because confidence is precisely what a merchant uses to decide
    # whether to trust everything else.
    #
    # Until predictions are validated against real outcomes (Phase 19/27), the
    # honest ceiling is low. It is exposed as a numeric field only because
    # existing API clients and the database column expect a float; the
    # meaningful version is the banded, per-signal confidence in the
    # intelligence report.
    confidence = _MODEL_CONFIDENCE_CEILING

    routing_decision = _derive_routing(
        risk_score=risk_score,
        predicted_cost=predicted_cost,
        item_value=item_value,
        risk_threshold=risk_threshold,
        fraud_score=fraud_score,
    )

    return {
        "predicted_cost_inr": Decimal(str(predicted_cost)),
        "risk_score": Decimal(str(risk_score)),
        "fraud_score": Decimal(str(fraud_score)),
        "damage_probability": damage_prob,
        "resale_value_estimate": Decimal(str(resale_value)),
        "carbon_footprint_kg": carbon,
        "confidence_score": confidence,
        "routing_decision": routing_decision,
        "model_version": predictor.metadata.get("model_version", "unknown"),
        "inference_latency_ms": round(latency_ms, 3),
        # PHASE 14: per-signal provenance and confidence, alongside the flat
        # values. Additive, so every existing caller keeps working.
        # PHASE 21: exact, reconciling explanation for the rule-based fraud
        # score. Not an approximation -- these contributions sum to the score.
        "fraud_explanation": explain_rule_score(
            "fraud_score", fraud_score, baseline=0.0, fired=fraud_contributions,
        ).as_dict(),
        "intelligence": intelligence_engine.build_report({
            "predicted_cost_inr": predicted_cost,
            "fraud_score": fraud_score,
            "damage_probability": damage_prob,
            "resale_value_estimate": resale_value,
            "carbon_footprint_kg": carbon,
            "risk_score": risk_score,
            "model_version": predictor.metadata.get("model_version", "unknown"),
        }).as_dict(),
        "feature_snapshot": features,
        "explainability": {
            "top_cost_drivers": top_drivers,
            "method": "xgboost_importance_weighted",
            "risk_factors": [
                f for f, v in [
                    ("High customer return rate", customer_return_rate > 0.3),
                    ("COD payment", features.get("payment_mode") == "COD"),
                    ("Festive season surge", bool(features.get("festive"))),
                    ("Fragile item", bool(features.get("fragile"))),
                    ("Long distance shipment", features.get("distance_km", 0) > 800),
                ] if v
            ]
        }
    }


def get_model_stats() -> dict:
    p = get_predictor()
    return {
        **p.stats,
        "models_active": ["cost_prediction", "fraud_detection", "damage_assessment",
                          "resale_estimation", "carbon_footprint"],
        "models_real_ml": ["cost_prediction"],
        "models_rule_based": ["fraud_detection", "damage_assessment",
                              "resale_estimation", "carbon_footprint"],
    }
