"""
Pure-Python/NumPy preprocessor — replaces sklearn ColumnTransformer.
Zero scipy dependency. Works on Windows with AppLocker/WDAC policies.

Replicates the exact transform of the original preprocessor.joblib,
verified against actual model output during development.
"""
from __future__ import annotations

import numpy as np

# ── Exact categories from the trained model (do NOT change order) ─────────────
COURIERS      = ['BlueDart', 'DTDC', 'Delhivery', 'Ekart', 'Shadowfax', 'Xpressbees']
CATEGORIES    = ['Beauty', 'Books', 'Electronics', 'Fashion', 'Home', 'Sports']
PAYMENT_MODES = ['COD', 'Prepaid']
RETURN_REASONS = ['Changed Mind', 'Damaged', 'Quality Issue', 'Wrong Item', 'Wrong Size']
NUMERIC_COLS  = [
    'product_value', 'actual_weight', 'volumetric_weight', 'chargeable_weight',
    'pickup_tier', 'destination_tier', 'distance_km',
    'fragile', 'festive', 'customer_return_rate', 'merchant_return_rate'
]

# Total feature vector length = 6 + 6 + 2 + 5 + 11 = 30
N_FEATURES = len(COURIERS) + len(CATEGORIES) + len(PAYMENT_MODES) + len(RETURN_REASONS) + len(NUMERIC_COLS)

# Human-readable name for every column of the 30-element vector, in the exact
# order transform() emits them. Used by ml/predict.py to turn raw XGBoost
# feature_importances_ (which only knows column *indices*) into names that
# are actually meaningful for explainability output.
FEATURE_NAMES: list[str] = (
    [f"courier={c}" for c in COURIERS]
    + [f"category={c}" for c in CATEGORIES]
    + [f"payment_mode={c}" for c in PAYMENT_MODES]
    + [f"return_reason={c}" for c in RETURN_REASONS]
    + list(NUMERIC_COLS)
)
assert len(FEATURE_NAMES) == N_FEATURES

def _ohe(value: str, vocab: list[str]) -> list[float]:
    """One-hot encode a single value against a vocabulary."""
    return [1.0 if value == v else 0.0 for v in vocab]


def transform(row: dict) -> np.ndarray:
    """
    Transform a single feature dict into the 30-element numpy array
    that the XGBoost model expects.

    Unknown categorical values produce all-zeros for that group
    (handle_unknown='ignore' behaviour of the original OHE).
    """
    vec: list[float] = []
    vec += _ohe(row.get('courier', ''),       COURIERS)       # 6
    vec += _ohe(row.get('category', ''),      CATEGORIES)     # 6
    vec += _ohe(row.get('payment_mode', ''),  PAYMENT_MODES)  # 2
    vec += _ohe(row.get('return_reason', ''), RETURN_REASONS) # 5
    for col in NUMERIC_COLS:                                   # 11
        vec.append(float(row.get(col, 0)))
    return np.array(vec, dtype=np.float32).reshape(1, -1)


class PurePythonPreprocessor:
    """Drop-in replacement for the sklearn ColumnTransformer."""
    def transform(self, df) -> np.ndarray:
        rows = df.to_dict(orient='records')
        return np.vstack([transform(r) for r in rows])
