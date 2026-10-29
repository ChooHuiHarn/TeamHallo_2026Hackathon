"""Deterministic warehouse simulation.

One call to `Simulation.step()` advances the world by one tick (2 simulated
seconds). Robots are processed in ID order, so the same sequence of requests
always produces the same result. There is no randomness inside the simulator.

This is a simulation; it does not control real robots.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from . import config as C
from . import rules
from .entities import Robot, Task
from .errors import Conflict, InvalidRequest, NotFound
from .pathfinding import astar, manhattan
from .warehouse import Cell, Warehouse

MAX_EVENTS = 300
MAX_DECISIONS = 200


# --------------------------------------------------------------------------- congestion
def congestion_score(
    robots: list[Robot],
    queued: int,
    cells: list[Cell],
    exclude_id: Optional[str] = None,
    extra_active: int = 0,
) -> float:
    """Congestion between 0 and 1.

        0.5 * share of robots that are working
      + 0.3 * local density (other robots within 2 cells of the sampled cells)
      + 0.2 * queue pressure (queued tasks / 10, capped)

    `cells` are the cells to sample (the robot's own cell during the simulation,
    or the candidate route when the dispatcher plans an assignment).
    `extra_active` counts a candidate robot that is about to become active.
    """
    total = max(len(robots), 1)
    active = sum(1 for r in robots if r.status in (C.ROBOT_ASSIGNED, C.ROBOT_MOVING)) + extra_active
    busy_share = min(active / total, 1.0)
    densities = []
    for cx, cy in cells:
        near = sum(
            1 for r in robots
            if r.id != exclude_id and max(abs(r.x - cx), abs(r.y - cy)) <= 2
        )
        densities.append(min(near / 3.0, 1.0))
    local = sum(densities) / len(densities) if densities else 0.0
    queue = min(max(queued, 0), 10) / 10.0
    return rules.clamp(0.5 * busy_share + 0.3 * local + 0.2 * queue, 0.0, 1.0)


class Simulation:
    def __init__(
        self,
        safety_reserve: float = C.DEFAULT_SAFETY_RESERVE,
        initial_batteries: Optional[list[float]] = None,
    ):
        self.safety_reserve = float(safety_reserve)
        self._initial_batteries = list(initial_batteries) if initial_batteries else list(C.INITIAL_BATTERIES)
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def reset(self, initial_batteries: Optional[list[float]] = None) -> None:
        """Return to the known starting state (default layout, full fleet at the charging bays)."""
        if initial_batteries is not None:
            self._initial_batteries = list(initial_batteries)
        self.warehouse = Warehouse()
        self.tick = 0
        self.sim_time = 0.0
        self.tasks: list[Task] = []
        self.events: list[dict] = []
        self.decisions: list[dict] = []
        self.last_decision: Optional[dict] = None
        self._event_seq = 0
        self._task_seq = 0
        self._decision_seq = 0
        self.rejected_task_ids: set[str] = set()   # had an idle robot but none feasible
        self.waited_task_ids: set[str] = set()     # had to wait because no robot was idle
        self.violations: list[str] = []
        charging = self.warehouse.charging_cells()
        order = sorted(charging, key=lambda c: (c[1], c[0]))
        self.robots = []
        for i in range(C.NUM_ROBOTS):
            x, y = order[i]
            battery = self._initial_batteries[i] if i < len(self._initial_batteries) else 100.0
            robot = Robot(id=f"R{i + 1:02d}", x=x, y=y, battery=float(battery))
            if robot.battery < C.CHARGE_START_BELOW:
                robot.status = C.ROBOT_CHARGING   # docked and recharging at the start
            self.robots.append(robot)
        self.add_event("reset", "Simulation reset to the known starting state.")

    # ------------------------------------------------------------------ lookups
    def robot_by_id(self, robot_id: str) -> Robot:
        for robot in self.robots:
            if robot.id == robot_id:
                return robot
        raise NotFound(f"Robot '{robot_id}' does not exist.")

    def task_by_id(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise NotFound(f"Task '{task_id}' does not exist.")

    def _task_or_none(self, task_id: Optional[str]) -> Optional[Task]:
        if task_id is None:
            return None
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def occupied_cells(self, exclude_id: Optional[str] = None) -> set[Cell]:
        return {r.cell for r in self.robots if r.id != exclude_id}

    def pending_tasks(self) -> list[Task]:
        """Pending tasks ordered by priority (Urgent first), then FIFO."""
        pending = [t for t in self.tasks if t.status == C.TASK_PENDING]
        return sorted(pending, key=lambda t: (-t.priority_value, t.seq))

    def active_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status in (C.TASK_ASSIGNED, C.TASK_IN_PROGRESS)]

    def all_done(self) -> bool:
        return all(t.status == C.TASK_COMPLETED for t in self.tasks)

    # ------------------------------------------------------------------ events
    def add_event(self, kind: str, message: str, robot_id: Optional[str] = None, task_id: Optional[str] = None) -> dict:
        self._event_seq += 1
        event = {
            "id": self._event_seq,
            "type": kind,
            "message": message,
            "robot_id": robot_id,
            "task_id": task_id,
            "tick": self.tick,
            "sim_time": self.sim_time,
        }
        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]
        return event

    def _violation(self, message: str) -> None:
        self.violations.append(f"t={self.sim_time:.0f}s: {message}")
        self.add_event("violation", f"Constraint violation: {message}")

    # ------------------------------------------------------------------ tasks
    def resolve_location(self, loc: dict, label: str) -> dict:
        zone_id = loc.get("zone")
        x, y = loc.get("x"), loc.get("y")
        wh = self.warehouse
        if zone_id is not None and (x is not None or y is not None):
            raise InvalidRequest(f"{label}: give either a zone or x/y coordinates, not both.")
        if zone_id is not None:
            zone = wh.zone_by_id(zone_id)
            if zone is None:
                valid = ", ".join(z.id for z in wh.zones)
                raise InvalidRequest(f"{label}: unknown zone '{zone_id}'. Valid zones: {valid}.")
            x, y = zone.dock
        else:
            if x is None or y is None:
                raise InvalidRequest(f"{label}: give a zone or both x and y coordinates.")
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
                raise InvalidRequest(f"{label}: coordinates must be whole numbers.")
            if not wh.in_bounds(x, y):
                raise InvalidRequest(
                    f"{label}: ({x}, {y}) is outside the {wh.width} x {wh.height} warehouse grid "
                    f"(x 0-{wh.width - 1}, y 0-{wh.height - 1})."
                )
        if wh.is_blocked(x, y):
            raise InvalidRequest(f"{label}: ({x}, {y}) is a blocked cell (obstacle).")
        zone = wh.zone_at(x, y)
        if zone is not None and zone.id == "charging":
            raise InvalidRequest(
                f"{label}: ({x}, {y}) is inside the Charging Station, which is reserved for robot parking."
            )
        return {"x": x, "y": y, "zone": zone.id if zone else None}

    def create_task(self, pickup: dict, destination: dict, priority: str = "Normal", load_pct: float = 30.0) -> Task:
        if priority not in C.PRIORITY_VALUES:
            raise InvalidRequest(f"Priority must be one of: {', '.join(C.PRIORITY_VALUES)}.")
        if isinstance(load_pct, bool) or not isinstance(load_pct, (int, float)) or not 0 <= load_pct <= 100:
            raise InvalidRequest("Load must be a number between 0 and 100.")
        pick = self.resolve_location(pickup, "Pickup")
        dest = self.resolve_location(destination, "Destination")
        if (pick["x"], pick["y"]) == (dest["x"], dest["y"]):
            raise InvalidRequest("Pickup and destination must be different cells.")
        self._task_seq += 1
        task = Task(
            id=f"T{self._task_seq:03d}",
            seq=self._task_seq,
            pickup=pick,
            destination=dest,
            priority=priority,
            load_pct=float(load_pct),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            created_sim_time=self.sim_time,
        )
        self.tasks.append(task)
        self.add_event(
            "task_created",
            f"Task {task.id} created: ({pick['x']},{pick['y']}) -> ({dest['x']},{dest['y']}), {priority} priority.",
            task_id=task.id,
        )
        return task

    def record_rejection(self, task: Task, summary: str, infeasible: bool) -> None:
        """Remember why a task could not be assigned (keeps it pending, never drops it)."""
        if infeasible:
            self.rejected_task_ids.add(task.id)
        else:
            self.waited_task_ids.add(task.id)
        if task.last_rejection != summary:
            task.last_rejection = summary
            self.add_event("assignment_rejected", f"{task.id} not assigned: {summary}", task_id=task.id)

    def commit_assignment(self, task: Task, robot: Robot, decision: dict) -> dict:
        """Record an assignment and update task and robot together.

        Raises Conflict if the task is not pending or the robot is not idle, so
        two jobs can never be given to one robot (or one job to two robots).
        """
        if task.status != C.TASK_PENDING:
            raise Conflict(f"Task {task.id} is already {task.status}; it cannot be assigned again.")
        if robot.status != C.ROBOT_IDLE or robot.task_id is not None:
            raise Conflict(f"Robot {robot.id} is {robot.status} and cannot take a new task.")
        route_to_pickup: list[Cell] = decision["_path_to_pickup"]
        route_to_dest: list[Cell] = decision["_path_to_destination"]
        delay = rules.queue_delay_ticks(int(decision["features"]["queued_tasks"]))

        self._decision_seq += 1
        decision["id"] = f"D{self._decision_seq:03d}"
        decision["sim_time"] = self.sim_time
        decision["tick"] = self.tick

        robot.status = C.ROBOT_ASSIGNED
        robot.task_id = task.id
        robot.path = list(route_to_pickup[1:])
        robot.dest_plan = list(route_to_dest[1:])
        robot.start_delay = delay
        robot.phase = "start_delay" if delay > 0 else "to_pickup"
        robot.progress = 0.0
        robot.wait_ticks = 0
        robot.leg_blocked = 0
        robot.charge_target = None
        robot.flagged_critical = False

        task.status = C.TASK_ASSIGNED
        task.assigned_robot = robot.id
        task.assigned_sim_time = self.sim_time
        task.predicted_seconds = decision["predicted_seconds"]
        task.route_distance = decision["route_distance"]
        task.dispatcher = decision["dispatcher"]
        task.last_rejection = None

        public = {k: v for k, v in decision.items() if not k.startswith("_")}
        self.last_decision = public
        self.decisions.append(public)
        if len(self.decisions) > MAX_DECISIONS:
            self.decisions = self.decisions[-MAX_DECISIONS:]
        self.add_event(
            "robot_assigned",
            f"{robot.id} assigned to {task.id} ({decision['dispatcher']} dispatcher, "
            f"predicted {decision['predicted_seconds']:.0f} s).",
            robot_id=robot.id, task_id=task.id,
        )
        return public

    # ------------------------------------------------------------------ robot controls
    def patch_robot(self, robot_id: str, battery: Optional[float] = None, offline: Optional[bool] = None) -> Robot:
        """Demonstration controls: set a battery level or take a robot offline / online."""
        robot = self.robot_by_id(robot_id)
        if battery is not None:
            if isinstance(battery, bool) or not isinstance(battery, (int, float)) or not 0 <= battery <= 100:
                raise InvalidRequest("Battery must be a number between 0 and 100.")
            robot.battery = float(battery)
            if battery >= C.CRITICAL_BATTERY:
                robot.flagged_critical = False
            self.add_event("robot_status", f"{robot.id} battery set to {robot.battery:.0f}%.", robot_id=robot.id)
        if offline is True and robot.status != C.ROBOT_OFFLINE:
            self._take_offline(robot, "taken offline by operator")
        elif offline is False and robot.status == C.ROBOT_OFFLINE:
            robot.status = C.ROBOT_IDLE
            robot.phase = "none"
            self.add_event("robot_status", f"{robot.id} is back online.", robot_id=robot.id)
            if self.warehouse.zone_at(*robot.cell) is None or self.warehouse.zone_at(*robot.cell).id != "charging":
                self._start_return(robot)
            elif robot.battery < C.CHARGE_START_BELOW:
                robot.status = C.ROBOT_CHARGING
        return robot

    def _release_task(self, robot: Robot, reason: str) -> None:
        task = self._task_or_none(robot.task_id)
        if task is not None and task.status != C.TASK_COMPLETED:
            task.status = C.TASK_PENDING
            task.assigned_robot = None
            task.assigned_sim_time = None
            task.started_sim_time = None
            task.predicted_seconds = None
            task.route_distance = None
            task.dispatcher = None
            self.add_event(
                "task_requeued", f"{task.id} returned to the pending queue ({reason}).",
                robot_id=robot.id, task_id=task.id,
            )
        robot.task_id = None
        robot.load_pct = 0.0
        robot.path = []
        robot.dest_plan = []
        robot.phase = "none"
        robot.progress = 0.0
        robot.wait_ticks = 0

    def _take_offline(self, robot: Robot, reason: str) -> None:
        self._release_task(robot, reason)
        robot.status = C.ROBOT_OFFLINE
        robot.charge_target = None
        self.add_event("robot_status", f"{robot.id} is offline ({reason}).", robot_id=robot.id)

    # ------------------------------------------------------------------ obstacles
    def set_obstacle(self, x: int, y: int, blocked: bool) -> None:
        wh = self.warehouse
        if not wh.in_bounds(x, y):
            raise InvalidRequest(f"({x}, {y}) is outside the {wh.width} x {wh.height} grid.")
        if blocked == wh.is_blocked(x, y):
            return  # already in the requested state
        if not blocked:
            wh.set_obstacle(x, y, False)
            self.add_event("obstacle", f"Obstacle removed at ({x},{y}).")
            return
        zone = wh.zone_at(x, y)
        if zone is not None and zone.id == "charging":
            raise InvalidRequest("Charging bays cannot be blocked.")
        if any(r.cell == (x, y) for r in self.robots):
            raise Conflict(f"A robot is standing at ({x}, {y}); it cannot be blocked right now.")
        for task in self.tasks:
            if task.status != C.TASK_COMPLETED:
                for end in (task.pickup, task.destination):
                    if (end["x"], end["y"]) == (x, y):
                        raise Conflict(f"({x}, {y}) is the pickup or destination of open task {task.id}.")
        # Tentatively block, then make sure every working robot can still finish.
        wh.set_obstacle(x, y, True)
        new_plans: dict[str, tuple[list[Cell], list[Cell]]] = {}
        for robot in self.robots:
            if robot.status not in (C.ROBOT_ASSIGNED, C.ROBOT_MOVING):
                continue
            path, dest_plan = list(robot.path), list(robot.dest_plan)
            if path:
                goal = path[-1]
                new_path = astar(wh, robot.cell, goal)
                if new_path is None:
                    wh.set_obstacle(x, y, False)
                    raise Conflict(f"Blocking ({x}, {y}) would leave {robot.id} without a route; not applied.")
                path = new_path[1:]
            if dest_plan and robot.phase in ("start_delay", "to_pickup", "loading"):
                start = robot.path[-1] if robot.path else robot.cell
                new_leg = astar(wh, start, dest_plan[-1])
                if new_leg is None:
                    wh.set_obstacle(x, y, False)
                    raise Conflict(f"Blocking ({x}, {y}) would leave {robot.id} without a route; not applied.")
                dest_plan = new_leg[1:]
            new_plans[robot.id] = (path, dest_plan)
        for robot_id, (path, dest_plan) in new_plans.items():
            robot = self.robot_by_id(robot_id)
            robot.path, robot.dest_plan = path, dest_plan
        self.add_event("obstacle", f"Obstacle placed at ({x},{y}); active routes were re-planned.")

    # ------------------------------------------------------------------ stepping
    def step(self) -> list[dict]:
        """Advance one tick. Returns the events created during this tick."""
        first_new = self._event_seq
        self.tick += 1
        self.sim_time = self.tick * C.TICK_SECONDS
        for robot in self.robots:
            if robot.status == C.ROBOT_OFFLINE:
                robot.offline_ticks += 1
            elif robot.status == C.ROBOT_CHARGING:
                self._charge(robot)
            elif robot.status == C.ROBOT_IDLE:
                self._idle_policy(robot)
                if robot.status == C.ROBOT_IDLE:
                    robot.idle_ticks += 1
                elif robot.status == C.ROBOT_CHARGING:
                    robot.charging_ticks += 1
                else:
                    robot.busy_ticks += 1
            else:
                self._advance_active(robot)
        self._audit()
        return [e for e in self.events if e["id"] > first_new]

    def _in_charging_zone(self, robot: Robot) -> bool:
        zone = self.warehouse.zone_at(*robot.cell)
        return zone is not None and zone.id == "charging"

    def _idle_policy(self, robot: Robot) -> None:
        """Idle robots stay where they are, but go to (or start) charging when their battery is low."""
        if self._in_charging_zone(robot):
            if robot.battery < C.CHARGE_START_BELOW:
                robot.status = C.ROBOT_CHARGING
                self.add_event(
                    "robot_charging", f"{robot.id} is charging at its bay ({robot.battery:.0f}%).", robot_id=robot.id
                )
        elif robot.battery < C.AUTO_CHARGE_BELOW:
            self._start_return(robot)

    def _charge(self, robot: Robot) -> None:
        robot.charging_ticks += 1
        robot.battery = min(100.0, robot.battery + C.CHARGE_PER_TICK)
        if robot.battery >= C.CRITICAL_BATTERY:
            robot.flagged_critical = False
        if robot.battery >= C.CHARGE_DONE:
            robot.status = C.ROBOT_IDLE
            self.add_event(
                "charging_complete", f"{robot.id} finished charging ({robot.battery:.0f}%).", robot_id=robot.id
            )

    def _advance_active(self, robot: Robot) -> None:
        robot.busy_ticks += 1
        task = self._task_or_none(robot.task_id)
        phase = robot.phase
        if phase == "start_delay":
            robot.start_delay -= 1
            if robot.start_delay <= 0:
                robot.phase = "to_pickup"
        elif phase in ("loading", "unloading"):
            self._drain(robot, C.HANDLING_BATTERY / (2 * C.LOAD_TICKS))
            if robot.status == C.ROBOT_OFFLINE:
                return
            robot.phase_timer -= 1
            if robot.phase_timer <= 0:
                if phase == "loading":
                    self._finish_loading(robot, task)
                else:
                    self._finish_unloading(robot, task)
        elif phase in ("to_pickup", "to_dest", "returning"):
            self._move(robot, task)

    def _drain(self, robot: Robot, amount: float) -> None:
        robot.battery = max(0.0, robot.battery - amount)
        if robot.battery <= 0.0 and robot.status != C.ROBOT_OFFLINE:
            self._violation(f"{robot.id} battery depleted while working")
            self._take_offline(robot, "battery depleted")
        elif (
            robot.battery < C.CRITICAL_BATTERY
            and not robot.flagged_critical
            and robot.status in (C.ROBOT_ASSIGNED, C.ROBOT_MOVING)
        ):
            robot.flagged_critical = True
            self._violation(f"{robot.id} battery fell below {C.CRITICAL_BATTERY:.0f}% ({robot.battery:.1f}%)")

    def _move(self, robot: Robot, task: Optional[Task]) -> None:
        if robot.status == C.ROBOT_ASSIGNED:
            robot.status = C.ROBOT_MOVING
            if robot.phase == "to_pickup" and task is not None:
                self.add_event(
                    "robot_moving", f"{robot.id} started moving to pickup for {task.id}.",
                    robot_id=robot.id, task_id=task.id,
                )
        if not robot.path:
            self._arrive(robot, task)
            return
        priority = task.priority_value if (task is not None and robot.phase != "returning") else 0
        congestion = congestion_score(
            self.robots, queued=len(self.pending_tasks()), cells=[robot.cell], exclude_id=robot.id
        )
        multiplier = rules.movement_multiplier(robot.battery, robot.load_pct, congestion, priority)
        robot.progress += 1.0 / multiplier
        if robot.progress < 1.0 - 1e-9:
            return  # still travelling inside the current cell
        nxt = robot.path[0]
        if nxt in self.occupied_cells(exclude_id=robot.id):
            self._blocked(robot, nxt)
            return
        robot.x, robot.y = nxt
        robot.path.pop(0)
        robot.progress = max(0.0, robot.progress - 1.0)
        robot.wait_ticks = 0
        robot.distance_travelled += 1
        self._drain(robot, rules.drain_per_cell(robot.load_pct))
        if robot.status == C.ROBOT_OFFLINE:
            return
        if not robot.path:
            self._arrive(robot, task)

    def _rank(self, robot: Robot) -> tuple:
        """Right-of-way rank: higher wins. Urgent work first, returning robots last, then lowest id."""
        task = self._task_or_none(robot.task_id)
        priority = task.priority_value if (task is not None and robot.phase != "returning") else -1
        return (priority, -int(robot.id[1:]))

    def _blocked(self, robot: Robot, blocked_cell: Cell) -> None:
        """Another robot is in the way.

        * Idle blocker: it steps aside.
        * Offline blocker on our final cell: the task goes back to the queue.
        * Charging / offline blocker elsewhere: re-plan around it.
        * Working blocker: the robot with the LOWER rank re-plans, the higher one holds
          its route. A strict rank order means two robots can never swap routes forever.
        """
        robot.progress = 1.0
        robot.leg_blocked += 1
        blocker = next((r for r in self.robots if r.cell == blocked_cell and r.id != robot.id), None)
        if blocker is None:
            return
        replan = False
        if blocker.status == C.ROBOT_IDLE:
            if self._nudge_idle(blocker, robot):
                return   # the idle robot stepped aside; try again next tick
            replan = True
        elif blocker.status == C.ROBOT_OFFLINE:
            if len(robot.path) == 1 and robot.phase in ("to_pickup", "to_dest"):
                self._release_task(robot, f"({blocked_cell[0]},{blocked_cell[1]}) is held by offline robot {blocker.id}")
                self._start_return(robot)
                return
            replan = True
        elif blocker.status == C.ROBOT_CHARGING:
            replan = True
        else:
            replan = self._rank(robot) < self._rank(blocker)

        robot.wait_ticks += 1
        if replan and robot.wait_ticks % C.REPLAN_AFTER_WAITS == 0 and robot.path:
            goal = robot.path[-1]
            alt = astar(self.warehouse, robot.cell, goal, extra_blocked=self.occupied_cells(exclude_id=robot.id))
            if alt is not None and len(alt) > 1:
                robot.path = alt[1:]
        if robot.leg_blocked >= C.STUCK_LIMIT:
            robot.leg_blocked = 0
            self._sidestep(robot)

    def _nudge_idle(self, idle: Robot, mover: Robot, depth: int = 0) -> bool:
        """An idle robot that blocks a working robot steps to a free neighbouring cell.

        If it is boxed in by other idle robots, those are asked to move first
        (up to 4 levels deep), so a cluster of parked robots can always be cleared.
        """
        on_route = set(mover.path)
        for attempt in range(2):
            occupied = self.occupied_cells()
            for avoid_route in (True, False):
                for nb in self.warehouse.neighbors(idle.cell):
                    if nb in occupied or self.warehouse.is_blocked(*nb):
                        continue
                    if avoid_route and nb in on_route:
                        continue
                    idle.x, idle.y = nb
                    idle.distance_travelled += 1
                    idle.battery = max(0.0, idle.battery - rules.drain_per_cell(0.0))
                    self.add_event(
                        "robot_status", f"{idle.id} moved aside to let {mover.id} pass.", robot_id=idle.id
                    )
                    return True
            if attempt == 1 or depth >= 4:
                return False
            moved = False
            for nb in self.warehouse.neighbors(idle.cell):
                neighbour = next((r for r in self.robots if r.cell == nb and r.id != mover.id), None)
                if neighbour is not None and neighbour.status == C.ROBOT_IDLE:
                    if self._nudge_idle(neighbour, mover, depth + 1):
                        moved = True
                        break
            if not moved:
                return False
        return False

    def _sidestep(self, robot: Robot) -> None:
        occupied = self.occupied_cells(exclude_id=robot.id)
        goal = robot.path[-1] if robot.path else robot.cell
        for nb in self.warehouse.neighbors(robot.cell):
            if nb not in occupied and not self.warehouse.is_blocked(*nb):
                robot.x, robot.y = nb
                robot.stuck_events += 1
                robot.wait_ticks = 0
                robot.progress = 0.0
                new_path = astar(self.warehouse, robot.cell, goal) or [robot.cell]
                robot.path = new_path[1:]
                self.add_event("robot_status", f"{robot.id} side-stepped to clear a blockage.", robot_id=robot.id)
                return

    def _arrive(self, robot: Robot, task: Optional[Task]) -> None:
        phase = robot.phase
        robot.progress = 0.0
        robot.leg_blocked = 0
        if phase == "to_pickup":
            robot.phase = "loading"
            robot.phase_timer = C.LOAD_TICKS
        elif phase == "to_dest":
            robot.phase = "unloading"
            robot.phase_timer = C.LOAD_TICKS
        elif phase == "returning":
            robot.path = []
            robot.phase = "none"
            robot.charge_target = None
            if robot.battery < C.CHARGE_START_BELOW:
                robot.status = C.ROBOT_CHARGING
                self.add_event(
                    "robot_charging", f"{robot.id} docked and is charging ({robot.battery:.0f}%).", robot_id=robot.id
                )
            else:
                robot.status = C.ROBOT_IDLE

    def _finish_loading(self, robot: Robot, task: Optional[Task]) -> None:
        if task is None:
            self._start_return(robot)
            return
        robot.load_pct = task.load_pct
        task.status = C.TASK_IN_PROGRESS
        task.started_sim_time = self.sim_time
        goal = (task.destination["x"], task.destination["y"])
        others = self.occupied_cells(exclude_id=robot.id)
        path = astar(self.warehouse, robot.cell, goal, extra_blocked=others) or astar(self.warehouse, robot.cell, goal)
        if path is None:
            self._release_task(robot, "no route to destination")
            self._start_return(robot)
            return
        robot.path = path[1:]
        robot.dest_plan = []
        robot.phase = "to_dest"
        robot.progress = 0.0
        robot.wait_ticks = 0

    def _finish_unloading(self, robot: Robot, task: Optional[Task]) -> None:
        if task is not None:
            task.status = C.TASK_COMPLETED
            task.completed_sim_time = self.sim_time
            task.actual_seconds = self.sim_time - (task.assigned_sim_time or 0.0)
            robot.tasks_completed += 1
            predicted = "" if task.predicted_seconds is None else f", predicted {task.predicted_seconds:.0f} s"
            self.add_event(
                "task_completed",
                f"{robot.id} completed {task.id} in {task.actual_seconds:.0f} s{predicted}.",
                robot_id=robot.id, task_id=task.id,
            )
        robot.task_id = None
        robot.load_pct = 0.0
        robot.path = []
        robot.dest_plan = []
        robot.phase = "none"
        if robot.battery < C.RETURN_TO_CHARGE_BELOW:
            self._start_return(robot)
        else:
            robot.status = C.ROBOT_IDLE
            self.add_event(
                "robot_idle", f"{robot.id} is idle at ({robot.x},{robot.y}), battery {robot.battery:.0f}%.",
                robot_id=robot.id,
            )

    def _start_return(self, robot: Robot) -> None:
        """Send a robot to the nearest free charging bay."""
        reserved = {r.charge_target for r in self.robots if r.id != robot.id and r.charge_target is not None}
        occupied = self.occupied_cells(exclude_id=robot.id)
        free = [c for c in self.warehouse.charging_cells() if c not in occupied and c not in reserved]
        if not free:
            robot.status = C.ROBOT_IDLE
            robot.phase = "none"
            robot.path = []
            self.add_event("warning", f"{robot.id} found no free charging bay and is waiting in place.", robot_id=robot.id)
            return
        target = min(free, key=lambda c: (manhattan(robot.cell, c), c[1], c[0]))
        path = astar(self.warehouse, robot.cell, target, extra_blocked=occupied) or astar(self.warehouse, robot.cell, target)
        if path is None:
            robot.status = C.ROBOT_IDLE
            robot.phase = "none"
            robot.path = []
            return
        robot.charge_target = target
        robot.path = path[1:]
        robot.phase = "returning"
        robot.status = C.ROBOT_MOVING
        robot.progress = 0.0
        robot.wait_ticks = 0
        robot.leg_blocked = 0
        if robot.battery < C.CHARGE_START_BELOW:
            self.add_event(
                "robot_charging", f"{robot.id} sent to the charging station (battery {robot.battery:.0f}%).",
                robot_id=robot.id,
            )
        else:
            self.add_event("robot_returning", f"{robot.id} returning to the charging area.", robot_id=robot.id)
        if not robot.path:
            self._arrive(robot, None)

    # ------------------------------------------------------------------ invariants
    def _audit(self) -> None:
        """Independent consistency check run after every tick."""
        owners: dict[str, str] = {}
        seen_cells: dict[Cell, str] = {}
        for robot in self.robots:
            if robot.cell in seen_cells:
                self._violation(f"{robot.id} and {seen_cells[robot.cell]} occupy the same cell")
            seen_cells[robot.cell] = robot.id
            if robot.task_id is not None:
                if robot.task_id in owners:
                    self._violation(f"duplicate assignment: {robot.task_id} held by {owners[robot.task_id]} and {robot.id}")
                owners[robot.task_id] = robot.id
                if robot.status in (C.ROBOT_IDLE, C.ROBOT_CHARGING, C.ROBOT_OFFLINE):
                    self._violation(f"{robot.id} holds {robot.task_id} while {robot.status}")
        for task in self.tasks:
            if task.status in (C.TASK_ASSIGNED, C.TASK_IN_PROGRESS):
                if owners.get(task.id) != task.assigned_robot:
                    self._violation(f"{task.id} is {task.status} but robot ownership does not match")

    # ------------------------------------------------------------------ reporting
    def summary(self) -> dict:
        batteries = [r.battery for r in self.robots]
        counts = {s: sum(1 for r in self.robots if r.status == s) for s in C.ROBOT_STATUSES}
        return {
            "total_robots": len(self.robots),
            "available_robots": counts[C.ROBOT_IDLE],
            "robots_by_status": counts,
            "active_tasks": sum(1 for t in self.tasks if t.status in (C.TASK_ASSIGNED, C.TASK_IN_PROGRESS)),
            "pending_tasks": sum(1 for t in self.tasks if t.status == C.TASK_PENDING),
            "completed_tasks": sum(1 for t in self.tasks if t.status == C.TASK_COMPLETED),
            "total_tasks": len(self.tasks),
            "battery_avg": round(sum(batteries) / len(batteries), 1) if batteries else 0.0,
            "battery_min": round(min(batteries), 1) if batteries else 0.0,
            "battery_max": round(max(batteries), 1) if batteries else 0.0,
            "low_battery_robots": sum(1 for b in batteries if b < C.BATTERY_SLOW_THRESHOLD),
        }

    def status_label(self) -> str:
        if self.active_tasks() or any(r.status in (C.ROBOT_ASSIGNED, C.ROBOT_MOVING) for r in self.robots):
            return "Active"
        if self.tick == 0 and not self.tasks:
            return "Ready"
        return "Idle"

    def snapshot(self, event_limit: int = 60) -> dict:
        return {
            "sim": {
                "tick": self.tick,
                "time_s": round(self.sim_time, 1),
                "tick_seconds": C.TICK_SECONDS,
                "status": self.status_label(),
            },
            "warehouse": self.warehouse.to_dict(),
            "robots": [r.to_dict() for r in self.robots],
            "tasks": [t.to_dict() for t in self.tasks],
            "events": list(reversed(self.events[-event_limit:])),
            "summary": self.summary(),
            "last_decision": self.last_decision,
            "config": {
                "safety_reserve": self.safety_reserve,
                "tick_seconds": C.TICK_SECONDS,
                "grid_width": self.warehouse.width,
                "grid_height": self.warehouse.height,
            },
        }

    def run_metrics(self) -> dict:
        """Measured results of the run so far (nothing is estimated or invented)."""
        done = [t for t in self.tasks if t.status == C.TASK_COMPLETED]
        turnaround = [t.completed_sim_time - t.created_sim_time for t in done]
        service = [t.actual_seconds for t in done if t.actual_seconds is not None]
        total_ticks = max(self.tick, 1)
        per_robot = []
        for r in self.robots:
            per_robot.append({
                "id": r.id,
                "tasks_completed": r.tasks_completed,
                "distance_cells": r.distance_travelled,
                "idle_s": r.idle_ticks * C.TICK_SECONDS,
                "busy_s": r.busy_ticks * C.TICK_SECONDS,
                "charging_s": r.charging_ticks * C.TICK_SECONDS,
                "offline_s": r.offline_ticks * C.TICK_SECONDS,
                "utilization_pct": round(100.0 * r.busy_ticks / total_ticks, 1) if self.tick else None,
            })
        return {
            "ticks": self.tick,
            "sim_time_s": self.sim_time,
            "tasks_total": len(self.tasks),
            "tasks_completed": len(done),
            "avg_turnaround_s": round(sum(turnaround) / len(turnaround), 2) if turnaround else None,
            "avg_service_s": round(sum(service) / len(service), 2) if service else None,
            "makespan_s": max(t.completed_sim_time for t in done) if done else None,
            "total_distance_cells": sum(r.distance_travelled for r in self.robots),
            "robot_idle_s": sum(r.idle_ticks for r in self.robots) * C.TICK_SECONDS,
            "rejected_assignments": len(self.rejected_task_ids),
            "tasks_that_waited": len(self.waited_task_ids),
            "constraint_violations": len(self.violations),
            "violation_details": list(self.violations[:20]),
            "per_robot": per_robot,
        }

    def live_prediction_accuracy(self) -> dict:
        """Predicted vs actual duration for completed AI-dispatched tasks (this run only)."""
        pairs = [
            (t.predicted_seconds, t.actual_seconds)
            for t in self.tasks
            if t.status == C.TASK_COMPLETED and t.dispatcher == "ai"
            and t.predicted_seconds is not None and t.actual_seconds is not None
        ]
        if not pairs:
            return {"n": 0, "mae_s": None, "rmse_s": None, "pairs": []}
        errors = [p - a for p, a in pairs]
        return {
            "n": len(pairs),
            "mae_s": round(sum(abs(e) for e in errors) / len(errors), 2),
            "rmse_s": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 2),
            "pairs": [{"predicted": round(p, 1), "actual": round(a, 1)} for p, a in pairs],
        }
