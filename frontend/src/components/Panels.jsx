import React, { useState } from "react";
import Icon from "./Icons.jsx";
import { Badge, Card, fmtNum } from "./Common.jsx";

// ---------------------------------------------------------------- location picker
export function LocationPicker({ label, zones, value, onChange }) {
  // value: { mode: "zone" | "xy", zone, x, y }
  return (
    <div className="stack" style={{ gap: 6 }}>
      <label className="field">
        {label}
        <select
          value={value.mode === "zone" ? value.zone : "__xy"}
          onChange={(e) => (e.target.value === "__xy" ? onChange({ ...value, mode: "xy" }) : onChange({ ...value, mode: "zone", zone: e.target.value }))}
        >
          {zones.filter((z) => z.id !== "charging").map((z) => (
            <option key={z.id} value={z.id}>{z.name}</option>
          ))}
          <option value="__xy">Custom coordinates…</option>
        </select>
      </label>
      {value.mode === "xy" && (
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <label className="field" style={{ flex: 1 }}>
            x (0–9)
            <input type="number" min="0" max="9" value={value.x} onChange={(e) => onChange({ ...value, x: e.target.value })} />
          </label>
          <label className="field" style={{ flex: 1 }}>
            y (0–7)
            <input type="number" min="0" max="7" value={value.y} onChange={(e) => onChange({ ...value, y: e.target.value })} />
          </label>
        </div>
      )}
    </div>
  );
}

export const defaultLoc = (zone) => ({ mode: "zone", zone, x: 0, y: 0 });

export function locToApi(v) {
  if (v.mode === "zone") return { zone: v.zone };
  const x = v.x === "" ? null : Number(v.x);
  const y = v.y === "" ? null : Number(v.y);
  return { x, y };
}

// ---------------------------------------------------------------- create task + assign
export function QuickDispatch({ fleet, state, withLoad = false, onPreview }) {
  const zones = state.warehouse.zones;
  const [pickup, setPickup] = useState(defaultLoc("receiving"));
  const [dest, setDest] = useState(defaultLoc("shipping"));
  const [priority, setPriority] = useState("Normal");
  const [load, setLoad] = useState(30);

  const update = (setter) => (v) => {
    setter(v);
  };
  React.useEffect(() => {
    if (!onPreview) return;
    const cell = (v) => {
      if (v.mode === "xy") {
        const x = Number(v.x), y = Number(v.y);
        return Number.isInteger(x) && Number.isInteger(y) ? { x, y } : null;
      }
      const z = zones.find((zz) => zz.id === v.zone);
      return z ? { x: z.dock.x, y: z.dock.y } : null;
    };
    onPreview({ pickup: cell(pickup), destination: cell(dest) });
  }, [pickup, dest, zones, onPreview]);

  const body = () => ({ pickup: locToApi(pickup), destination: locToApi(dest), priority, load_pct: Number(load) });
  const pending = state.summary.pending_tasks;

  return (
    <Card title="Quick Dispatch" subtitle="Create a delivery task, then let the dispatcher pick a robot.">
      <div className="stack" style={{ gap: 12 }}>
        <LocationPicker label="Pickup location" zones={zones} value={pickup} onChange={update(setPickup)} />
        <LocationPicker label="Destination" zones={zones} value={dest} onChange={update(setDest)} />
        <div>
          <div className="small muted" style={{ fontWeight: 500, marginBottom: 4 }}>Priority</div>
          <div className="seg" role="group" aria-label="Priority">
            {["Low", "Normal", "Urgent"].map((p) => (
              <button key={p} type="button" className={`${priority === p ? "on" : ""} ${p === "Urgent" ? "urgent" : ""}`} onClick={() => setPriority(p)} aria-pressed={priority === p}>
                {p}
              </button>
            ))}
          </div>
        </div>
        {withLoad && (
          <label className="field">
            Package load ({load}% of robot capacity)
            <input type="range" min="0" max="100" value={load} onChange={(e) => setLoad(e.target.value)} />
          </label>
        )}
        <div className="row">
          <button className="btn primary" disabled={fleet.busy} onClick={() => fleet.createTask(body())}>
            <Icon name="plus" size={16} /> Create Task
          </button>
          <button className="btn amber" disabled={fleet.busy || pending === 0} onClick={() => fleet.dispatch()} title={pending === 0 ? "No pending tasks" : "Assign the next pending task"}>
            <Icon name="bolt" size={16} /> Assign Best Robot
          </button>
        </div>
        <div className="row small muted">
          <span>Dispatcher:</span>
          <DispatcherSelect fleet={fleet} />
          <span className="right">{pending} pending</span>
        </div>
      </div>
    </Card>
  );
}

