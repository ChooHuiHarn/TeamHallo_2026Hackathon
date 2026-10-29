"""Pydantic request and response models for the REST API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------------- requests
class LocationIn(BaseModel):
    """A warehouse location: either a zone id, or x/y grid coordinates."""
    zone: Optional[str] = Field(None, description="Zone id such as 'receiving' or 'shipping'")
    x: Optional[int] = Field(None, description="Column (0-9)")
    y: Optional[int] = Field(None, description="Row (0-7)")


class TaskCreateIn(BaseModel):
    pickup: LocationIn
    destination: LocationIn
    priority: Literal["Low", "Normal", "Urgent"] = "Normal"
    load_pct: float = Field(30.0, ge=0, le=100, description="Package load as % of robot capacity")


class DispatchIn(BaseModel):
    dispatcher: Literal["ai", "baseline"] = "ai"
    task_id: Optional[str] = Field(None, description="Dispatch this task; default is the next by priority/FIFO")


class StepIn(BaseModel):
    steps: int = Field(1, ge=1, le=500)
    auto_dispatch: bool = False
    dispatcher: Literal["ai", "baseline"] = "ai"


class ResetIn(BaseModel):
    safety_reserve: Optional[float] = Field(None, ge=0, le=50)


class RobotPatchIn(BaseModel):
    battery: Optional[float] = Field(None, ge=0, le=100)
    offline: Optional[bool] = None


class ObstacleIn(BaseModel):
    x: int
    y: int
    blocked: bool = True


class ConfigIn(BaseModel):
    safety_reserve: float = Field(..., ge=0, le=50, description="Battery % that must remain after a task")


class ExperimentIn(BaseModel):
    seed: int = Field(42, ge=0, le=1_000_000)
    runs: int = Field(3, ge=1, le=10, description="Number of scenarios (seeds seed .. seed+runs-1)")
    num_tasks: int = Field(12, ge=1, le=40)
    arrival: Literal["burst", "staggered", "sparse"] = "burst"
    safety_reserve: Optional[float] = Field(None, ge=0, le=50)
    max_steps: int = Field(600, ge=50, le=2000)


# ----------------------------------------------------------------------------- responses
class CellOut(BaseModel):
    x: int
    y: int


class LocationOut(BaseModel):
    x: int
    y: int
    zone: Optional[str] = None


class ZoneOut(BaseModel):
    id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    color: str
    dock: CellOut
    description: str


class WarehouseOut(BaseModel):
    width: int
    height: int
    zones: list[ZoneOut]
    obstacles: list[CellOut]


class RobotOut(BaseModel):
    id: str
    x: int
    y: int
    battery: float
    load_pct: float
    status: str
    task_id: Optional[str] = None
    phase: str
    route: list[CellOut]
    route_kind: Optional[str] = None
    target: Optional[CellOut] = None
    distance_travelled: int
    tasks_completed: int
    idle_s: float
    busy_s: float
    charging_s: float
    offline_s: float
    wait_ticks: int


class TaskOut(BaseModel):
    id: str
    pickup: LocationOut
    destination: LocationOut
    priority: str
    load_pct: float
    status: str
    created_at: str
    created_sim_time: float
    assigned_robot: Optional[str] = None
    assigned_sim_time: Optional[float] = None
    started_sim_time: Optional[float] = None
    completed_sim_time: Optional[float] = None
    predicted_seconds: Optional[float] = None
    actual_seconds: Optional[float] = None
    route_distance: Optional[int] = None
    dispatcher: Optional[str] = None
    last_rejection: Optional[str] = None


class EventOut(BaseModel):
    id: int
    type: str
    message: str
    robot_id: Optional[str] = None
    task_id: Optional[str] = None
    tick: int
    sim_time: float


class CandidateOut(BaseModel):
    robot_id: str
    feasible: bool
    reason: str
    battery_pct: float
    route_distance: Optional[int] = None
    battery_needed_pct: Optional[float] = None
    congestion: Optional[float] = None
    predicted_seconds: Optional[float] = None
    baseline_seconds: Optional[float] = None


class DecisionOut(BaseModel):
    id: str
    task_id: str
    robot_id: str
    dispatcher: str
    estimator: str
    predicted_seconds: float
    route_distance: int
    battery_pct: float
    battery_needed_pct: float
    features: dict[str, float]
    route: list[CellOut]
    candidates: list[CandidateOut]
    explanation: str
    sim_time: float
    tick: int


class SimOut(BaseModel):
    tick: int
    time_s: float
    tick_seconds: float
    status: str


class SummaryOut(BaseModel):
    total_robots: int
    available_robots: int
    robots_by_status: dict[str, int]
    active_tasks: int
    pending_tasks: int
    completed_tasks: int
    total_tasks: int
    battery_avg: float
    battery_min: float
    battery_max: float
    low_battery_robots: int


class ConfigOut(BaseModel):
    safety_reserve: float
    tick_seconds: float
    grid_width: int
    grid_height: int


class ModelStatusOut(BaseModel):
    available: bool
    status: str
    version: Optional[str] = None
    error: Optional[str] = None
    trained_on: Optional[str] = None


class StateOut(BaseModel):
    sim: SimOut
    warehouse: WarehouseOut
    robots: list[RobotOut]
    tasks: list[TaskOut]
    events: list[EventOut]
    summary: SummaryOut
    last_decision: Optional[DecisionOut] = None
    config: ConfigOut
    model: ModelStatusOut


class HealthOut(BaseModel):
    status: str
    app: str
    simulation: SimOut
    model: ModelStatusOut


class SkippedOut(BaseModel):
    task_id: str
    reason: str


class DispatchOut(BaseModel):
    assigned: bool
    message: str
    task_id: Optional[str] = None
    robot_id: Optional[str] = None
    decision: Optional[DecisionOut] = None
    skipped: list[SkippedOut] = []


class AssignmentOut(BaseModel):
    task_id: str
    robot_id: str


class StepOut(BaseModel):
    steps: int
    assignments: list[AssignmentOut]
    events: list[EventOut]
    sim: SimOut


class MetricsOut(BaseModel):
    model: dict[str, Any]
    evaluation: dict[str, Any]
    test_predictions: list[dict[str, float]]
    live_prediction: dict[str, Any]
    dispatch: dict[str, Any]
    decisions: list[DecisionOut]
    disclaimer: str
