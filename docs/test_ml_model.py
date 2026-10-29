"""TensorFlow model loading and inference tests.

These need TensorFlow AND a trained model (`python ml/train_model.py`). They skip
themselves with a clear message otherwise, so the rest of the suite still runs.
"""
import numpy as np
import pytest

from app import config as C
from app.ml.predictor import DurationPredictor


def test_missing_model_files_give_a_clear_error_without_crashing(tmp_path=None):
    import tempfile, pathlib
    base = pathlib.Path(tempfile.mkdtemp())
    predictor = DurationPredictor(base / "nope.keras", base / "prep.json", base / "meta.json", base / "tp.json")
    assert predictor.load() is False
    assert predictor.available is False and "not found" in predictor.error
    with pytest.raises(RuntimeError):
        predictor.predict(np.zeros((1, 6)))


def _loaded():
    pytest.importorskip("tensorflow")
    if not C.MODEL_PATH.exists():
        pytest.skip("No trained model found - run `python ml/train_model.py` first.")
    predictor = DurationPredictor()
    assert predictor.load(), predictor.error
    return predictor


def test_model_loads_and_predicts_real_values():
    predictor = _loaded()
    row = np.array([[20, 80, 40, 2, 0.3, 1]], dtype=np.float32)
    out = predictor.predict(row)
    assert out.shape == (1,) and np.isfinite(out).all() and out[0] > 0


def test_model_predictions_respond_to_inputs():
    predictor = _loaded()
    short = predictor.predict(np.array([[5, 90, 20, 0, 0.1, 1]]))[0]
    long_ = predictor.predict(np.array([[35, 90, 20, 0, 0.1, 1]]))[0]
    congested = predictor.predict(np.array([[20, 90, 20, 0, 0.9, 1]]))[0]
    calm = predictor.predict(np.array([[20, 90, 20, 0, 0.0, 1]]))[0]
    assert long_ > short            # farther routes take longer
    assert congested > calm         # congestion slows tasks down


def test_model_batch_matches_single_predictions():
    predictor = _loaded()
    rows = np.array([[10, 70, 30, 1, 0.2, 0], [25, 55, 80, 4, 0.6, 2]], dtype=np.float32)
    batch = predictor.predict(rows)
    singles = np.array([predictor.predict(r.reshape(1, -1))[0] for r in rows])
    assert np.allclose(batch, singles, atol=1e-3)


def test_wrong_feature_count_is_rejected():
    predictor = _loaded()
    with pytest.raises(ValueError):
        predictor.predict(np.zeros((1, 5)))


def test_metadata_contains_real_evaluation_metrics():
    predictor = _loaded()
    meta = predictor.metadata()
    assert meta and meta["metrics"]["test"]["mae"] > 0 and meta["metrics"]["test"]["rmse"] > 0
    assert "synthetic" in meta["data"]["source"]


def test_ai_dispatch_uses_the_real_model():
    predictor = _loaded()
    from app.dispatch import dispatch_next
    from app.simulation import Simulation
    sim = Simulation()
    sim.create_task({"zone": "receiving"}, {"zone": "shipping"}, "Normal", 40)
    result = dispatch_next(sim, predictor, "ai")
    assert result["assigned"] and result["decision"]["estimator"] == "tensorflow"
    f = result["decision"]["features"]
    direct = predictor.predict(np.array([[f[n] for n in C.FEATURE_NAMES]]))[0]
    assert abs(direct - result["decision"]["predicted_seconds"]) < 0.05
