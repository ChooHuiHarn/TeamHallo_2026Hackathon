"""AI-versus-baseline experiments.

Both dispatchers run the *same* scenarios: identical starting batteries, warehouse
layout and task list (all generated from one integer seed). Every number in the
result comes from an actual simulation run; nothing is estimated or invented.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from . import config as C
from .dispatch import Predictor, dispatch_next
from .errors import InvalidRequest
from .simulation import Simulation
from .warehouse import Warehouse

SOURCE_ZONES = ["receiving", "storage", "picking"]
TARGET_ZONES = ["storage", "picking", "packing", "shipping"]
PRIORITIES = ["Low", "Normal", "Urgent"]
ARRIVALS = ("burst", "staggered", "sparse")

# key, label, unit, which direction is better
METRICS = [
    ("avg_turnaround_s", "Average task completion time (created to delivered)", "s", "lower"),
    ("avg_service_s", "Average service time (assigned to delivered)", "s", "lower"),
    ("makespan_s", "Total simulated completion time", "s", "lower"),
    ("tasks_completed", "Tasks completed", "tasks", "higher"),
    ("robot_idle_s", "Robot idle time (all robots)", "s", "lower"),
    ("total_distance_cells", "Total distance travelled", "cells", "lower"),
    ("rejected_assignments", "Failed / rejected assignments", "tasks", "lower"),
    ("constraint_violations", "Constraint violations", "events", "lower"),
]


def generate_scenario(seed: int, num_tasks: int = 12, arrival: str = "burst") -> dict[str, Any]:
    """Build a reproducible scenario (starting batteries + a task list) from a seed."""
    rng = np.random.RandomState(seed)
    wh = Warehouse()
    batteries = [float(rng.randint(22, 101)) for _ in range(C.NUM_ROBOTS)]   # a realistic mix of charge levels
    first_wave = math.ceil(num_tasks / 2)
    tasks = []
    for i in range(num_tasks):
        src = SOURCE_ZONES[rng.randint(0, len(SOURCE_ZONES))]
        options = [z for z in TARGET_ZONES if z != src]
        dst = options[rng.randint(0, len(options))]
        src_cells = [c for c in wh.zone_by_id(src).cells() if c not in wh.blocked]
        dst_cells = [c for c in wh.zone_by_id(dst).cells() if c not in wh.blocked]
        pickup = src_cells[rng.randint(0, len(src_cells))]
        destination = dst_cells[rng.randint(0, len(dst_cells))]
        priority = PRIORITIES[int(rng.choice(3, p=[0.3, 0.5, 0.2]))]
        load = float(rng.randint(10, 91))
        if arrival == "burst":
            arrival_tick = 0 if i < first_wave else (i - first_wave + 1) * 3
        elif arrival == "staggered":
            arrival_tick = i * 4
        else:  # "sparse": one task every 10 ticks, so several robots are usually free at decision time
            arrival_tick = i * 10
        tasks.append({
            "arrival_tick": arrival_tick,
            "pickup": {"x": pickup[0], "y": pickup[1]},
            "destination": {"x": destination[0], "y": destination[1]},
            "priority": priority,
            "load_pct": load,
        })
    return {"seed": seed, "arrival": arrival, "batteries": batteries, "tasks": tasks}


def run_scenario(
    scenario: dict[str, Any],
    kind: str,
    predictor: Optional[Predictor],
    safety_reserve: float = C.DEFAULT_SAFETY_RESERVE,
    max_steps: int = 600,
) -> dict[str, Any]:
    """Run one scenario with one dispatcher on a fresh simulation."""
    sim = Simulation(safety_reserve=safety_reserve, initial_batteries=scenario["batteries"])
    arrivals = sorted(scenario["tasks"], key=lambda t: t["arrival_tick"])
    idx = 0
    for _ in range(max_steps + 1):
        while idx < len(arrivals) and arrivals[idx]["arrival_tick"] <= sim.tick:
            a = arrivals[idx]
            sim.create_task(a["pickup"], a["destination"], a["priority"], a["load_pct"])
            idx += 1
        while dispatch_next(sim, predictor, kind)["assigned"]:
            pass
        if idx >= len(arrivals) and sim.all_done():
            break
        sim.step()
    metrics = sim.run_metrics()
    return {
        "dispatcher": kind,
        "finished": idx >= len(arrivals) and sim.all_done(),
        "metrics": {key: metrics[key] for key, *_ in METRICS},
        "ticks": metrics["ticks"],
        "violation_details": metrics["violation_details"],
        "prediction": sim.live_prediction_accuracy() if kind == "ai" else None,
    }


def _mean(values: list[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def compare(
    predictor: Optional[Predictor],
    seed: int = 42,
    runs: int = 3,
    num_tasks: int = 12,
    arrival: str = "burst",
    safety_reserve: float = C.DEFAULT_SAFETY_RESERVE,
    max_steps: int = 600,
) -> dict[str, Any]:
    if not 1 <= runs <= 10:
        raise InvalidRequest("runs must be between 1 and 10.")
    if not 1 <= num_tasks <= 40:
        raise InvalidRequest("num_tasks must be between 1 and 40.")
    if arrival not in ARRIVALS:
        raise InvalidRequest(f"arrival must be one of: {', '.join(ARRIVALS)}.")
    if not 50 <= max_steps <= 2000:
        raise InvalidRequest("max_steps must be between 50 and 2000.")
    if not 0 <= safety_reserve <= 50:
        raise InvalidRequest("safety_reserve must be between 0 and 50.")

    warnings: list[str] = []
    ai_available = predictor is not None and predictor.available
    if not ai_available:
        warnings.append(
            "The TensorFlow model is not loaded, so the AI dispatcher was not evaluated. "
            "Run `python ml/train_model.py` and restart the backend."
        )

    per_run = []
    for k in range(runs):
        scenario = generate_scenario(seed + k, num_tasks, arrival)
        baseline = run_scenario(scenario, "baseline", predictor, safety_reserve, max_steps)
        ai = run_scenario(scenario, "ai", predictor, safety_reserve, max_steps) if ai_available else None
        per_run.append({"seed": scenario["seed"], "baseline": baseline, "ai": ai})
        for label, result in (("baseline", baseline), ("AI", ai)):
            if result is not None and not result["finished"]:
                warnings.append(
                    f"Seed {scenario['seed']}: the {label} dispatcher did not finish all tasks within {max_steps} steps."
                )

    metrics_summary = []
    for key, label, unit, better in METRICS:
        base_mean = _mean([r["baseline"]["metrics"][key] for r in per_run])
        ai_mean = _mean([r["ai"]["metrics"][key] for r in per_run]) if ai_available else None
        improvement = None
        winner = None
        if ai_mean is not None and base_mean is not None:
            if ai_mean == base_mean:
                winner = "tie"
            else:
                ai_better = ai_mean < base_mean if better == "lower" else ai_mean > base_mean
                winner = "ai" if ai_better else "baseline"
            if base_mean != 0:
                raw = (base_mean - ai_mean) / abs(base_mean) * 100.0
                improvement = round(raw if better == "lower" else -raw, 1) + 0.0   # + 0.0 turns -0.0 into 0.0
        metrics_summary.append({
            "key": key, "label": label, "unit": unit, "better": better,
            "ai": ai_mean, "baseline": base_mean,
            "ai_improvement_pct": improvement,   # positive = AI better than baseline
            "winner": winner,
        })

    prediction = None
    if ai_available:
        pairs = [p for r in per_run for p in r["ai"]["prediction"]["pairs"]]
        if pairs:
            errs = [p["predicted"] - p["actual"] for p in pairs]
            prediction = {
                "n": len(pairs),
                "mae_s": round(sum(abs(e) for e in errs) / len(errs), 2),
                "rmse_s": round(math.sqrt(sum(e * e for e in errs) / len(errs)), 2),
                "pairs": pairs[:300],
            }

    for r in per_run:
        if r["ai"] is not None:
            r["ai"]["prediction"] = {k: v for k, v in (r["ai"]["prediction"] or {}).items() if k != "pairs"}

    return {
        "scenario": {
            "seed_start": seed, "runs": runs, "num_tasks": num_tasks, "arrival": arrival,
            "safety_reserve": safety_reserve, "max_steps": max_steps,
            "note": "Identical starting batteries, layout, task list and seed for both dispatchers.",
        },
        "ai_available": ai_available,
        "metrics": metrics_summary,
        "per_run": per_run,
        "prediction_accuracy_in_simulation": prediction,
        "conclusion": _conclusion(metrics_summary, per_run, ai_available, runs, num_tasks, seed),
        "warnings": warnings,
    }


def _conclusion(metrics: list[dict], per_run: list[dict], ai_available: bool, runs: int, num_tasks: int, seed: int) -> str:
    if not ai_available:
        return "Not evaluated: the AI dispatcher needs the trained TensorFlow model."
    turnaround = next(m for m in metrics if m["key"] == "avg_turnaround_s")
    ai_t, base_t = turnaround["ai"], turnaround["baseline"]
    if ai_t is None or base_t is None:
        return "Not evaluated: no tasks were completed, so completion times could not be compared."
    wins = sum(
        1 for r in per_run
        if r["ai"]["metrics"]["avg_turnaround_s"] is not None
        and r["baseline"]["metrics"]["avg_turnaround_s"] is not None
        and r["ai"]["metrics"]["avg_turnaround_s"] < r["baseline"]["metrics"]["avg_turnaround_s"]
    )
    ties = sum(
        1 for r in per_run
        if r["ai"]["metrics"]["avg_turnaround_s"] == r["baseline"]["metrics"]["avg_turnaround_s"]
    )
    diff = (base_t - ai_t) / base_t * 100.0 if base_t else 0.0
    scope = f"Over {runs} scenario(s) of {num_tasks} tasks (seeds {seed}-{seed + runs - 1})"
    if abs(diff) < 1.0:
        verdict = (
            f"{scope} there was no meaningful difference in average task completion time "
            f"(AI {ai_t:.1f} s vs baseline {base_t:.1f} s)."
        )
    elif diff > 0:
        verdict = (
            f"{scope} the AI dispatcher's average task completion time was {ai_t:.1f} s versus "
            f"{base_t:.1f} s for the baseline ({diff:.1f}% lower)."
        )
    else:
        verdict = (
            f"{scope} the baseline dispatcher was faster: {base_t:.1f} s versus {ai_t:.1f} s for the AI "
            f"dispatcher ({abs(diff):.1f}% lower)."
        )
    return (
        f"{verdict} The AI dispatcher had the shorter average in {wins} of {runs} scenario(s)"
        f"{f' ({ties} tied)' if ties else ''}. "
        "These are small runs of a simulation with synthetic rules; they do not show real-world warehouse performance."
    )
