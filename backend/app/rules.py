"""Pure functions describing the simulation rules.

These functions are shared by:
  * the simulator (app/simulation.py)   - to move robots tick by tick,
  * the dispatcher (app/dispatch.py)    - to estimate battery use,
  * the dataset generator (ml/generate_dataset.py) - to create training data,
  * the non-AI baseline                 - to estimate durations.

Keeping them in one module means the rules are documented once.
"""
from __future__ import annotations

from . import config as C


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ----------------------------------------------------------------- movement multipliers
def battery_multiplier(battery_pct: float) -> float:
    """Travel-time multiplier from battery level (1.0 above the threshold)."""
    deficit = (C.BATTERY_SLOW_THRESHOLD - battery_pct) / C.BATTERY_SLOW_THRESHOLD
    return 1.0 + C.BATTERY_SLOW_MAX * clamp(deficit, 0.0, 1.0)


def load_multiplier(load_pct: float) -> float:
    """Travel-time multiplier from the carried load."""
    return 1.0 + C.LOAD_SLOW_MAX * clamp(load_pct, 0.0, 100.0) / 100.0


def congestion_multiplier(congestion: float, priority: int) -> float:
    """Travel-time multiplier from congestion; urgent tasks get right of way."""
    relief = C.PRIORITY_CONGESTION_RELIEF.get(int(priority), 1.0)
    return 1.0 + C.CONGESTION_SLOW_MAX * clamp(congestion, 0.0, 1.0) * relief


def movement_multiplier(battery_pct: float, load_pct: float, congestion: float, priority: int) -> float:
    """Seconds-per-cell is TICK_SECONDS times this value."""
    return (
        battery_multiplier(battery_pct)
        * load_multiplier(load_pct)
        * congestion_multiplier(congestion, priority)
    )


def queue_delay_ticks(queued_tasks: int) -> int:
    """Dispatcher backlog: every 2 queued tasks add one tick of start delay (max 4)."""
    return int(min(max(queued_tasks, 0) // 2, C.QUEUE_DELAY_MAX_TICKS))


# ----------------------------------------------------------------- battery
def drain_per_cell(load_pct: float) -> float:
    return C.BATTERY_PER_CELL * (1.0 + C.LOAD_DRAIN_FACTOR * clamp(load_pct, 0.0, 100.0))


def estimate_route_battery(pickup_cells: int, delivery_cells: int, return_cells: int, load_pct: float) -> float:
    """Battery % expected for: robot -> pickup, pickup -> destination (loaded),
    destination -> charging station, plus the load/unload operation."""
    return (
        drain_per_cell(0.0) * (pickup_cells + return_cells)
        + drain_per_cell(load_pct) * delivery_cells
        + C.HANDLING_BATTERY
    )


# ----------------------------------------------------------------- baseline estimator
def baseline_estimate_seconds(route_distance: float) -> float:
    """Documented non-AI formula:

        duration = route_distance * TICK_SECONDS (assumed speed 1 cell per tick)
                   + HANDLING_SECONDS (loading + unloading)

    It ignores battery, load, congestion, queue length and priority.
    """
    return route_distance * C.TICK_SECONDS + C.HANDLING_SECONDS


# ----------------------------------------------------------------- generator ground truth
def expected_duration_seconds(
    route_distance: float,
    battery_pct: float,
    load_pct: float,
    queued_tasks: int,
    congestion: float,
    priority: int,
    pickup_fraction: float = 0.4,
) -> float:
    """Noise-free expected task duration used by the synthetic data generator.

    The robot is empty on the way to the pickup (a share `pickup_fraction` of the
    route) and loaded on the way to the destination.
    """
    d_pickup = route_distance * pickup_fraction
    d_deliver = route_distance - d_pickup
    travel = (
        C.TICK_SECONDS
        * battery_multiplier(battery_pct)
        * congestion_multiplier(congestion, priority)
        * (d_pickup + d_deliver * load_multiplier(load_pct))
    )
    return travel + C.HANDLING_SECONDS + queue_delay_ticks(queued_tasks) * C.TICK_SECONDS
