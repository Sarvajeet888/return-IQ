"""
ML validation tests (Phase 9.7).

Verifies the model pipeline behaves correctly and - importantly - that the
system is honest about what it is. Phase 1 found four rule-based components
labelled as "AI models"; these tests pin down the corrected behaviour so it
cannot silently regress.
"""
from __future__ import annotations
import uuid

import pytest

from app.services.feature_mapping import (
    build_feature_dict, check_unmapped_features,
    COURIER_MAP, CATEGORY_MAP, REASON_MAP, PAYMENT_MAP,
)


# ── Feature mapping correctness ──────────────────────────────────────────────

MODEL_VOCABULARY = {
    "courier":       {"BlueDart", "DTDC", "Delhivery", "Ekart", "Shadowfax", "Xpressbees"},
    "category":      {"Beauty", "Books", "Electronics", "Fashion", "Home", "Sports"},
    "payment_mode":  {"COD", "Prepaid"},
    "return_reason": {"Changed Mind", "Damaged", "Quality Issue", "Wrong Item", "Wrong Size"},
}


@pytest.mark.parametrize("mapping,field", [
    (COURIER_MAP, "courier"),
    (CATEGORY_MAP, "category"),
    (REASON_MAP, "return_reason"),
    (PAYMENT_MAP, "payment_mode"),
])
def test_every_mapping_target_exists_in_model_vocabulary(mapping, field):
    """
    Every value the mapping layer can produce must be something the trained
    model actually recognises. A typo here (e.g. "XpressBees" vs "Xpressbees")
    would silently zero out that feature for every affected return.
    """
    targets = set(mapping.values())
    unknown = targets - MODEL_VOCABULARY[field]
    assert not unknown, (
        f"{field} mapping produces values the model was never trained on: {unknown}. "
        f"These would be one-hot encoded as all-zeros."
    )


def test_courier_mapping_is_case_insensitive():
    for variant in ["BlueDart", "bluedart", "BLUEDART", "  BlueDart  "]:
        f = build_feature_dict(_base_return(courier=variant), 0, 0)
        assert f["courier"] == "BlueDart", f"variant {variant!r} did not normalise"


def test_category_aliases_map_correctly():
    """Merchants use different words for the same thing - all must map."""
    for alias in ["Apparel", "Clothing", "Footwear", "Fashion", "accessories"]:
        f = build_feature_dict(_base_return(item_category=alias), 0, 0)
        assert f["category"] == "Fashion", f"{alias!r} -> {f['category']!r}, expected Fashion"


def test_reason_aliases_map_correctly():
    assert build_feature_dict(_base_return(return_reason_code="defective"), 0, 0)["return_reason"] == "Damaged"
    assert build_feature_dict(_base_return(return_reason_code="damaged"), 0, 0)["return_reason"] == "Damaged"
    assert build_feature_dict(_base_return(return_reason_code="size_issue"), 0, 0)["return_reason"] == "Wrong Size"


def _base_return(**overrides):
    base = {
        "item_value_minor": 1500000, "currency": "INR", "item_category": "Electronics",
        "weight_grams": 2000, "volumetric_weight_grams": 2500,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False,
    }
    base.update(overrides)
    return base


# ── Feature dict shape ───────────────────────────────────────────────────────

REQUIRED_FEATURES = [
    "product_value", "actual_weight", "volumetric_weight", "chargeable_weight",
    "courier", "category", "payment_mode", "return_reason",
    "pickup_tier", "destination_tier", "distance_km",
    "fragile", "festive", "customer_return_rate", "merchant_return_rate",
]


def test_feature_dict_has_exactly_the_expected_keys():
    f = build_feature_dict(_base_return(), 0, 0)
    assert set(f.keys()) == set(REQUIRED_FEATURES), (
        f"feature mismatch. Missing: {set(REQUIRED_FEATURES) - set(f.keys())}, "
        f"Extra: {set(f.keys()) - set(REQUIRED_FEATURES)}"
    )


