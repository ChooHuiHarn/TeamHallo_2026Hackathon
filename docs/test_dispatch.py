"""Dispatch, routing, constraints, validation and reset tests (no TensorFlow needed)."""
import pytest

from app import config as C
from app.dispatch import dispatch_next, evaluate_candidates
from app.errors import Conflict, InvalidRequest, ModelUnavailable
from app.pathfinding import astar
from app.simulation import Simulation
from conftest import RuleBasedPredictor, UnavailablePredictor, run_until_done


def make_task(sim, src="receiving", dst="shipping", priority="Normal", load=30):
    return sim.create_task({"zone": src}, {"zone": dst}, priority, load)


# ------------------------------------------------------------------ normal flow
def test_normal_task_creation_and_dispatch():
    sim = Simulation()
    task = make_task(sim)
    assert task.id == "T001" and task.status == C.TASK_PENDING
    result = dispatch_next(sim, RuleBasedPredictor(), "ai")
    assert result["assigned"] is True
    robot = sim.robot_by_id(result["robot_id"])
    assert robot.status == C.ROBOT_ASSIGNED and robot.task_id == "T001"
    assert task.status == C.TASK_ASSIGNED and task.assigned_robot == robot.id
    assert result["decision"]["explanation"]
    assert len(result["decision"]["candidates"]) == 6


def test_task_runs_to_completion_and_robot_becomes_available():
    sim = Simulation()
    make_task(sim)
    assert run_until_done(sim, "baseline")
    task = sim.tasks[0]
    assert task.status == C.TASK_COMPLETED and task.actual_seconds > 0
    assert sim.summary()["completed_tasks"] == 1
    assert sim.summary()["active_tasks"] == 0
    assert all(r.task_id is None for r in sim.robots)
    assert sim.violations == []


def test_urgent_task_is_dispatched_before_older_normal_task():
    sim = Simulation()
    make_task(sim, priority="Normal")
    make_task(sim, src="storage", dst="packing", priority="Urgent")
    result = dispatch_next(sim, None, "baseline")
    assert result["task_id"] == "T002"


def test_fifo_within_same_priority():
    sim = Simulation()
    make_task(sim, priority="Low")
    make_task(sim, src="storage", dst="packing", priority="Low")
    assert dispatch_next(sim, None, "baseline")["task_id"] == "T001"


def test_ai_chooses_lowest_predicted_time():
    sim = Simulation()
    make_task(sim)
    result = dispatch_next(sim, RuleBasedPredictor(), "ai")
    feasible = [c for c in result["decision"]["candidates"] if c["feasible"]]
    best = min(feasible, key=lambda c: (c["predicted_seconds"], c["robot_id"]))
    assert result["robot_id"] == best["robot_id"]


# ------------------------------------------------------------------ battery constraints
def test_insufficient_battery_rejects_robot_and_keeps_task_pending():
    sim = Simulation()
    for r in sim.robots:
        r.battery = 10.0
        r.status = C.ROBOT_IDLE
    task = make_task(sim, "receiving", "shipping")
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] is False
    assert task.status == C.TASK_PENDING
    assert "battery" in result["message"].lower()
    assert any(e["type"] == "assignment_rejected" for e in sim.events)
    assert sim.run_metrics()["rejected_assignments"] == 1


def test_low_battery_robot_skipped_but_others_used():
    sim = Simulation()
    sim.robots[0].battery = 12.0
    for r in sim.robots[1:]:
        r.battery = 100.0
        r.status = C.ROBOT_IDLE
    sim.robots[0].status = C.ROBOT_IDLE
    make_task(sim)
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] and result["robot_id"] != "R01"
    r01 = next(c for c in result["decision"]["candidates"] if c["robot_id"] == "R01")
    assert not r01["feasible"] and "Battery" in r01["reason"]


def test_safety_reserve_is_configurable():
    sim = Simulation(safety_reserve=0.0)
    for r in sim.robots:
        r.status = C.ROBOT_IDLE
        r.battery = 30.0
    make_task(sim, "receiving", "shipping")
    ok = dispatch_next(sim, None, "baseline")["assigned"]
    sim2 = Simulation(safety_reserve=40.0)
    for r in sim2.robots:
        r.status = C.ROBOT_IDLE
        r.battery = 30.0
    make_task(sim2, "receiving", "shipping")
    assert ok is True
    assert dispatch_next(sim2, None, "baseline")["assigned"] is False


