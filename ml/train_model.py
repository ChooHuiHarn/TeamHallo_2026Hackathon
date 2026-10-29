"""Train and evaluate the TensorFlow/Keras task-duration model.

    python ml/train_model.py                 # 20,000 synthetic rows, seed 42
    python ml/train_model.py --rows 40000 --epochs 300

Steps: generate synthetic data -> 70/15/15 train/validation/test split ->
standardise features and target (statistics from the TRAINING split only) ->
train Dense(32, relu) -> Dense(16, relu) -> Dense(1) with Adam and MSE ->
evaluate MAE / RMSE / R2 on the held-out test split -> save to models/.

Saved files:
  models/duration_model.keras     the trained network
  models/preprocessing.json       scaling parameters used at inference time
  models/metadata.json            version, architecture, split sizes, metrics
  models/test_predictions.json    predicted-vs-actual points for the analytics chart

All data is synthetic, so the metrics describe agreement with the simulator's
rules, not accuracy in a real warehouse.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app import config as C                       # noqa: E402
from app import rules                             # noqa: E402
from generate_dataset import TARGET, generate     # noqa: E402


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    err = predicted - actual
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((actual - actual.mean()) ** 2))
    return {
        "mae": round(float(np.mean(np.abs(err))), 3),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 3),
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--out-dir", type=Path, default=C.MODELS_DIR)
    args = parser.parse_args()

    import tensorflow as tf
    from tensorflow import keras

    np.random.seed(args.seed)
    tf.random.set_seed(args.seed)
    try:
        tf.keras.utils.set_random_seed(args.seed)
    except Exception:
        pass

    df = generate(args.rows, args.seed)
    X = df[C.FEATURE_NAMES].to_numpy(dtype=np.float32)
    y = df[TARGET].to_numpy(dtype=np.float32)

    # ---- split 70 / 15 / 15
    order = np.random.RandomState(args.seed).permutation(len(df))
    n_train, n_val = int(0.70 * len(df)), int(0.15 * len(df))
    tr, va, te = order[:n_train], order[n_train:n_train + n_val], order[n_train + n_val:]

    # ---- scaling from the training split only
    x_mean, x_std = X[tr].mean(axis=0), X[tr].std(axis=0)
    x_std = np.where(x_std < 1e-8, 1.0, x_std)
    y_mean, y_std = float(y[tr].mean()), float(y[tr].std())

    def sx(a): return (a - x_mean) / x_std
    def sy(a): return (a - y_mean) / y_std

    model = keras.Sequential([
        keras.layers.Input(shape=(len(C.FEATURE_NAMES),)),
        keras.layers.Dense(32, activation="relu"),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(1, activation="linear"),
    ], name="fleetpilot_duration_model")
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=0.003), loss="mse", metrics=["mae"])
    model.summary()

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=15, restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=6, min_lr=1e-5),
    ]
    history = model.fit(
        sx(X[tr]), sy(y[tr]), validation_data=(sx(X[va]), sy(y[va])),
        epochs=args.epochs, batch_size=args.batch_size, callbacks=callbacks, verbose=2,
    )

    def predict_seconds(rows: np.ndarray) -> np.ndarray:
        out = model.predict(sx(rows), verbose=0).reshape(-1) * y_std + y_mean
        return np.maximum(out, C.MIN_PREDICTION_SECONDS)

    pred_val, pred_test = predict_seconds(X[va]), predict_seconds(X[te])
    baseline_test = np.array([rules.baseline_estimate_seconds(d) for d in X[te][:, 0]])
    metrics = {
        "validation": regression_metrics(y[va], pred_val),
        "test": regression_metrics(y[te], pred_test),
        "baseline_formula_test": regression_metrics(y[te], baseline_test),
    }

    # ---- save
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "duration_model.keras")
    (out / "preprocessing.json").write_text(json.dumps({
        "feature_names": C.FEATURE_NAMES,
        "x_mean": [float(v) for v in x_mean], "x_std": [float(v) for v in x_std],
        "y_mean": y_mean, "y_std": y_std,
    }, indent=2))
    version = datetime.now(timezone.utc).strftime("v%Y.%m.%d-%H%M")
    (out / "metadata.json").write_text(json.dumps({
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "framework": f"TensorFlow {tf.__version__} / Keras {keras.__version__}",
        "architecture": "Dense(32, relu) -> Dense(16, relu) -> Dense(1, linear)",
        "parameters": int(model.count_params()),
        "loss": "mse (on standardised target)",
        "features": C.FEATURE_NAMES,
        "target": "task completion time in seconds",
        "data": {"source": "synthetic, generated by ml/generate_dataset.py", "rows": int(len(df)), "seed": args.seed},
        "split": {"train": int(len(tr)), "validation": int(len(va)), "test": int(len(te))},
        "epochs_run": len(history.history["loss"]),
        "metrics": metrics,
        "disclaimer": "Trained on synthetic data; performance does not establish real-world warehouse accuracy.",
    }, indent=2))
    pick = np.random.RandomState(args.seed).choice(len(te), size=min(300, len(te)), replace=False)
    (out / "test_predictions.json").write_text(json.dumps({
        "points": [{"actual": round(float(y[te][i]), 1), "predicted": round(float(pred_test[i]), 1)} for i in pick]
    }))

    print("\nSaved model to", out)
    for name, m in metrics.items():
        print(f"  {name:22s} MAE {m['mae']:7.3f} s   RMSE {m['rmse']:7.3f} s   R2 {m['r2']}")


if __name__ == "__main__":
    main()
