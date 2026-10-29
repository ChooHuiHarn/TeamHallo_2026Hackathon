import React, { useState } from "react";
import { Badge, Card, fmtTime, locText } from "../components/Common.jsx";
import { CandidateTable, DecisionSummary, DispatcherSelect, QuickDispatch, SimControls } from "../components/Panels.jsx";
import Icon from "../components/Icons.jsx";

export default function DispatchPage({ fleet, state }) {
  const zones = state.warehouse.zones;
  const [reserve, setReserve] = useState(state.config.safety_reserve);
  const pending = state.tasks.filter((t) => t.status === "Pending");
  const order = { Urgent: 0, Normal: 1, Low: 2 };
  const queue = [...pending].sort((a, b) => order[a.priority] - order[b.priority] || a.id.localeCompare(b.id));
  const msg = fleet.lastMessage;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Task Dispatch</h1>
          <p>Create tasks, run the assignment workflow and advance the simulation.</p>
        </div>
        <SimControls fleet={fleet} state={state} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1.4fr)", alignItems: "start", marginBottom: 16 }}>
        <div className="stack">
          <QuickDispatch fleet={fleet} state={state} withLoad />
          <Card title="Dispatch settings">
            <div className="stack" style={{ gap: 10 }}>
              <div className="row"><span className="small muted">Dispatcher</span><DispatcherSelect fleet={fleet} /></div>
              <div className="row">
                <label className="field" style={{ flex: 1 }}>
                  Battery safety reserve (%)
                  <input type="number" min="0" max="50" value={reserve} onChange={(e) => setReserve(e.target.value)} />
                </label>
                <button className="btn sm" style={{ alignSelf: "flex-end" }} disabled={fleet.busy} onClick={() => fleet.setReserve(Number(reserve))}>Apply</button>
              </div>
              <p className="small muted">A robot is only eligible if its battery covers the route to the pickup, the delivery, the trip back to a charging bay and this reserve.</p>
            </div>
          </Card>
        </div>
        <div className="stack">
          {msg && !msg.assigned && (
            <div className="banner warn" role="status"><Icon name="alert" /><div><b>Task kept pending.</b> {msg.message}</div></div>
          )}
          <DecisionSummary decision={state.last_decision} />
          {state.last_decision && (
            <Card title="Candidate robots" subtitle="Every robot considered for the last assignment">
              <CandidateTable decision={state.last_decision} />
            </Card>
          )}
        </div>
      </div>

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <Card title={`Pending queue (${queue.length})`} subtitle="Urgent first, then first-in-first-out">
          {queue.length === 0 ? <div className="empty">No pending tasks.</div> : (
            <div className="table-wrap"><table className="data">
              <thead><tr><th>#</th><th>Task</th><th>Priority</th><th>Route</th><th>Note</th></tr></thead>
              <tbody>
                {queue.map((t, i) => (
                  <tr key={t.id}>
                    <td>{i + 1}</td><td><b>{t.id}</b></td><td><Badge kind={t.priority} /></td>
                    <td className="small">{locText(t.pickup, zones)} → {locText(t.destination, zones)}</td>
                    <td className="small muted">{t.last_rejection || "Waiting"}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>
        <Card title={`All tasks (${state.tasks.length})`}>
          {state.tasks.length === 0 ? <div className="empty">No tasks yet.</div> : (
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Task</th><th>Priority</th><th>Status</th><th>Robot</th><th>Pred.</th><th>Actual</th><th>Created</th></tr></thead>
              <tbody>
                {[...state.tasks].reverse().map((t) => (
                  <tr key={t.id}>
                    <td><b>{t.id}</b><div className="small muted">{t.pickup.zone || `(${t.pickup.x},${t.pickup.y})`} → {t.destination.zone || `(${t.destination.x},${t.destination.y})`}</div></td>
                    <td><Badge kind={t.priority} /></td><td><Badge kind={t.status} /></td>
                    <td>{t.assigned_robot || "—"}</td>
                    <td className="mono">{t.predicted_seconds != null ? fmtTime(t.predicted_seconds) : "—"}</td>
                    <td className="mono">{t.actual_seconds != null ? fmtTime(t.actual_seconds) : "—"}</td>
                    <td className="small muted">{new Date(t.created_at).toLocaleTimeString()} · t={Math.round(t.created_sim_time)}s</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>
      </div>
    </>
  );
}