# ------------------------------------------------------------------ availability
def test_no_available_robots_keeps_task_pending_with_explanation():
    sim = Simulation()
    for r in sim.robots:
        r.status = C.ROBOT_OFFLINE
    task = make_task(sim)
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] is False and task.status == C.TASK_PENDING
    assert "No suitable robot" in result["message"]


def test_charging_and_offline_robots_are_never_assigned():
    sim = Simulation()
    for r in sim.robots:
        r.status = C.ROBOT_CHARGING
    sim.robots[5].status = C.ROBOT_OFFLINE
    make_task(sim)
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] is False
    reasons = {c.robot_id: c.reason for c in evaluate_candidates(sim, sim.tasks[0])}
    assert "Charging" in reasons["R01"] and reasons["R06"] == "Offline"


def test_no_pending_tasks_message():
    sim = Simulation()
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] is False and "no pending" in result["message"].lower()


# ------------------------------------------------------------------ duplicate assignments
def test_robot_never_gets_two_tasks():
    sim = Simulation()
    for i in range(10):
        make_task(sim, "receiving", "shipping")
    while dispatch_next(sim, None, "baseline")["assigned"]:
        pass
    owners = [r.task_id for r in sim.robots if r.task_id]
    assert len(owners) == len(set(owners))
    assert sum(1 for t in sim.tasks if t.status == C.TASK_ASSIGNED) == len(owners) <= 6


def test_task_cannot_be_assigned_twice():
    sim = Simulation()
    make_task(sim)
    dispatch_next(sim, None, "baseline")
    with pytest.raises(Conflict):
        dispatch_next(sim, None, "baseline", task_id="T001")


def test_commit_assignment_refuses_busy_robot():
    sim = Simulation()
    make_task(sim)
    make_task(sim, "storage", "packing")
    first = dispatch_next(sim, None, "baseline")
    busy = sim.robot_by_id(first["robot_id"])
    with pytest.raises(Conflict):
        sim.commit_assignment(sim.tasks[1], busy, {
            "_path_to_pickup": [busy.cell], "_path_to_destination": [busy.cell],
            "features": {"queued_tasks": 0}, "predicted_seconds": 1.0,
            "route_distance": 0, "dispatcher": "baseline",
        })


# ------------------------------------------------------------------ routes
def test_astar_finds_shortest_path_around_obstacles():
    sim = Simulation()
    path = astar(sim.warehouse, (0, 3), (4, 3))
    assert path[0] == (0, 3) and path[-1] == (4, 3)
    assert all(cell not in sim.warehouse.blocked for cell in path)
    assert len(path) - 1 == 6   # detour around the (2,3)/(2,4) obstacle


def test_astar_returns_none_when_unreachable():
    sim = Simulation()
    for y in range(sim.warehouse.height):
        sim.warehouse.set_obstacle(5, y, True)   # a full wall
    assert astar(sim.warehouse, (0, 0), (9, 7)) is None


def test_unreachable_route_rejects_task_with_reason():
    sim = Simulation()
    make_task(sim, "receiving", "shipping")
    for y in range(sim.warehouse.height):
        sim.warehouse.set_obstacle(5, y, True)
    result = dispatch_next(sim, None, "baseline")
    assert result["assigned"] is False
    assert "No route" in result["message"]
    assert sim.tasks[0].status == C.TASK_PENDING


def test_blocking_obstacle_that_strands_a_robot_is_refused():
    sim = Simulation()
    for y in range(sim.warehouse.height - 1):
        if (5, y) not in sim.warehouse.blocked:
            sim.set_obstacle(5, y, True)
    make_task(sim, "receiving", "shipping")
    dispatch_next(sim, None, "baseline")
    with pytest.raises(Conflict):
        sim.set_obstacle(5, 7, True)   # would seal the last gap


def test_robots_avoid_obstacles_while_moving():
    sim = Simulation()
    make_task(sim, "receiving", "shipping")
    dispatch_next(sim, None, "baseline")
    for _ in range(80):
        sim.step()
        assert all(not sim.warehouse.is_blocked(*r.cell) for r in sim.robots)