export function DispatcherSelect({ fleet }) {
  return (
    <div className="seg" role="group" aria-label="Dispatcher">
      {[["ai", "AI (TensorFlow)"], ["baseline", "Baseline"]].map(([k, label]) => (
        <button key={k} type="button" className={fleet.dispatcher === k ? "on" : ""} style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => fleet.setDispatcher(k)} aria-pressed={fleet.dispatcher === k}>
          {label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- AI dispatch summary
export function DecisionSummary({ decision, message }) {
  if (!decision) {
    return (
      <Card title="AI Dispatch Summary">
        {message ? <div className="banner warn" style={{ marginBottom: 0 }}><Icon name="alert" /><div>{message}</div></div> : <div className="empty">No assignment yet. Create a task and click “Assign Best Robot”.</div>}
      </Card>
    );
  }
  const d = decision;
  return (
    <Card title="AI Dispatch Summary" subtitle={`${d.id} · ${d.task_id} · ${d.dispatcher === "ai" ? "TensorFlow prediction" : "baseline formula"}`}>
      <dl className="kv">
        <dt>Selected robot</dt><dd>{d.robot_id}</dd>
        <dt>Predicted completion time</dt><dd className="mono">{fmtNum(d.predicted_seconds, 1)} s</dd>
        <dt>Estimated route distance</dt><dd className="mono">{d.route_distance} cells</dd>
        <dt>Battery level</dt><dd className="mono">{d.battery_pct}% (needs {d.battery_needed_pct}%)</dd>
      </dl>
      <div className="explain"><b>Why this robot:</b> {d.explanation}</div>
    </Card>
  );
}

export function CandidateTable({ decision }) {
  if (!decision) return null;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr><th>Robot</th><th>Result</th><th>Battery</th><th>Route</th><th>Needs</th><th>Congestion</th><th>Predicted</th></tr>
        </thead>
        <tbody>
          {decision.candidates.map((c) => (
            <tr key={c.robot_id} className={`${c.robot_id === decision.robot_id ? "sel" : ""} ${c.feasible ? "" : "rejected"}`}>
              <td><b>{c.robot_id}</b></td>
              <td>{c.robot_id === decision.robot_id ? <Badge kind="ok">Selected</Badge> : c.feasible ? <Badge kind="Moving">Feasible</Badge> : <Badge kind="bad">Rejected</Badge>}
                {!c.feasible && <div className="small">{c.reason}</div>}</td>
              <td className="mono">{c.battery_pct}%</td>
              <td className="mono">{c.route_distance ?? "—"}</td>
              <td className="mono">{c.battery_needed_pct != null ? `${c.battery_needed_pct}%` : "—"}</td>
              <td className="mono">{c.congestion ?? "—"}</td>
              <td className="mono">{c.predicted_seconds != null ? `${c.predicted_seconds} s` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- activity feed
const EVENT_STYLE = {
  task_created: ["plus", ""], robot_assigned: ["bolt", ""], robot_moving: ["play", ""], task_completed: ["check", "ok"],
  robot_charging: ["battery", "warn"], charging_complete: ["battery", "ok"], assignment_rejected: ["alert", "warn"],
  violation: ["alert", "bad"], warning: ["alert", "warn"], robot_status: ["robot", ""], robot_idle: ["clock", ""],
  robot_returning: ["pin", ""], task_requeued: ["alert", "warn"], obstacle: ["map", "warn"], reset: ["reset", ""],
};

export function ActivityFeed({ events, limit = 40 }) {
  return (
    <Card title="Recent Activity" subtitle="Live events from the simulation">
      {events.length === 0 ? (
        <div className="empty">No events yet.</div>
      ) : (
        <ul className="feed">
          {events.slice(0, limit).map((e) => {
            const [icon, tone] = EVENT_STYLE[e.type] || ["info", ""];
            return (
              <li key={e.id}>
                <span className={`ico ${tone}`}><Icon name={icon} size={14} /></span>
                <span>{e.message}</span>
                <time>{Math.round(e.sim_time)} s</time>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- simulation controls
export function SimControls({ fleet, state }) {
  return (
    <div className="row">
      <button className="btn" disabled={fleet.busy || fleet.running} onClick={() => fleet.step(1)}><Icon name="step" size={15} /> Step</button>
      <button className="btn" disabled={fleet.busy || fleet.running} onClick={() => fleet.step(10)}>+10 steps</button>
      {fleet.running ? (
        <button className="btn danger" onClick={fleet.stopRun}><Icon name="pause" size={15} /> Stop</button>
      ) : (
        <button className="btn primary" disabled={fleet.busy} onClick={() => fleet.startRun()}><Icon name="play" size={15} /> Run</button>
      )}
      <label className="row small" style={{ gap: 6 }}>
        <input type="checkbox" checked={fleet.autoDispatch} onChange={(e) => fleet.setAutoDispatch(e.target.checked)} />
        Auto-dispatch each step
      </label>
      <span className="small muted mono">tick {state.sim.tick} · {state.sim.time_s} s simulated</span>
    </div>
  );
}
