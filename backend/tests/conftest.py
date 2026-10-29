"""Shared test helpers. Makes `import app` work when pytest runs from backend/ or the repo root."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402

from app import rules  # noqa: E402


class RuleBasedPredictor:
    """TEST DOUBLE ONLY: a closed-form stand-in used to exercise dispatch logic
    without TensorFlow. The real model is covered by test_ml_model.py."""
    available = True
    error = None

    def predict(self, features):
        rows = np.asarray(features, dtype=float)
        return np.array([
            rules.expected_duration_seconds(r[0], r[1], r[2], int(r[3]), r[4], int(r[5])) for r in rows
        ])


class UnavailablePredictor:
    available = False
    error = "The TensorFlow model is not loaded."

    def predict(self, features):
        raise RuntimeError(self.error)


def run_until_done(sim, kind="baseline", predictor=None, max_ticks=800):
    from app.dispatch import dispatch_next
    for _ in range(max_ticks):
        while dispatch_next(sim, predictor, kind)["assigned"]:
            pass
        if sim.all_done() and all(r.status != "Moving" and r.status != "Assigned" for r in sim.robots):
            return True
        sim.step()
    return False
