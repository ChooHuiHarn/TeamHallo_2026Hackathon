"""Plain data classes for robots and tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import config as C
from .warehouse import Cell


@dataclass
class Task:
    id: str
    seq: int
    pickup: dict            # {"x": int, "y": int, "zone": str | None}
    destination: dict
    priority: str           # "Low" | "Normal" | "Urgent"
    load_pct: float
    status: str = C.TASK_PENDING
    created_at: str = ""            # wall-clock ISO time (display only)
    created_sim_time: float = 0.0   # simulated seconds
    assigned_robot: Optional[str] = None
    assigned_sim_time: Optional[float] = None
    started_sim_time: Optional[float] = None
    completed_sim_time: Optional[float] = None
    predicted_seconds: Optional[float] = None
    actual_seconds: Optional[float] = None
    route_distance: Optional[int] = None
    dispatcher: Optional[str] = None
    last_rejection: Optional[str] = None

    @property
    def priority_value(self) -> int:
        return C.PRIORITY_VALUES[self.priority]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pickup": dict(self.pickup),
            "destination": dict(self.destination),
            "priority": self.priority,
            "load_pct": self.load_pct,
            "status": self.status,
            "created_at": self.created_at,
            "created_sim_time": self.created_sim_time,
            "assigned_robot": self.assigned_robot,
            "assigned_sim_time": self.assigned_sim_time,
            "started_sim_time": self.started_sim_time,
            "completed_sim_time": self.completed_sim_time,
            "predicted_seconds": None if self.predicted_seconds is None else round(self.predicted_seconds, 1),
            "actual_seconds": None if self.actual_seconds is None else round(self.actual_seconds, 1),
            "route_distance": self.route_distance,
            "dispatcher": self.dispatcher,
            "last_rejection": self.last_rejection,
        }


@dataclass
class Robot:
    id: str
    x: int
    y: int
    battery: float = 100.0
    load_pct: float = 0.0
    status: str = C.ROBOT_IDLE
    task_id: Optional[str] = None
    # phase: none | start_delay | to_pickup | loading | to_dest | unloading | returning
    phase: str = "none"
    path: list[Cell] = field(default_factory=list)       # remaining cells of the current leg
    dest_plan: list[Cell] = field(default_factory=list)  # planned pickup -> destination cells
    start_delay: int = 0
    phase_timer: int = 0
    progress: float = 0.0
    wait_ticks: int = 0
    leg_blocked: int = 0          # blocked ticks on the current leg (not reset by moving)
    charge_target: Optional[Cell] = None
    flagged_critical: bool = False
    # statistics
    distance_travelled: int = 0
    idle_ticks: int = 0
    busy_ticks: int = 0
    charging_ticks: int = 0
    offline_ticks: int = 0
    tasks_completed: int = 0
    stuck_events: int = 0

    @property
    def cell(self) -> Cell:
        return (self.x, self.y)

    def route_points(self) -> tuple[list[dict], Optional[str]]:
        """Cells the robot still plans to visit (current cell first) and the route kind."""
        if self.status not in (C.ROBOT_ASSIGNED, C.ROBOT_MOVING):
            return [], None
        cells: list[Cell] = [self.cell] + list(self.path)
        kind = "returning" if self.phase == "returning" else "delivery"
        if kind == "delivery" and self.phase in ("start_delay", "to_pickup", "loading"):
            cells += list(self.dest_plan)
        return [{"x": c[0], "y": c[1]} for c in cells], kind

    def to_dict(self, tick_seconds: float = C.TICK_SECONDS) -> dict:
        route, kind = self.route_points()
        target = None
        if self.path:
            target = {"x": self.path[-1][0], "y": self.path[-1][1]}
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "battery": round(self.battery, 1),
            "load_pct": round(self.load_pct, 1),
            "status": self.status,
            "task_id": self.task_id,
            "phase": self.phase,
            "route": route,
            "route_kind": kind,
            "target": target,
            "distance_travelled": self.distance_travelled,
            "tasks_completed": self.tasks_completed,
            "idle_s": round(self.idle_ticks * tick_seconds, 1),
            "busy_s": round(self.busy_ticks * tick_seconds, 1),
            "charging_s": round(self.charging_ticks * tick_seconds, 1),
            "offline_s": round(self.offline_ticks * tick_seconds, 1),
            "wait_ticks": self.wait_ticks,
        }
