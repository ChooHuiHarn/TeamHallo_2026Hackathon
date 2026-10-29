"""AI-versus-baseline comparison tests (uses a test-double predictor, so no TensorFlow needed)."""
from app import experiments
from conftest import RuleBasedPredictor, UnavailablePredictor


def test_scenario_generation_is_reproducible():
    a = experiments.generate_scenario(7, 10, "burst")
    b = experiments.generate_scenario(7, 10, "burst")
    c = experiments.generate_scenario(8, 10, "burst")
    assert a == b and a != c


def test_both_dispatchers_receive_identical_scenarios():
    scenario = experiments.generate_scenario(11, 8, "staggered")
    before = repr(scenario)
    experiments.run_scenario(scenario, "baseline", None)
    experiments.run_scenario(scenario, "ai", RuleBasedPredictor())
    assert repr(scenario) == before    # scenario data is never modified by a run


def test_compare_reports_measured_metrics_for_both():
    result = experiments.compare(RuleBasedPredictor(), seed=3, runs=2, num_tasks=8, arrival="sparse")
    assert result["ai_available"] is True
    keys = {m["key"] for m in result["metrics"]}
    assert {"avg_turnaround_s", "makespan_s", "tasks_completed", "robot_idle_s",
            "total_distance_cells", "rejected_assignments", "constraint_violations"} <= keys
    for m in result["metrics"]:
        assert m["ai"] is not None and m["baseline"] is not None
    for run in result["per_run"]:
        assert run["ai"]["finished"] and run["baseline"]["finished"]
        assert run["ai"]["metrics"]["tasks_completed"] == 8
    assert "synthetic" in result["conclusion"].lower() or "do not show" in result["conclusion"]


def test_compare_is_deterministic():
    a = experiments.compare(RuleBasedPredictor(), seed=5, runs=2, num_tasks=8)
    b = experiments.compare(RuleBasedPredictor(), seed=5, runs=2, num_tasks=8)
    assert a["metrics"] == b["metrics"]


def test_improvement_sign_matches_winner():
    result = experiments.compare(RuleBasedPredictor(), seed=42, runs=3, num_tasks=10, arrival="sparse")
    for m in result["metrics"]:
        if m["winner"] == "ai":
            assert m["ai_improvement_pct"] is None or m["ai_improvement_pct"] > 0
        elif m["winner"] == "baseline":
            assert m["ai_improvement_pct"] is None or m["ai_improvement_pct"] < 0
        else:
            assert m["ai_improvement_pct"] in (None, 0)


def test_compare_without_model_says_not_evaluated():
    result = experiments.compare(UnavailablePredictor(), seed=1, runs=1, num_tasks=5)
    assert result["ai_available"] is False
    assert all(m["ai"] is None for m in result["metrics"])
    assert all(m["winner"] is None for m in result["metrics"])
    assert "Not evaluated" in result["conclusion"]
    assert result["warnings"]


def test_compare_validates_parameters():
    import pytest
    from app.errors import InvalidRequest
    with pytest.raises(InvalidRequest):
        experiments.compare(None, runs=0)
    with pytest.raises(InvalidRequest):
        experiments.compare(None, num_tasks=500)
    with pytest.raises(InvalidRequest):
        experiments.compare(None, arrival="weird")
