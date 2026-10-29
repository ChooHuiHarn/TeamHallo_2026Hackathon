"""Central configuration for FleetPilot AI.

Every tunable number used by the simulation, the dispatcher and the synthetic
dataset generator lives here, so the "documented simulation rules" are in one
place. The training data generator (ml/generate_dataset.py) imports the same
constants, which keeps the learned model and the simulator describing the same
(simplified) warehouse.

THIS IS A COMPUTER SIMULATION. Nothing here controls real robots.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.environ.get("FLEETPILOT_MODELS_DIR", PROJECT_ROOT / "models"))
MODEL_PATH = MODELS_DIR / "duration_model.keras"
PREPROCESSING_PATH = MODELS_DIR / "preprocessing.json"
METADATA_PATH = MODELS_DIR / "metadata.json"
TEST_PREDICTIONS_PATH = MODELS_DIR / "test_predictions.json"

# --------------------------------------------------------------------------- grid
GRID_WIDTH = 10   # columns (x = 0..9)
GRID_HEIGHT = 8   # rows    (y = 0..7, y = 0 is the top row)

# --------------------------------------------------------------------------- time
TICK_SECONDS = 2.0          # one simulation step = 2 simulated seconds
LOAD_TICKS = 3              # ticks to load a package at pickup (and to unload)
HANDLING_SECONDS = 2 * LOAD_TICKS * TICK_SECONDS   # 12 s of loading + unloading

# --------------------------------------------------------------------------- battery
BATTERY_PER_CELL = 0.8          # % of battery used per cell travelled (empty robot)
LOAD_DRAIN_FACTOR = 0.005       # extra drain per % of load (100 % load -> +50 %)
HANDLING_BATTERY = 0.5          # % used for the whole load + unload operation
DEFAULT_SAFETY_RESERVE = 10.0   # % that must remain after a task (configurable)
CRITICAL_BATTERY = 5.0          # an active robot below this is a constraint violation
CHARGE_PER_TICK = 4.0           # % gained per tick while charging
CHARGE_START_BELOW = 80.0       # on docking, charge only if battery is below this
CHARGE_DONE = 95.0              # charging finishes at this level
RETURN_TO_CHARGE_BELOW = 50.0   # after a task, robots below this go to charge; others stay where they are
AUTO_CHARGE_BELOW = 35.0        # idle robots below this battery level go to charge by themselves

# --------------------------------------------------------------------------- movement rules
# A robot normally covers one cell per tick (2 s). Three factors slow it down:
BATTERY_SLOW_THRESHOLD = 30.0   # below this battery %, robots slow down
BATTERY_SLOW_MAX = 0.50         # up to +50 % travel time at 0 % battery
LOAD_SLOW_MAX = 0.25            # up to +25 % travel time at 100 % load
CONGESTION_SLOW_MAX = 0.80      # up to +80 % travel time at congestion = 1
# Urgent tasks get right of way: only this share of the congestion penalty applies.
PRIORITY_CONGESTION_RELIEF = {0: 1.0, 1: 1.0, 2: 0.6}
QUEUE_DELAY_MAX_TICKS = 4       # dispatcher backlog delay is capped at 4 ticks (8 s)

REPLAN_AFTER_WAITS = 3          # blocked this many ticks -> re-plan around robots
STUCK_LIMIT = 20                # blocked this many ticks -> side-step

# --------------------------------------------------------------------------- priorities
PRIORITY_NAMES = {0: "Low", 1: "Normal", 2: "Urgent"}
PRIORITY_VALUES = {name: value for value, name in PRIORITY_NAMES.items()}

# --------------------------------------------------------------------------- ML
FEATURE_NAMES = [
    "route_distance",   # cells: robot -> pickup + pickup -> destination
    "battery_pct",      # robot battery at assignment time
    "load_pct",         # load the robot will carry for this task
    "queued_tasks",     # other tasks waiting in the queue
    "congestion",       # 0..1
    "priority",         # 0 Low, 1 Normal, 2 Urgent
]
MIN_PREDICTION_SECONDS = 1.0    # model output is clamped to at least this

# --------------------------------------------------------------------------- statuses
ROBOT_IDLE = "Idle"
ROBOT_ASSIGNED = "Assigned"
ROBOT_MOVING = "Moving"
ROBOT_CHARGING = "Charging"
ROBOT_OFFLINE = "Offline"
ROBOT_STATUSES = [ROBOT_IDLE, ROBOT_ASSIGNED, ROBOT_MOVING, ROBOT_CHARGING, ROBOT_OFFLINE]

TASK_PENDING = "Pending"
TASK_ASSIGNED = "Assigned"
TASK_IN_PROGRESS = "In Progress"
TASK_COMPLETED = "Completed"

# Starting state (deterministic): robot id -> (x, y, battery %)
NUM_ROBOTS = 6
INITIAL_BATTERIES = [100.0, 94.0, 86.0, 72.0, 58.0, 100.0]

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "FLEETPILOT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if o.strip()
]
