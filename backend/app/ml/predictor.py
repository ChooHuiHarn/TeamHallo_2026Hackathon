"""Loads the trained TensorFlow/Keras model once and runs real inference.

The model is trained offline by `ml/train_model.py` on synthetic data. This
module never invents a prediction: if the model or its preprocessing file is
missing, `available` is False and callers must report that clearly.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from .. import config as C


class DurationPredictor:
    def __init__(
        self,
        model_path: Path = C.MODEL_PATH,
        preprocessing_path: Path = C.PREPROCESSING_PATH,
        metadata_path: Path = C.METADATA_PATH,
        test_predictions_path: Path = C.TEST_PREDICTIONS_PATH,
    ):
        self.model_path = Path(model_path)
        self.preprocessing_path = Path(preprocessing_path)
        self.metadata_path = Path(metadata_path)
        self.test_predictions_path = Path(test_predictions_path)
        self.available = False
        self.error: Optional[str] = "The model has not been loaded yet."
        self.model = None
        self._tf = None
        self._lock = threading.Lock()
        self._x_mean: Optional[np.ndarray] = None
        self._x_std: Optional[np.ndarray] = None
        self._y_mean = 0.0
        self._y_std = 1.0
        self.feature_names: list[str] = list(C.FEATURE_NAMES)
        self._metadata: Optional[dict] = None

    # ------------------------------------------------------------------ loading
    def load(self) -> bool:
        """Load the model and preprocessing parameters. Never raises."""
        self.available = False
        self.model = None
        try:
            if not self.model_path.exists():
                self.error = (
                    f"Model file not found at {self.model_path}. "
                    "Train it with `python ml/train_model.py`."
                )
                return False
            if not self.preprocessing_path.exists():
                self.error = f"Preprocessing file not found at {self.preprocessing_path}."
                return False
            prep = json.loads(self.preprocessing_path.read_text())
            self._x_mean = np.asarray(prep["x_mean"], dtype=np.float32)
            self._x_std = np.maximum(np.asarray(prep["x_std"], dtype=np.float32), 1e-8)
            self._y_mean = float(prep["y_mean"])
            self._y_std = max(float(prep["y_std"]), 1e-8)
            self.feature_names = list(prep.get("feature_names", C.FEATURE_NAMES))
            if len(self._x_mean) != len(C.FEATURE_NAMES):
                self.error = "Preprocessing file does not match the six expected input features."
                return False
            self._metadata = self._read_json(self.metadata_path)

            import tensorflow as tf  # imported lazily: the API still starts without TensorFlow
            from tensorflow import keras

            self._tf = tf
            self.model = keras.models.load_model(self.model_path, compile=False)
            self.error = None
            self.available = True
            return True
        except ImportError:
            self.error = "TensorFlow is not installed in this Python environment (pip install tensorflow)."
        except Exception as exc:  # corrupt file, version mismatch, ...
            self.error = f"The model could not be loaded: {exc}"
        self.model = None
        self.available = False
        return False

    @staticmethod
    def _read_json(path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text()) if path.exists() else None
        except Exception:
            return None

    # ------------------------------------------------------------------ inference
    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict task duration (seconds) for a matrix of shape (n, 6).

        Column order is `config.FEATURE_NAMES`. Real TensorFlow inference.
        """
        if not self.available or self.model is None:
            raise RuntimeError(self.error or "Model not available.")
        x = np.asarray(features, dtype=np.float32)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.shape[1] != len(C.FEATURE_NAMES):
            raise ValueError(f"Expected {len(C.FEATURE_NAMES)} features per row, got {x.shape[1]}.")
        scaled = (x - self._x_mean) / self._x_std
        with self._lock:
            out = self.model(self._tf.constant(scaled, dtype=self._tf.float32), training=False)
        pred = np.asarray(out.numpy(), dtype=np.float64).reshape(-1) * self._y_std + self._y_mean
        return np.maximum(pred, C.MIN_PREDICTION_SECONDS)

    # ------------------------------------------------------------------ reporting
    def metadata(self) -> Optional[dict]:
        return self._metadata

    def test_predictions(self) -> Optional[list[dict]]:
        data = self._read_json(self.test_predictions_path)
        return data.get("points") if data else None

    def status(self) -> dict:
        meta = self._metadata or {}
        return {
            "available": self.available,
            "status": "Loaded" if self.available else "Unavailable",
            "version": meta.get("version"),
            "error": self.error,
            "trained_on": "synthetic data" if meta else None,
        }
