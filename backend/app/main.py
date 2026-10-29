"""FleetPilot AI - FastAPI application.

Run from the `backend/` folder:   uvicorn app.main:app --reload --port 8000

This API drives a computer simulation of a warehouse. It does not control real robots.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config as C
from . import experiments
from .dispatch import advance, dispatch_next
from .errors import FleetError
from .ml.predictor import DurationPredictor
from .models import (
    ConfigIn, ConfigOut, DispatchIn, DispatchOut, ExperimentIn, HealthOut, MetricsOut,
    ObstacleIn, ResetIn, RobotOut, RobotPatchIn, StateOut, StepIn, StepOut, TaskCreateIn,
    TaskOut, WarehouseOut,
)
from .simulation import Simulation

APP_NAME = "FleetPilot AI"
APP_VERSION = "1.0.0"
DISCLAIMER = (
    "FleetPilot AI is a computer simulation. The TensorFlow model is trained on synthetic data generated "
    "from documented simulation rules; its accuracy does not establish real-world warehouse accuracy."
)


class FleetState:
    """The single in-memory simulation, the model, and a lock (requests run in threads)."""

    def __init__(self, predictor: Optional[Any] = None):
        self.sim = Simulation()
        self.predictor = predictor if predictor is not None else DurationPredictor()
        self.lock = threading.RLock()


def get_fleet(request: Request) -> FleetState:
    return request.app.state.fleet


router = APIRouter(prefix="/api")


def _model_status(fleet: FleetState) -> dict:
    status = getattr(fleet.predictor, "status", None)
    if callable(status):
        return status()
    return {"available": bool(fleet.predictor.available), "status": "Loaded" if fleet.predictor.available else "Unavailable",
            "version": None, "error": getattr(fleet.predictor, "error", None), "trained_on": None}


def _snapshot(fleet: FleetState) -> dict:
    data = fleet.sim.snapshot()
    data["model"] = _model_status(fleet)
    return data


# ----------------------------------------------------------------------------- health / state
@router.get("/health", response_model=HealthOut)
def health(fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        snap = fleet.sim.snapshot(event_limit=0)
        return {"status": "ok", "app": APP_NAME, "simulation": snap["sim"], "model": _model_status(fleet)}


@router.get("/state", response_model=StateOut)
def get_state(fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        return _snapshot(fleet)


# ----------------------------------------------------------------------------- robots
@router.get("/robots", response_model=list[RobotOut])
def list_robots(fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        return [r.to_dict() for r in fleet.sim.robots]


@router.get("/robots/{robot_id}", response_model=RobotOut)
def get_robot(robot_id: str, fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        return fleet.sim.robot_by_id(robot_id).to_dict()


@router.patch("/robots/{robot_id}", response_model=RobotOut)
def patch_robot(robot_id: str, body: RobotPatchIn, fleet: FleetState = Depends(get_fleet)):
    """Demonstration control: set a robot's battery or take it offline / back online."""
    with fleet.lock:
        return fleet.sim.patch_robot(robot_id, battery=body.battery, offline=body.offline).to_dict()


# ----------------------------------------------------------------------------- tasks
@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        return [t.to_dict() for t in fleet.sim.tasks]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreateIn, fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        task = fleet.sim.create_task(
            pickup=body.pickup.model_dump(),
            destination=body.destination.model_dump(),
            priority=body.priority,
            load_pct=body.load_pct,
        )
        return task.to_dict()


# ----------------------------------------------------------------------------- dispatch
@router.post("/dispatch/next", response_model=DispatchOut)
def dispatch(body: Optional[DispatchIn] = None, fleet: FleetState = Depends(get_fleet)):
    body = body or DispatchIn()
    with fleet.lock:
        return dispatch_next(fleet.sim, fleet.predictor, body.dispatcher, body.task_id)


# ----------------------------------------------------------------------------- simulation
@router.post("/simulation/step", response_model=StepOut)
def step(body: Optional[StepIn] = None, fleet: FleetState = Depends(get_fleet)):
    body = body or StepIn()
    with fleet.lock:
        result = advance(fleet.sim, fleet.predictor, body.steps, body.auto_dispatch, body.dispatcher)
        result["sim"] = fleet.sim.snapshot(event_limit=0)["sim"]
        return result