# ------------------------------------------------------------------ validation
def test_invalid_coordinates_and_data_rejected():
    sim = Simulation()
    with pytest.raises(InvalidRequest):
        sim.create_task({"x": 99, "y": 0}, {"zone": "shipping"}, "Normal", 10)
    with pytest.raises(InvalidRequest):
        sim.create_task({"x": -1, "y": 2}, {"zone": "shipping"}, "Normal", 10)
    with pytest.raises(InvalidRequest):
        sim.create_task({"x": 2, "y": 3}, {"zone": "shipping"}, "Normal", 10)    # obstacle
    with pytest.raises(InvalidRequest):
        sim.create_task({"zone": "nowhere"}, {"zone": "shipping"}, "Normal", 10)
    with pytest.raises(InvalidRequest):
        sim.create_task({"zone": "receiving"}, {"zone": "receiving"}, "Normal", 10)  # same place
    with pytest.raises(InvalidRequest):
        sim.create_task({"zone": "receiving"}, {"zone": "shipping"}, "Critical", 10)
    with pytest.raises(InvalidRequest):
        sim.create_task({"zone": "receiving"}, {"zone": "shipping"}, "Normal", 150)
    with pytest.raises(InvalidRequest):
        sim.create_task({"x": 1}, {"zone": "shipping"}, "Normal", 10)           # missing y
    with pytest.raises(InvalidRequest):
        sim.create_task({"zone": "charging"}, {"zone": "shipping"}, "Normal", 10)
    assert sim.tasks == []


def test_unknown_dispatcher_rejected():
    sim = Simulation()
    make_task(sim)
    with pytest.raises(InvalidRequest):
        dispatch_next(sim, None, "magic")


# ------------------------------------------------------------------ model unavailable
def test_ai_dispatch_reports_clear_error_when_model_missing():
    sim = Simulation()
    task = make_task(sim)
    with pytest.raises(ModelUnavailable) as info:
        dispatch_next(sim, UnavailablePredictor(), "ai")
    assert "baseline" in info.value.message
    assert task.status == C.TASK_PENDING     # nothing was assigned or lost


def test_baseline_works_without_model():
    sim = Simulation()
    make_task(sim)
    assert dispatch_next(sim, UnavailablePredictor(), "baseline")["assigned"]


# ------------------------------------------------------------------ simulation behaviour
def test_moving_robot_consumes_battery():
    sim = Simulation()
    make_task(sim)
    result = dispatch_next(sim, None, "baseline")
    robot = sim.robot_by_id(result["robot_id"])
    before = robot.battery
    for _ in range(10):
        sim.step()
    assert robot.battery < before


def test_robot_charges_when_it_docks_with_low_battery():
    sim = Simulation()
    robot = sim.robots[0]
    robot.battery = 40.0
    robot.status = C.ROBOT_CHARGING
    for _ in range(30):
        sim.step()
    assert robot.battery >= C.CHARGE_DONE and robot.status == C.ROBOT_IDLE


def test_offline_robot_releases_task_back_to_queue():
    sim = Simulation()
    make_task(sim)
    result = dispatch_next(sim, None, "baseline")
    sim.patch_robot(result["robot_id"], offline=True)
    task = sim.tasks[0]
    assert task.status == C.TASK_PENDING and task.assigned_robot is None
    again = dispatch_next(sim, None, "baseline")
    assert again["assigned"] and again["robot_id"] != result["robot_id"]


def test_simulation_is_deterministic():
    def run():
        sim = Simulation()
        for i in range(6):
            make_task(sim, "receiving", ["shipping", "packing", "picking"][i % 3], ["Low", "Normal", "Urgent"][i % 3], 20 + 10 * i)
        run_until_done(sim, "baseline")
        return [(t.id, t.assigned_robot, t.actual_seconds) for t in sim.tasks], sim.tick

    assert run() == run()


def test_no_constraint_violations_over_a_busy_run():
    sim = Simulation()
    for i in range(20):
        make_task(sim, ["receiving", "storage", "picking"][i % 3], ["packing", "shipping"][i % 2], ["Low", "Normal", "Urgent"][i % 3], 40)
    assert run_until_done(sim, "baseline", max_ticks=1500)
    assert sim.run_metrics()["constraint_violations"] == 0
    for r in sim.robots:
        assert r.idle_ticks + r.busy_ticks + r.charging_ticks + r.offline_ticks == sim.tick


# ------------------------------------------------------------------ reset
def test_reset_restores_known_starting_state():
    sim = Simulation()
    start = [(r.id, r.cell, r.battery, r.status) for r in sim.robots]
    for _ in range(5):
        make_task(sim)
    while dispatch_next(sim, None, "baseline")["assigned"]:
        pass
    for _ in range(25):
        sim.step()
    sim.set_obstacle(5, 4, True)
    sim.reset()
    assert [(r.id, r.cell, r.battery, r.status) for r in sim.robots] == start
    assert sim.tasks == [] and sim.tick == 0 and sim.last_decision is None
    assert sim.warehouse.blocked == {(2, 3), (2, 4), (7, 3), (7, 4)}
    assert make_task(sim).id == "T001"    # ids restart after reset
