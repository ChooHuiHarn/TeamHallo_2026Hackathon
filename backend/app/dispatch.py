"""Task dispatch: choose the best robot for the next task.

Workflow (see docs/architecture.md):
  1. find pending tasks;
  2. take the next one by priority, FIFO inside a priority;
  3. find robots that are idle and feasible (route exists, battery covers the
     task plus a safety reserve);
  4. plan routes with A*;
  5. estimate completion time for every feasible robot
        - "ai":       real TensorFlow inference on six features
        - "baseline": documented formula (distance x speed + handling);
  6. pick the lowest estimate (ties: lowest robot id);
  7. record the assignment and a human-readable explanation.

If nobody is feasible the task stays pending and the reason is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import numpy as np

from . import config as C
from . import rules
from .entities import Robot, Task
from .errors import Conflict, InvalidRequest, ModelUnavailable
from .pathfinding import astar, manhattan
from .simulation import Simulation, congestion_score
from .warehouse import Cell

DISPATCHERS = ("ai", "baseline")


class Predictor(Protocol):
    available: bool
    error: Optional[str]

    def predict(self, features: np.ndarray) -> np.ndarray: ...


@dataclass
class Candidate:
    robot_id: str
    feasible: bool
    reason: str
    battery_pct: float
    route_distance: Optional[int] = None
    battery_needed_pct: Optional[float] = None
    congestion: Optional[float] = None
    features: Optional[dict] = None
    predicted_seconds: Optional[float] = None
    baseline_seconds: Optional[float] = None
    path_to_pickup: list[Cell] = field(default_factory=list)
    path_to_destination: list[Cell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "feasible": self.feasible,
            "reason": self.reason,
            "battery_pct": round(self.battery_pct, 1),
            "route_distance": self.route_distance,
            "battery_needed_pct": None if self.battery_needed_pct is None else round(self.battery_needed_pct, 1),
            "congestion": None if self.congestion is None else round(self.congestion, 3),
            "predicted_seconds": None if self.predicted_seconds is None else round(self.predicted_seconds, 1),
            "baseline_seconds": None if self.baseline_seconds is None else round(self.baseline_seconds, 1),
        }


# --------------------------------------------------------------------------- candidates
def _nearest_charging_distance(sim: Simulation, start: Cell) -> Optional[int]:
    """Moves from `start` to the closest charging bay (obstacles only)."""
    best: Optional[int] = None
    for cell in sorted(sim.warehouse.charging_cells(), key=lambda c: (manhattan(start, c), c[1], c[0])):
        if best is not None and manhattan(start, cell) >= best:
            break
        path = astar(sim.warehouse, start, cell)
        if path is not None:
            length = len(path) - 1
            if best is None or length < best:
                best = length
    return best


def evaluate_candidate(sim: Simulation, task: Task, robot: Robot, queued: int) -> Candidate:
    """Check whether one robot can take the task and plan its route."""
    cand = Candidate(robot_id=robot.id, feasible=False, reason="", battery_pct=robot.battery)

    if robot.status == C.ROBOT_OFFLINE:
        cand.reason = "Offline"
        return cand
    if robot.status == C.ROBOT_CHARGING:
        cand.reason = f"Charging ({robot.battery:.0f}%), not assignable"
        return cand
    if robot.status != C.ROBOT_IDLE or robot.task_id is not None:
        cand.reason = f"Busy ({robot.status}{', ' + robot.task_id if robot.task_id else ''})"
        return cand

    pickup: Cell = (task.pickup["x"], task.pickup["y"])
    dest: Cell = (task.destination["x"], task.destination["y"])
    others = sim.occupied_cells(exclude_id=robot.id)

    for label, cell in (("pickup", pickup), ("destination", dest)):
        stuck = next((r for r in sim.robots if r.cell == cell and r.status == C.ROBOT_OFFLINE), None)
        if stuck is not None:
            cand.reason = f"The {label} cell is occupied by offline robot {stuck.id}"
            return cand

    path1 = astar(sim.warehouse, robot.cell, pickup, extra_blocked=others)
    if path1 is None:
        if astar(sim.warehouse, robot.cell, pickup) is None:
            cand.reason = "No route to pickup (blocked by obstacles)"
        else:
            cand.reason = "Boxed in: path to pickup is blocked by other robots"
        return cand
    path2 = astar(sim.warehouse, pickup, dest)
    if path2 is None:
        cand.reason = "No route from pickup to destination (blocked by obstacles)"
        return cand
    return_cells = _nearest_charging_distance(sim, dest)
    if return_cells is None:
        cand.reason = "No route from destination back to the charging station"
        return cand

    d1, d2 = len(path1) - 1, len(path2) - 1
    needed = rules.estimate_route_battery(d1, d2, return_cells, task.load_pct) + sim.safety_reserve
    cand.route_distance = d1 + d2
    cand.battery_needed_pct = needed
    cand.path_to_pickup, cand.path_to_destination = path1, path2
    if robot.battery < needed:
        cand.reason = (
            f"Battery {robot.battery:.0f}% is below the {needed:.1f}% needed "
            f"(route + return + {sim.safety_reserve:.0f}% reserve)"
        )
        return cand

    congestion = congestion_score(
        sim.robots, queued=queued, cells=list(path1) + list(path2[1:]), exclude_id=robot.id, extra_active=1
    )
    cand.congestion = congestion
    cand.features = {
        "route_distance": float(d1 + d2),
        "battery_pct": float(robot.battery),
        "load_pct": float(task.load_pct),
        "queued_tasks": float(queued),
        "congestion": float(congestion),
        "priority": float(task.priority_value),
    }
    cand.baseline_seconds = rules.baseline_estimate_seconds(d1 + d2)
    cand.feasible = True
    cand.reason = "Feasible"
    return cand


def evaluate_candidates(sim: Simulation, task: Task) -> list[Candidate]:
    queued = max(len(sim.pending_tasks()) - 1, 0)   # other tasks waiting in the queue
    return [evaluate_candidate(sim, task, robot, queued) for robot in sim.robots]


# --------------------------------------------------------------------------- scoring
def _score(cands: list[Candidate], kind: str, predictor: Optional[Predictor]) -> None:
    feasible = [c for c in cands if c.feasible]
    if not feasible:
        return
    if kind == "ai":
        if predictor is None or not predictor.available:
            message = getattr(predictor, "error", None) or "The TensorFlow model is not loaded."
            raise ModelUnavailable(
                f"AI dispatch is unavailable: {message} Train the model with `python ml/train_model.py` "
                "and restart the backend, or use the baseline dispatcher."
            )
        matrix = np.array([[c.features[name] for name in C.FEATURE_NAMES] for c in feasible], dtype=np.float32)
        predictions = np.asarray(predictor.predict(matrix), dtype=float).reshape(-1)
        if predictions.shape[0] != len(feasible):
            raise ModelUnavailable("The model returned an unexpected number of predictions.")
        for cand, value in zip(feasible, predictions):
            cand.predicted_seconds = float(value)
    else:
        for cand in feasible:
            cand.predicted_seconds = float(cand.baseline_seconds)


def _rejection_summary(cands: list[Candidate], any_idle: bool) -> str:
    if not any_idle:
        states = ", ".join(f"{c.robot_id}: {c.reason}" for c in cands)
        return f"No suitable robot available - every robot is busy, charging or offline ({states})."
    reasons = "; ".join(f"{c.robot_id}: {c.reason}" for c in cands if c.reason != "Feasible")
    return f"No feasible robot ({reasons})."


def _explain(task: Task, chosen: Candidate, cands: list[Candidate], kind: str, reserve: float) -> str:
    feasible = sorted((c for c in cands if c.feasible), key=lambda c: (c.predicted_seconds, c.robot_id))
    if kind == "ai":
        head = (
            f"{chosen.robot_id} was selected because it has the lowest TensorFlow-predicted completion time "
            f"({chosen.predicted_seconds:.1f} s) among {len(feasible)} feasible robot(s)."
        )
    else:
        head = (
            f"{chosen.robot_id} was selected because it has the lowest baseline estimate "
            f"({chosen.predicted_seconds:.1f} s = route x {C.TICK_SECONDS:.0f} s + {C.HANDLING_SECONDS:.0f} s handling) "
            f"among {len(feasible)} feasible robot(s)."
        )
    parts = [head]
    if len(feasible) > 1:
        runner = feasible[1]
        parts.append(f"Next best: {runner.robot_id} at {runner.predicted_seconds:.1f} s.")
    parts.append(
        f"Route {chosen.route_distance} cells, battery {chosen.battery_pct:.0f}% "
        f"(needs {chosen.battery_needed_pct:.1f}% including a {reserve:.0f}% reserve), "
        f"congestion {chosen.congestion:.2f}, {task.priority} priority."
    )
    rejected = [c for c in cands if not c.feasible]
    if rejected:
        parts.append("Not eligible: " + "; ".join(f"{c.robot_id} ({c.reason})" for c in rejected) + ".")
    return " ".join(parts)


# --------------------------------------------------------------------------- main entry points
def dispatch_next(
    sim: Simulation,
    predictor: Optional[Predictor],
    kind: str = "ai",
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    """Assign the next pending task (or `task_id`) to the best feasible robot.

    Returns a dict with `assigned` (bool), a readable `message`, and the decision.
    Tasks that cannot be served right now stay pending.
    """
    if kind not in DISPATCHERS:
        raise InvalidRequest(f"Dispatcher must be one of: {', '.join(DISPATCHERS)}.")

    if task_id is not None:
        task = sim.task_by_id(task_id)
        if task.status != C.TASK_PENDING:
            raise Conflict(f"Task {task.id} is {task.status}, not Pending; it cannot be dispatched again.")
        queue = [task]
    else:
        queue = sim.pending_tasks()

    if not queue:
        return {"assigned": False, "message": "There are no pending tasks to dispatch.",
                "task_id": None, "robot_id": None, "decision": None, "skipped": []}

    any_idle = any(r.status == C.ROBOT_IDLE for r in sim.robots)
    skipped: list[dict] = []
    for task in queue:
        cands = evaluate_candidates(sim, task)
        if not any(c.feasible for c in cands):
            summary = _rejection_summary(cands, any_idle)
            sim.record_rejection(task, summary, infeasible=any_idle)
            skipped.append({"task_id": task.id, "reason": summary})
            continue

        _score(cands, kind, predictor)
        feasible = [c for c in cands if c.feasible]
        chosen = min(feasible, key=lambda c: (c.predicted_seconds, c.robot_id))
        robot = sim.robot_by_id(chosen.robot_id)
        route = list(chosen.path_to_pickup) + list(chosen.path_to_destination[1:])
        decision = {
            "task_id": task.id,
            "robot_id": chosen.robot_id,
            "dispatcher": kind,
            "estimator": "tensorflow" if kind == "ai" else "baseline_formula",
            "predicted_seconds": round(chosen.predicted_seconds, 2),
            "route_distance": chosen.route_distance,
            "battery_pct": round(chosen.battery_pct, 1),
            "battery_needed_pct": round(chosen.battery_needed_pct, 1),
            "features": dict(chosen.features),
            "route": [{"x": c[0], "y": c[1]} for c in route],
            "candidates": [c.to_dict() for c in cands],
            "explanation": _explain(task, chosen, cands, kind, sim.safety_reserve),
            "_path_to_pickup": chosen.path_to_pickup,
            "_path_to_destination": chosen.path_to_destination,
        }
        public = sim.commit_assignment(task, robot, decision)
        return {
            "assigned": True,
            "message": f"{robot.id} assigned to {task.id}.",
            "task_id": task.id, "robot_id": robot.id, "decision": public, "skipped": skipped,
        }

    message = skipped[0]["reason"] if len(skipped) == 1 else (
        f"None of the {len(skipped)} pending tasks can be assigned right now. {skipped[0]['reason']}"
    )
    return {"assigned": False, "message": message, "task_id": skipped[0]["task_id"],
            "robot_id": None, "decision": None, "skipped": skipped}


def advance(
    sim: Simulation,
    predictor: Optional[Predictor],
    steps: int = 1,
    auto_dispatch: bool = False,
    kind: str = "ai",
) -> dict[str, Any]:
    """Advance the simulation `steps` ticks, optionally dispatching before each tick."""
    assignments: list[dict] = []
    events: list[dict] = []
    for _ in range(steps):
        if auto_dispatch:
            while True:
                result = dispatch_next(sim, predictor, kind)
                if not result["assigned"]:
                    break
                assignments.append({"task_id": result["task_id"], "robot_id": result["robot_id"]})
        events.extend(sim.step())
    return {"steps": steps, "assignments": assignments, "events": events}
