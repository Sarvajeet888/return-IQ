"""
ML predictor — uses pure Python/NumPy preprocessor.
No sklearn, no scipy required at runtime.
Compatible with Windows AppLocker / WDAC environments.
"""
from __future__ import annotations

import base64
import io
import json
import lzma
from pathlib import Path

import joblib
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
MODEL_PATH = ML_DIR / "artifacts" / "model.joblib"
MODEL_XZ_B64_PATH = ML_DIR / "artifacts" / "model.joblib.xz.b64"
METADATA_PATH = ML_DIR / "artifacts" / "model_metadata.json"

# Import our pure-Python preprocessor (no sklearn/scipy)
from ml.preprocessor import FEATURE_NAMES, PurePythonPreprocessor



# Reverse logistics can be cheap, but it is never free and it is never
# negative - somebody always pays the courier. XGBoost regressors are
# unbounded, so inputs outside the training distribution extrapolate
# straight through zero: a real load of 500 records produced a minimum
# predicted cost of Rs -738, i.e. the model claiming it would PAY the
# merchant to process a return.
#
# Clamping here rather than at the call sites so every consumer
# (predict, predict_with_explanation, batch loaders) gets the same floor.
MIN_COST_INR = 20.0


def _clamp_cost(value: float) -> float:
    """Floor a raw model output at a physically possible minimum."""
    return max(float(value), MIN_COST_INR)


class ReverseLogisticsPredictor:
    def __init__(self) -> None:
        # Load only the XGBoost model — no sklearn preprocessor needed.
        # Repositories may store the same model as .xz to keep Git clones small.
        if MODEL_PATH.exists():
            self.model = joblib.load(MODEL_PATH)
        elif MODEL_XZ_B64_PATH.exists():
            encoded = MODEL_XZ_B64_PATH.read_text(encoding="ascii")
            compressed = base64.b64decode(encoded)
            model_bytes = lzma.decompress(compressed)
            self.model = joblib.load(io.BytesIO(model_bytes))
        else:
            raise FileNotFoundError(
                f"ML model not found at {MODEL_PATH} or {MODEL_XZ_B64_PATH}"
            )
        self.preprocessor = PurePythonPreprocessor()
        self._call_count = 0
        self._total_latency_ms = 0.0
        self._global_importance = self._load_global_importance()
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        """Single source of truth for version/metrics - read from disk, never hardcoded."""
        try:
            with open(METADATA_PATH) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load_global_importance(self) -> list[tuple[str, float]]:
        """
        Real XGBoost feature importances (gain-based, from the trained
        Booster itself) - not a hand-picked guess. Returned sorted, highest
        first. Empty list if the loaded object doesn't expose importances
        (e.g. a non-tree model), so callers must handle that gracefully.
        """
        raw = getattr(self.model, "feature_importances_", None)
        if raw is None:
            return []
        pairs = list(zip(FEATURE_NAMES, [float(v) for v in raw]))
        return sorted(pairs, key=lambda p: p[1], reverse=True)

    def top_drivers_for_row(self, processed_row, k: int = 3) -> list[str]:
        """
        Approximate per-prediction explanation: rank features by
        (global XGBoost importance) x (how far this row's value is from 0
        for that feature - i.e. whether the feature was "active" at all for
        one-hot columns, or how large it is for numeric columns).

        This is a real, computed signal from the actual trained model - not
        a hardcoded if/else - but it is an importance-weighted heuristic,
        NOT full SHAP value attribution. Label it as such in any UI/API that
        surfaces it, so it isn't mistaken for a more rigorous explanation
        than it is.
        """
        if not self._global_importance or processed_row is None:
            return []
        row = processed_row[0]
        scored = []
        for name, importance in self._global_importance:
            idx = FEATURE_NAMES.index(name)
            activation = abs(float(row[idx]))
            scored.append((name, importance * activation))
        scored.sort(key=lambda p: p[1], reverse=True)
        return [name for name, score in scored[:k] if score > 0]

    def predict(self, payload: dict) -> float:
        import time
        start = time.perf_counter()
        processed = self.preprocessor.transform(pd.DataFrame([payload]))
        prediction = _clamp_cost(self.model.predict(processed)[0])
        latency = (time.perf_counter() - start) * 1000
        self._call_count += 1
        self._total_latency_ms += latency
        return round(prediction, 2)

    def predict_with_explanation(self, payload: dict) -> dict:
        """Same as predict(), but also returns real top feature drivers for this row."""
        import time
        start = time.perf_counter()
        processed = self.preprocessor.transform(pd.DataFrame([payload]))
        prediction = _clamp_cost(self.model.predict(processed)[0])
        latency = (time.perf_counter() - start) * 1000
        self._call_count += 1
        self._total_latency_ms += latency
        return {
            "predicted_cost_inr": round(prediction, 2),
            "top_drivers": self.top_drivers_for_row(processed),
            "inference_latency_ms": round(latency, 3),
        }

    @property
    def stats(self) -> dict:
        return {
            "total_predictions": self._call_count,
            "avg_latency_ms": round(self._total_latency_ms / max(self._call_count, 1), 2),
            "model_version": self.metadata.get("model_version", "unknown"),
            "algorithm": self.metadata.get("algorithm", "unknown"),
            "train_rows": self.metadata.get("train_rows"),
            "r2_score": self.metadata.get("r2"),
            "mae": self.metadata.get("mae"),
            "rmse": self.metadata.get("rmse"),
        }
