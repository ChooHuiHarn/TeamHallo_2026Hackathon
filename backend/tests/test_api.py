"""REST API tests (need fastapi + httpx; skipped when they are not installed)."""
import pytest

from conftest import RuleBasedPredictor, UnavailablePredictor


def _client(predictor=None):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app(predictor=predictor or RuleBasedPredictor(), load_model=False))


def test_health_and_state():
    c = _client()
    assert c.get("/api/health").json()["status"] == "ok"
    state = c.get("/api/state").json()
    assert len(state["robots"]) == 6 and len(state["warehouse"]["zones"]) == 6
    assert state["summary"]["total_robots"] == 6 and state["sim"]["status"] == "Ready"


def test_create_task_dispatch_step_flow():
    c = _client()
    r = c.post("/api/tasks", json={"pickup": {"zone": "receiving"}, "destination": {"zone": "shipping"}, "priority": "Urgent"})
    assert r.status_code == 201 and r.json()["id"] == "T001"
    d = c.post("/api/dispatch/next", json={"dispatcher": "ai"}).json()
    assert d["assigned"] and d["decision"]["explanation"]
    s = c.post("/api/simulation/step", json={"steps": 40}).json()
    assert s["sim"]["tick"] == 40
    assert c.get("/api/metrics").json()["dispatch"]["tasks_completed"] == 1


def test_validation_errors_are_readable():
    c = _client()
    r = c.post("/api/tasks", json={"pickup": {"x": 50, "y": 50}, "destination": {"zone": "shipping"}})
    assert r.status_code == 400 and "outside" in r.json()["detail"]
    r = c.post("/api/tasks", json={"pickup": {"zone": "receiving"}, "destination": {"zone": "shipping"}, "priority": "Asap"})
    assert r.status_code == 422 and "detail" in r.json()
    assert c.get("/api/robots/R99").status_code == 404


def test_pending_task_not_dispatched_twice_returns_409():
    c = _client()
    c.post("/api/tasks", json={"pickup": {"zone": "receiving"}, "destination": {"zone": "shipping"}})
    c.post("/api/dispatch/next", json={})
    assert c.post("/api/dispatch/next", json={"task_id": "T001"}).status_code == 409


def test_ai_dispatch_without_model_returns_503_but_baseline_works():
    c = _client(UnavailablePredictor())
    c.post("/api/tasks", json={"pickup": {"zone": "receiving"}, "destination": {"zone": "shipping"}})
    r = c.post("/api/dispatch/next", json={"dispatcher": "ai"})
    assert r.status_code == 503 and "train" in r.json()["detail"].lower()
    assert c.post("/api/dispatch/next", json={"dispatcher": "baseline"}).json()["assigned"] is True


def test_reset_and_compare():
    c = _client()
    c.post("/api/tasks", json={"pickup": {"zone": "receiving"}, "destination": {"zone": "shipping"}})
    state = c.post("/api/simulation/reset", json={}).json()
    assert state["tasks"] == [] and state["sim"]["tick"] == 0
    res = c.post("/api/experiments/compare", json={"runs": 2, "num_tasks": 6, "arrival": "sparse"}).json()
    assert res["ai_available"] and len(res["per_run"]) == 2


def test_metrics_say_not_evaluated_without_model_metadata():
    c = _client()
    m = c.get("/api/metrics").json()
    assert m["evaluation"]["status"] == "Not evaluated" and m["evaluation"]["mae_s"] is None
    assert "synthetic" in m["disclaimer"]
