"""
Real ML pipeline tests for PurePythonPreprocessor / transform().
Covers: shape correctness, one-hot correctness, unknown-category handling,
determinism, ordering guarantees, and numeric passthrough accuracy.

Run with: pytest test_preprocessor.py -v
(No xgboost/fastapi required - this only tests the preprocessing layer.)
"""
import math
import numpy as np
import pandas as pd
from ml.preprocessor import PurePythonPreprocessor, transform, N_FEATURES, COURIERS, CATEGORIES, PAYMENT_MODES, RETURN_REASONS, NUMERIC_COLS

BASE_ROW = {
    "courier": "BlueDart", "category": "Electronics", "payment_mode": "COD",
    "return_reason": "Damaged", "product_value": 1500, "actual_weight": 0.8,
    "volumetric_weight": 1.1, "chargeable_weight": 1.1, "pickup_tier": 1,
    "destination_tier": 3, "distance_km": 900, "fragile": 1, "festive": 0,
    "customer_return_rate": 0.3, "merchant_return_rate": 0.1,
}


def test_feature_vector_length_matches_declared_n_features():
    out = transform(BASE_ROW)
    assert out.shape == (1, N_FEATURES)
    assert N_FEATURES == 30  # documents the contract predict.py/model.joblib rely on


def test_one_hot_blocks_are_mutually_exclusive_and_sum_to_one():
    out = transform(BASE_ROW)[0]
    courier_block = out[0:6]
    category_block = out[6:12]
    payment_block = out[12:14]
    reason_block = out[14:19]
    assert courier_block.sum() == 1.0
    assert category_block.sum() == 1.0
    assert payment_block.sum() == 1.0
    assert reason_block.sum() == 1.0


def test_correct_index_is_hot_for_known_category():
    out = transform(BASE_ROW)[0]
    assert out[COURIERS.index("BlueDart")] == 1.0
    assert out[6 + CATEGORIES.index("Electronics")] == 1.0


def test_unknown_category_produces_all_zero_block_not_a_crash():
    row = dict(BASE_ROW, courier="NewCourierNotInTraining")
    out = transform(row)[0]
    courier_block = out[0:6]
    assert courier_block.sum() == 0.0  # documented "handle_unknown=ignore" behaviour


def test_missing_field_defaults_gracefully_instead_of_keyerror():
    row = {k: v for k, v in BASE_ROW.items() if k != "distance_km"}
    out = transform(row)  # should not raise
    distance_idx = 19 + NUMERIC_COLS.index("distance_km")
    assert out[0][distance_idx] == 0.0


def test_numeric_passthrough_values_are_exact():
    out = transform(BASE_ROW)[0]
    for i, col in enumerate(NUMERIC_COLS):
        assert math.isclose(out[19 + i], float(BASE_ROW[col]), rel_tol=1e-6)


def test_transform_is_deterministic():
    out1 = transform(BASE_ROW)
    out2 = transform(BASE_ROW)
    assert np.array_equal(out1, out2)


def test_dataframe_batch_path_matches_single_row_path():
    p = PurePythonPreprocessor()
    df = pd.DataFrame([BASE_ROW, BASE_ROW])
    batch_out = p.transform(df)
    single_out = transform(BASE_ROW)
    assert batch_out.shape == (2, N_FEATURES)
    assert np.array_equal(batch_out[0], single_out[0])
    assert np.array_equal(batch_out[1], single_out[0])


def test_extreme_numeric_values_do_not_produce_nan_or_inf():
    row = dict(BASE_ROW, product_value=1e9, distance_km=0, actual_weight=0)
    out = transform(row)
    assert not np.isnan(out).any()
    assert not np.isinf(out).any()


def test_output_dtype_is_float32_for_xgboost_compatibility():
    out = transform(BASE_ROW)
    assert out.dtype == np.float32
