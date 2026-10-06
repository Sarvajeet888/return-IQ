"""
Feature mapping — converts incoming API fields to the exact values
the XGBoost model was trained on.

Model training vocabulary (do NOT change):
  courier      : BlueDart, DTDC, Delhivery, Ekart, Shadowfax, Xpressbees
  category     : Beauty, Books, Electronics, Fashion, Home, Sports
  payment_mode : COD, Prepaid
  return_reason: Changed Mind, Damaged, Quality Issue, Wrong Item, Wrong Size
"""
from __future__ import annotations

_METRO_PREFIXES = {"11", "12", "40", "56", "60", "70", "50", "38"}

# ── Value normalisation maps ──────────────────────────────────────────────────
# Maps API input → exact model training label

COURIER_MAP: dict[str, str] = {
    "bluedart":    "BlueDart",
    "blue dart":   "BlueDart",
    "delhivery":   "Delhivery",
    "dtdc":        "DTDC",
    "ekart":       "Ekart",
    "xpressbees":  "Xpressbees",
    "xpress bees": "Xpressbees",
    "shadowfax":   "Shadowfax",
    # unknowns → empty string (OHE all-zeros = "other")
}

CATEGORY_MAP: dict[str, str] = {
    "apparel":     "Fashion",
    "fashion":     "Fashion",
    "clothing":    "Fashion",
    "footwear":    "Fashion",
    "accessories": "Fashion",
    "electronics": "Electronics",
    "mobile":      "Electronics",
    "laptop":      "Electronics",
    "books":       "Books",
    "beauty":      "Beauty",
    "cosmetics":   "Beauty",
    "sports":      "Sports",
    "fitness":     "Sports",
    "furniture":   "Home",
    "home":        "Home",
    "kitchen":     "Home",
    "grocery":     "Home",
    "toys":        "Home",
}

REASON_MAP: dict[str, str] = {
    "size_issue":        "Wrong Size",
    "size issue":        "Wrong Size",
    "wrong_item":        "Wrong Item",
    "wrong item":        "Wrong Item",
    "damaged":           "Damaged",
    "defective":         "Damaged",
    "quality_issue":     "Quality Issue",
    "quality issue":     "Quality Issue",
    "not_as_described":  "Wrong Item",
    "not as described":  "Wrong Item",
    "change_of_mind":    "Changed Mind",
    "change of mind":    "Changed Mind",
    "changed mind":      "Changed Mind",
}

PAYMENT_MAP: dict[str, str] = {
    "prepaid": "Prepaid",
    "cod":     "COD",
    "cash on delivery": "COD",
}


def _normalise(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(value.lower().strip(), "")


def check_unmapped_features(return_data: dict) -> list[str]:
    """
    Report which categorical inputs could not be mapped to the model's
    training vocabulary (Phase 9.7).

    Why this matters: _normalise() returns "" for anything it doesn't
    recognise, and the OneHotEncoder turns "" into an all-zeros row. The
    model still returns a number, so nothing looks broken - but that
    prediction was made with a missing feature and is quietly less accurate.

    Before this check, a caller sending courier="FedEx" (not one of the six
    couriers the model knows) got a confident-looking prediction with no
    indication that a feature had been dropped. Now the caller is told.

    Returns a list of human-readable warnings; empty means everything mapped.
    """
    warnings: list[str] = []

    checks = [
        ("courier", return_data.get("courier"), COURIER_MAP,
         "BlueDart, Delhivery, DTDC, Ekart, Xpressbees, Shadowfax"),
        ("item_category", return_data.get("item_category"), CATEGORY_MAP,
         "Electronics, Fashion, Home, Beauty, Books, Sports"),
        ("return_reason_code", return_data.get("return_reason_code"), REASON_MAP,
         "damaged, defective, wrong_item, size_issue, quality_issue, change_of_mind"),
        ("payment_mode", return_data.get("payment_mode"), PAYMENT_MAP,
         "Prepaid, COD"),
    ]

    for field, raw, mapping, known in checks:
        if raw and _normalise(str(raw), mapping) == "":
            warnings.append(
                f"'{raw}' is not a recognised {field}; this feature was dropped "
                f"from the prediction, which reduces its accuracy. "
                f"Known values: {known}."
            )

    return warnings


def _pincode_tier(pincode: str) -> int:
    return 1 if pincode[:2] in _METRO_PREFIXES else 3


def _estimate_distance_km(origin: str, destination: str) -> int:
    diff = abs(int(origin) - int(destination))
    return min(max(diff // 40, 10), 2500)


def _major(data: dict, key: str) -> float:
    """Minor units -> major units for the ML feature vector.

    Models were trained on rupee-scale values, so features stay in major units;
    only storage is exact. Raises a named error rather than a bare KeyError so
    schema drift is obvious at the call site instead of surfacing as a mystery
    failure inside inference.
    """
    if key not in data:
        raise KeyError(
            f"{key!r} missing from return data. Phase 3 moved money to integer "
            f"minor units -- callers must pass {key}, not the old float field."
        )
    return int(data[key] or 0) / 100


def build_feature_dict(
    return_data: dict,
    customer_return_count: int,
    org_return_count: int,
) -> dict:
    """
    Build the exact feature dict required by the ML model.
    Normalises all categorical values to the model's training vocabulary.
    """
    weight_grams = int(return_data["weight_grams"])
    vol_grams    = int(return_data["volumetric_weight_grams"])
    chargeable_weight = max(weight_grams, vol_grams) / 1000

    customer_return_rate = round(min(customer_return_count / 10, 0.6), 2)
    merchant_return_rate = round(min(org_return_count / 500, 0.30), 2) if org_return_count else 0.05

    # Normalise categoricals to model vocabulary
    courier       = _normalise(str(return_data.get("courier", "")), COURIER_MAP)
    category      = _normalise(str(return_data.get("item_category", "")), CATEGORY_MAP)
    payment_mode  = _normalise(str(return_data.get("payment_mode", "Prepaid")), PAYMENT_MAP)
    return_reason = _normalise(str(return_data.get("return_reason_code", "")), REASON_MAP)

    return {
        # Categorical (model vocabulary)
        "courier":       courier,
        "category":      category,
        "payment_mode":  payment_mode,
        "return_reason": return_reason,
        # Numeric (passthrough)
        # Minor units -> major, for the ML feature vector. Models were trained on
        # rupee-scale values; converting here keeps the feature distribution stable.
        "product_value":         _major(return_data, "item_value_minor"),
        "actual_weight":         weight_grams / 1000,
        "volumetric_weight":     vol_grams / 1000,
        "chargeable_weight":     chargeable_weight,
        "pickup_tier":           _pincode_tier(return_data["origin_pincode"]),
        "destination_tier":      _pincode_tier(return_data["destination_pincode"]),
        "distance_km":           _estimate_distance_km(
                                     return_data["origin_pincode"],
                                     return_data["destination_pincode"]
                                 ),
        "fragile":               int(return_data.get("fragile", False)),
        "festive":               int(return_data.get("festive", False)),
        "customer_return_rate":  customer_return_rate,
        "merchant_return_rate":  merchant_return_rate,
    }
