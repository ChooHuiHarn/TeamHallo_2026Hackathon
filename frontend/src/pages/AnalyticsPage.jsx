import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Card, StatCard, fmtNum } from "../components/Common.jsx";
import { CompareBars, Scatter, UtilizationBars } from "../components/Charts.jsx";
import Icon from "../components/Icons.jsx";

export default function AnalyticsPage({ fleet, state }) {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [exp, setExp] = useState({ seed: 42, runs: 3, num_tasks: 12, arrival: "sparse" });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [expError, setExpError] = useState(null);

  const load = useCallback(async () => {
    try {
      setMetrics(await api.metrics());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  // reload whenever the simulation moves (tick) or tasks change
  useEffect(() => { load(); }, [load, state.sim.tick, state.summary.completed_tasks, state.summary.total_tasks]);

  const runCompare = async () => {
    setRunning(true);
    setExpError(null);
    try {
      setResult(await api.compare({ seed: Number(exp.seed), runs: Number(exp.runs), num_tasks: Number(exp.num_tasks), arrival: exp.arrival }));
    } catch (e) {
      setExpError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const model = metrics?.model;
  const ev = metrics?.evaluation;
  const meta = model?.metadata;
  const live = metrics?.live_prediction;
  const dispatch = metrics?.dispatch;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>AI Analytics</h1>
          <p>Model prediction accuracy and dispatch-system performance are different things and are shown separately.</p>
        </div>
        <button className="btn" onClick={load}><Icon name="reset" size={15} /> Refresh</button>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      <Banner kind="info">
        {metrics?.disclaimer || "FleetPilot AI is a simulation. The TensorFlow model is trained on synthetic data; its accuracy does not establish real-world warehouse accuracy."}
      </Banner>

      {/* ------------------------------------------------ Part 1: model */}
      <h2 style={{ margin: "8px 0 12px" }}>1 · Model prediction accuracy</h2>
      {model && !model.available && (
        <Banner kind="warn">
          <b>TensorFlow model unavailable.</b> {model.error} AI dispatch and the AI side of comparisons are disabled until a model is trained.
        </Banner>
      )}
      <div className="grid cols-6" style={{ marginBottom: 16 }}>
        <StatCard icon="chart" label="Model status" value={model ? model.status : "…"} sub={model?.version ? `Version ${model.version}` : "No version"} />
        <StatCard icon="target" label="Test MAE" value={ev?.mae_s != null ? `${fmtNum(ev.mae_s, 2)} s` : "Not evaluated"} sub="mean absolute error" />
        <StatCard icon="target" label="Test RMSE" value={ev?.rmse_s != null ? `${fmtNum(ev.rmse_s, 2)} s` : "Not evaluated"} sub="root mean squared error" />
        <StatCard icon="chart" label="Test R²" value={ev?.r2 != null ? fmtNum(ev.r2, 3) : "Not evaluated"} sub="on held-out synthetic data" />
        <StatCard icon="bolt" label="Baseline formula MAE" value={ev?.baseline_formula_mae_s != null ? `${fmtNum(ev.baseline_formula_mae_s, 2)} s` : "Not evaluated"} sub="same test split" />
        <StatCard icon="clock" label="Live prediction MAE" value={live?.mae_s != null ? `${fmtNum(live.mae_s, 2)} s` : "Not evaluated"} sub={live?.n ? `${live.n} completed AI tasks this run` : "no completed AI tasks yet"} />
      </div>
      <div className="grid cols-2" style={{ marginBottom: 24, alignItems: "start" }}>
        <Card title="Predicted vs actual duration (test split)" subtitle="Synthetic held-out examples · dashed line = perfect prediction">
          <Scatter points={metrics?.test_predictions} />
        </Card>
        <Card title="Predicted vs actual (this simulation run)" subtitle="Completed AI-dispatched tasks in the live simulation">
          <Scatter points={live?.pairs?.map((p) => ({ predicted: p.predicted, actual: p.actual }))} />
          {meta && (
            <dl className="kv" style={{ marginTop: 12 }}>
              <dt>Architecture</dt><dd>{meta.architecture}</dd>
              <dt>Framework</dt><dd>{meta.framework}</dd>
              <dt>Training data</dt><dd>{meta.data?.rows?.toLocaleString()} synthetic rows</dd>
              <dt>Split (train / val / test)</dt><dd className="mono">{meta.split?.train} / {meta.split?.validation} / {meta.split?.test}</dd>
            </dl>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------ Part 2: dispatch */}
      <h2 style={{ margin: "8px 0 12px" }}>2 · Dispatch-system performance</h2>
      <Card title="AI vs baseline comparison" subtitle="Both dispatchers run identical scenarios (same layout, starting batteries, tasks and seeds). Results come from real simulation runs."
        actions={<Badge kind="Moving">Measured</Badge>}>
        <div className="row" style={{ marginBottom: 12, alignItems: "flex-end" }}>
          <label className="field">Seed<input type="number" min="0" value={exp.seed} onChange={(e) => setExp({ ...exp, seed: e.target.value })} style={{ width: 90 }} /></label>
          <label className="field">Scenarios<input type="number" min="1" max="10" value={exp.runs} onChange={(e) => setExp({ ...exp, runs: e.target.value })} style={{ width: 90 }} /></label>
          <label className="field">Tasks each<input type="number" min="1" max="40" value={exp.num_tasks} onChange={(e) => setExp({ ...exp, num_tasks: e.target.value })} style={{ width: 90 }} /></label>
          <label className="field">Arrivals
            <select value={exp.arrival} onChange={(e) => setExp({ ...exp, arrival: e.target.value })}>
              <option value="sparse">Sparse (one task / 20 s)</option>
              <option value="staggered">Staggered (one task / 8 s)</option>
              <option value="burst">Burst (half at once)</option>
            </select>
          </label>
          <button className="btn amber" disabled={running} onClick={runCompare}>
            <Icon name="play" size={15} /> {running ? "Running…" : "Run comparison"}
          </button>
        </div>
        {expError && <Banner kind="error">{expError}</Banner>}
        {!result && !expError && <div className="empty">Not evaluated — run a comparison to measure both dispatchers.</div>}
        {result && (
          <>
            {!result.ai_available && <Banner kind="warn">The AI dispatcher was not evaluated: the TensorFlow model is not loaded. Baseline results are shown on their own below.</Banner>}
            {result.warnings.map((w, i) => <Banner key={i} kind="warn">{w}</Banner>)}
            <div className="explain" style={{ marginTop: 0, marginBottom: 14 }}><b>Result:</b> {result.conclusion}</div>
            <div className="grid cols-2" style={{ alignItems: "start" }}>
              <CompareBars metrics={result.metrics} />
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Metric</th><th>AI</th><th>Baseline</th><th>Better</th></tr></thead>
                  <tbody>
                    {result.metrics.map((m) => (
                      <tr key={m.key}>
                        <td className="small">{m.label}</td>
                        <td className="mono">{m.ai != null ? m.ai : "Not evaluated"}</td>
                        <td className="mono">{m.baseline != null ? m.baseline : "—"}</td>
                        <td className="small">{m.winner === "ai" ? "AI" : m.winner === "baseline" ? "Baseline" : m.winner === "tie" ? "Tie" : "—"}{m.ai_improvement_pct ? ` (${m.ai_improvement_pct > 0 ? "+" : ""}${m.ai_improvement_pct}%)` : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="small muted" style={{ marginTop: 6 }}>Percentages are AI improvement over baseline (positive = AI better). Averages over {result.scenario.runs} scenario(s).</p>
              </div>
            </div>
            {result.prediction_accuracy_in_simulation && (
              <p className="small muted" style={{ marginTop: 10 }}>
                Across these AI runs, predictions differed from the simulated outcome by MAE {result.prediction_accuracy_in_simulation.mae_s} s / RMSE {result.prediction_accuracy_in_simulation.rmse_s} s ({result.prediction_accuracy_in_simulation.n} tasks).
              </p>
            )}
          </>
        )}
      </Card>

      <div className="grid cols-2" style={{ margin: "16px 0", alignItems: "start" }}>
        <Card title="Task completion statistics" subtitle="Current simulation run">
          {dispatch ? (
            <dl className="kv">
              <dt>Tasks completed</dt><dd className="mono">{dispatch.tasks_completed} of {dispatch.tasks_total}</dd>
              <dt>Average completion time (created → delivered)</dt><dd className="mono">{dispatch.avg_turnaround_s != null ? `${dispatch.avg_turnaround_s} s` : "Not evaluated"}</dd>
              <dt>Average service time (assigned → delivered)</dt><dd className="mono">{dispatch.avg_service_s != null ? `${dispatch.avg_service_s} s` : "Not evaluated"}</dd>
              <dt>Total simulated time</dt><dd className="mono">{dispatch.sim_time_s} s</dd>
              <dt>Total distance travelled</dt><dd className="mono">{dispatch.total_distance_cells} cells</dd>
              <dt>Rejected assignments</dt><dd className="mono">{dispatch.rejected_assignments}</dd>
              <dt>Constraint violations</dt><dd className="mono">{dispatch.constraint_violations}</dd>
            </dl>
          ) : <div className="empty">Not evaluated</div>}
        </Card>
        <Card title="Robot utilization and idle time" subtitle="Current simulation run">
          <UtilizationBars perRobot={dispatch?.per_robot} />
          {dispatch && <p className="small muted" style={{ marginTop: 8 }}>Total robot idle time: {dispatch.robot_idle_s} s</p>}
        </Card>
      </div>

      <Card title="Recent dispatch decisions" subtitle="Each decision lists why the robot was chosen">
        {!metrics || metrics.decisions.length === 0 ? <div className="empty">No dispatch decisions yet.</div> : (
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Decision</th><th>Task → Robot</th><th>Method</th><th>Predicted</th><th>Explanation</th></tr></thead>
            <tbody>
              {metrics.decisions.map((d) => (
                <tr key={d.id}>
                  <td><b>{d.id}</b><div className="small muted">t={Math.round(d.sim_time)}s</div></td>
                  <td>{d.task_id} → <b>{d.robot_id}</b></td>
                  <td><Badge kind={d.dispatcher === "ai" ? "Moving" : "Low"}>{d.dispatcher === "ai" ? "TensorFlow" : "Baseline"}</Badge></td>
                  <td className="mono">{d.predicted_seconds} s</td>
                  <td className="small" style={{ maxWidth: 520 }}>{d.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </>
  );
}