def test_chargeable_weight_is_max_of_actual_and_volumetric():
    """Courier billing rule: you pay for whichever is heavier."""
    f = build_feature_dict(_base_return(weight_grams=1000, volumetric_weight_grams=5000), 0, 0)
    assert f["chargeable_weight"] == 5.0

    f = build_feature_dict(_base_return(weight_grams=8000, volumetric_weight_grams=2000), 0, 0)
    assert f["chargeable_weight"] == 8.0


def test_metro_pincode_gets_tier_1():
    f = build_feature_dict(_base_return(origin_pincode="400001"), 0, 0)   # Mumbai
    assert f["pickup_tier"] == 1

    f = build_feature_dict(_base_return(origin_pincode="110001"), 0, 0)   # Delhi
    assert f["pickup_tier"] == 1


def test_non_metro_pincode_gets_tier_3():
    f = build_feature_dict(_base_return(origin_pincode="431122"), 0, 0)   # Beed, MH
    assert f["pickup_tier"] == 3


def test_customer_return_rate_is_capped():
    """Rate must stay in the range the model saw during training."""
    f = build_feature_dict(_base_return(), customer_return_count=10_000, org_return_count=0)
    assert 0 <= f["customer_return_rate"] <= 0.6, "rate escaped its training range"


def test_merchant_return_rate_is_capped():
    f = build_feature_dict(_base_return(), 0, 1_000_000)
    assert 0 <= f["merchant_return_rate"] <= 0.30


def test_distance_is_bounded():
    """Distance estimate must never go negative or absurdly large."""
    f = build_feature_dict(_base_return(origin_pincode="110001", destination_pincode="999999"), 0, 0)
    assert 10 <= f["distance_km"] <= 2500


def test_booleans_converted_to_ints():
    f = build_feature_dict(_base_return(fragile=True, festive=True), 0, 0)
    assert f["fragile"] == 1 and isinstance(f["fragile"], int)
    assert f["festive"] == 1


def test_feature_building_is_deterministic():
    """Same input must always produce the same features - no hidden randomness."""
    r = _base_return()
    assert build_feature_dict(r, 5, 100) == build_feature_dict(r, 5, 100)


# ── Unmapped value detection (the Phase 9 finding) ───────────────────────────

def test_unmapped_courier_is_detected():
    warnings = check_unmapped_features(_base_return(courier="FedEx"))
    assert len(warnings) == 1
    assert "FedEx" in warnings[0]
    assert "courier" in warnings[0]


def test_unmapped_category_is_detected():
    warnings = check_unmapped_features(_base_return(item_category="Automotive"))
    assert any("Automotive" in w for w in warnings)


def test_multiple_unmapped_values_all_reported():
    warnings = check_unmapped_features(
        _base_return(courier="FedEx", item_category="Automotive", return_reason_code="whatever")
    )
    assert len(warnings) == 3, f"expected 3 warnings, got {len(warnings)}: {warnings}"


def test_all_known_values_produce_no_warnings():
    assert check_unmapped_features(_base_return()) == []


def test_warning_message_lists_valid_alternatives():
    """A warning that doesn't tell you what IS valid isn't actionable."""
    warnings = check_unmapped_features(_base_return(courier="FedEx"))
    assert "BlueDart" in warnings[0], "warning should list the valid couriers"


# ── Model artifacts ──────────────────────────────────────────────────────────

def test_model_artifacts_exist():
    from pathlib import Path
    import app.services.ml_service as ml

    artifacts = Path(ml.__file__).parent.parent.parent / "ml" / "artifacts"
    for name in ["model.joblib", "preprocessor.joblib",
                 "feature_columns.json", "model_metadata.json"]:
        assert (artifacts / name).exists(), f"missing ML artifact: {name}"