@router.post("/simulation/reset", response_model=StateOut)
def reset(body: Optional[ResetIn] = None, fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        if body is not None and body.safety_reserve is not None:
            fleet.sim.safety_reserve = float(body.safety_reserve)
        else:
            fleet.sim.safety_reserve = C.DEFAULT_SAFETY_RESERVE
        fleet.sim.reset()
        return _snapshot(fleet)


@router.post("/map/obstacles", response_model=WarehouseOut)
def set_obstacle(body: ObstacleIn, fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        fleet.sim.set_obstacle(body.x, body.y, body.blocked)
        return fleet.sim.warehouse.to_dict()


@router.patch("/config", response_model=ConfigOut)
def update_config(body: ConfigIn, fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        fleet.sim.safety_reserve = float(body.safety_reserve)
        return fleet.sim.snapshot(event_limit=0)["config"]


# ----------------------------------------------------------------------------- metrics / experiments
@router.get("/metrics", response_model=MetricsOut)
def metrics(fleet: FleetState = Depends(get_fleet)):
    with fleet.lock:
        meta_getter = getattr(fleet.predictor, "metadata", None)
        meta = meta_getter() if callable(meta_getter) else None
        points_getter = getattr(fleet.predictor, "test_predictions", None)
        points = points_getter() if callable(points_getter) else None
        model_metrics = (meta or {}).get("metrics") or {}
        test = model_metrics.get("test")
        if test:
            baseline = model_metrics.get("baseline_formula_test") or {}
            evaluation = {
                "status": "Evaluated",
                "dataset": "synthetic test split (held out from training)",
                "n_test": (meta or {}).get("split", {}).get("test"),
                "mae_s": test.get("mae"), "rmse_s": test.get("rmse"), "r2": test.get("r2"),
                "validation_mae_s": (model_metrics.get("validation") or {}).get("mae"),
                "baseline_formula_mae_s": baseline.get("mae"),
                "baseline_formula_rmse_s": baseline.get("rmse"),
            }
        else:
            evaluation = {"status": "Not evaluated", "mae_s": None, "rmse_s": None, "r2": None}
        return {
            "model": {**_model_status(fleet), "metadata": meta},
            "evaluation": evaluation,
            "test_predictions": points or [],
            "live_prediction": fleet.sim.live_prediction_accuracy(),
            "dispatch": fleet.sim.run_metrics(),
            "decisions": list(reversed(fleet.sim.decisions[-20:])),
            "disclaimer": DISCLAIMER,
        }


@router.post("/experiments/compare")
def compare(body: Optional[ExperimentIn] = None, fleet: FleetState = Depends(get_fleet)):
    body = body or ExperimentIn()
    with fleet.lock:
        reserve = body.safety_reserve if body.safety_reserve is not None else fleet.sim.safety_reserve
        return experiments.compare(
            fleet.predictor, seed=body.seed, runs=body.runs, num_tasks=body.num_tasks,
            arrival=body.arrival, safety_reserve=reserve, max_steps=body.max_steps,
        )


# ----------------------------------------------------------------------------- app factory
def create_app(predictor: Optional[Any] = None, load_model: bool = True) -> FastAPI:
    """Build the app. Tests pass their own predictor and `load_model=False`."""
    fleet = FleetState(predictor)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if load_model and hasattr(fleet.predictor, "load"):
            fleet.predictor.load()   # load the TensorFlow model once, at startup
        yield

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan,
                  description="REST API for the FleetPilot AI warehouse simulation (not real robots).")
    app.state.fleet = fleet
    app.add_middleware(
        CORSMiddleware, allow_origins=C.CORS_ORIGINS, allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(FleetError)
    async def fleet_error_handler(_: Request, exc: FleetError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        problems = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            problems.append(f"{where}: {err.get('msg')}" if where else str(err.get("msg")))
        return JSONResponse(status_code=422, content={"detail": "Invalid request - " + "; ".join(problems)})

    return app


app = create_app()
