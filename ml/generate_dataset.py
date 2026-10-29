"""Synthetic dataset generator for the task-duration model.

Each row is one imaginary delivery task. Features are sampled from ranges the
simulator can produce, and the target (seconds) comes from the documented rules
in backend/app/rules.py (`expected_duration_seconds`), multiplied by random
variation:

    duration = expected * LogNormal(0, 0.06)   # ~6 % proportional variation (detours, waiting)
             + Normal(0, 2 s)                   # timing jitter
             + Exponential(mean 2 s)            # occasional small delays

So the data is SYNTHETIC. A model trained on it learns the simulator's rules,
not real warehouse behaviour.

Usage:  python ml/generate_dataset.py --rows 20000 --seed 42 --out ml/data/synthetic_tasks.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config as C          # noqa: E402
from app import rules                # noqa: E402

TARGET = "duration_seconds"


def generate(rows: int = 20000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    distance = rng.randint(2, 41, size=rows).astype(float)          # cells (a 10x8 grid tops out around 30-40)
    battery = rng.uniform(15, 100, size=rows)                        # %
    load = rng.uniform(0, 100, size=rows)                            # %
    queued = rng.randint(0, 11, size=rows).astype(float)             # tasks waiting
    congestion = rng.beta(2.0, 3.0, size=rows)                       # 0..1, skewed towards low
    priority = rng.randint(0, 3, size=rows).astype(float)            # 0 Low, 1 Normal, 2 Urgent
    pickup_fraction = rng.uniform(0.25, 0.55, size=rows)             # share of the route before the pickup

    expected = np.array([
        rules.expected_duration_seconds(d, b, l, int(q), c, int(p), pf)
        for d, b, l, q, c, p, pf in zip(distance, battery, load, queued, congestion, priority, pickup_fraction)
    ])
    noisy = (
        expected * rng.lognormal(mean=0.0, sigma=0.06, size=rows)
        + rng.normal(0.0, 2.0, size=rows)
        + rng.exponential(2.0, size=rows)
    )
    duration = np.maximum(noisy, C.MIN_PREDICTION_SECONDS)

    return pd.DataFrame({
        "route_distance": distance,
        "battery_pct": battery,
        "load_pct": load,
        "queued_tasks": queued,
        "congestion": congestion,
        "priority": priority,
        TARGET: duration,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "ml" / "data" / "synthetic_tasks.csv")
    args = parser.parse_args()
    df = generate(args.rows, args.seed)
    assert list(df.columns[:-1]) == C.FEATURE_NAMES, "feature order must match backend config"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} synthetic rows to {args.out}")
    print(df.describe().loc[["mean", "min", "max"]].round(2).to_string())


if __name__ == "__main__":
    main()