def test_model_stats_come_from_metadata_not_hardcoded():
    """
    Phase 4 fixed a bug where R2/RMSE were hardcoded literals that would
    keep reporting stale numbers after any retrain. This pins the fix.
    """
    import json
    from pathlib import Path
    from app.services.ml_service import get_model_stats
    import app.services.ml_service as ml

    meta_path = Path(ml.__file__).parent.parent.parent / "ml" / "artifacts" / "model_metadata.json"
    meta = json.loads(meta_path.read_text())
    stats = get_model_stats()

    assert stats, "get_model_stats returned nothing"
    # At least one metric in the response must match the metadata file
    meta_values = {str(v) for v in meta.values() if isinstance(v, (int, float, str))}
    stats_values = {str(v) for v in stats.values() if isinstance(v, (int, float, str))}
    assert meta_values & stats_values, (
        "no values shared between model_metadata.json and get_model_stats() - "
        "stats may be hardcoded again"
    )


# ── Honesty checks: ML vs rule-based labelling ───────────────────────────────

def test_explainability_does_not_claim_to_be_shap():
    """
    The explainability output is XGBoost gain-based feature importance, not
    SHAP. Phase 4 corrected this labelling; if the wording ever changes back
    to claiming SHAP, this test fails.
    """
    from pathlib import Path
    import app.services.ml_service as ml

    source = Path(ml.__file__).read_text().lower()
    if "shap" in source:
        assert "not full shap" in source or "not shap" in source, (
            "ml_service mentions SHAP without the disclaimer that it isn't real SHAP"
        )


def test_ai_transparency_doc_states_rule_based_components():
    """The transparency doc must keep saying which parts aren't real ML."""
    from pathlib import Path
    import app

    # Moved to docs/ai/ in Phase 10 documentation restructure.
    doc = Path(app.__file__).parent.parent.parent / "docs" / "ai" / "AI_TRANSPARENCY.md"
    if not doc.exists():
        pytest.skip("AI_TRANSPARENCY.md not present in this checkout")

    text = doc.read_text().lower()
    assert "rule" in text, "transparency doc no longer mentions rule-based components"
    assert "fraud" in text

    # The doc legitimately *quotes* the old false claim in order to correct it
    # ("the platform was previously labelled as having 5 AI models"). So a bare
    # substring check gives a false positive. What we actually care about is
    # that the claim never appears as a live assertion - i.e. it must always
    # sit next to corrective language.
    CORRECTIVE = ["previously", "incorrectly", "was labelled", "was labeled",
                  "corrects", "correcting", "not accurate", "mislabel"]

    for claim in ["5 ai models", "five ai models", "5 machine learning models"]:
        idx = text.find(claim)
        if idx == -1:
            continue
        window = text[max(0, idx - 250): idx + 250]
        assert any(c in window for c in CORRECTIVE), (
            f"transparency doc states {claim!r} without corrective context - "
            f"the Phase 1 mislabelling may have crept back in"
        )

    # And the honest breakdown must still be present
    assert "1 real ml model" in text or "one real ml model" in text or "real ml model" in text, (
        "transparency doc no longer states how many components are real ML"
    )


# ── Cost output bounds (found in a real 500-record load) ────────────────────

def test_predicted_cost_is_never_negative():
    """
    XGBoost regressors are unbounded. On inputs outside the training
    distribution they extrapolate straight through zero - a real load of 500
    records produced a minimum predicted cost of Rs -738, i.e. the model
    claiming it would PAY the merchant to process a return.

    Somebody always pays the courier. Cost has a floor.
    """
    from ml.predict import _clamp_cost, MIN_COST_INR
    assert _clamp_cost(-738.0) == MIN_COST_INR
    assert _clamp_cost(-0.01) == MIN_COST_INR
    assert _clamp_cost(0.0) == MIN_COST_INR
    # Legitimate values pass through untouched
    assert _clamp_cost(450.0) == 450.0
    assert _clamp_cost(1448.0) == 1448.0


def test_clamp_floor_is_plausible():
    """The floor should be a real minimum handling cost, not a token 0.01."""
    from ml.predict import MIN_COST_INR
    assert 1 <= MIN_COST_INR <= 100, "floor should be a plausible minimum handling cost"
