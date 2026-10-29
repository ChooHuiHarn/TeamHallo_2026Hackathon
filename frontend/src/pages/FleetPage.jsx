import React, { useState } from "react";
import { Badge, BatteryBar, Card, locText, robotColor } from "../components/Common.jsx";

function RobotCard({ r, selected, onSelect }) {
  return (
    <button className={`card robot-card ${selected ? "sel" : ""} ${r.status === "Offline" ? "offline" : ""}`} onClick={onSelect} aria-pressed={selected}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="swatch" style={{ background: robotColor(r.id) }} />
          <h3>{r.id}</h3>
        </div>
        <Badge kind={r.status} />
      </div>
      <div className="small muted" style={{ marginBottom: 4 }}>Battery {r.battery}%</div>
      <BatteryBar value={r.battery} />
      <dl className="kv" style={{ marginTop: 10 }}>
        <dt>Position</dt><dd className="mono">({r.x}, {r.y})</dd>
        <dt>Load</dt><dd className="mono">{r.load_pct}%</dd>
        <dt>Task</dt><dd>{r.task_id || "—"}</dd>
      </dl>
    </button>
  );
}

export default function FleetPage({ fleet, state }) {
  const [battery, setBattery] = useState(50);
  const sel = state.robots.find((r) => r.id === fleet.selectedRobot) || null;
  const task = sel && sel.task_id ? state.tasks.find((t) => t.id === sel.task_id) : null;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Robot Fleet</h1>
          <p>Six simulated AMRs (R01–R06). Select a robot to inspect it.</p>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr)", alignItems: "start" }}>
        <div className="grid cols-3">
          {state.robots.map((r) => (
            <RobotCard key={r.id} r={r} selected={sel?.id === r.id} onSelect={() => fleet.selectRobot(sel?.id === r.id ? null : r.id)} />
          ))}
        </div>
        <Card title={sel ? `${sel.id} details` : "Robot inspector"} subtitle={sel ? "Statistics measured in this simulation run" : undefined}>
          {!sel ? (
            <div className="empty">Select a robot card to see details.</div>
          ) : (
            <div className="stack" style={{ gap: 14 }}>
              <dl className="kv">
                <dt>Status</dt><dd><Badge kind={sel.status} /></dd>
                <dt>Phase</dt><dd>{sel.phase.replace("_", " ")}</dd>
                <dt>Position</dt><dd className="mono">({sel.x}, {sel.y}) {state.warehouse.zones.find((z) => sel.x >= z.x && sel.x < z.x + z.w && sel.y >= z.y && sel.y < z.y + z.h)?.name || "corridor"}</dd>
                <dt>Battery</dt><dd className="mono">{sel.battery}%</dd>
                <dt>Load</dt><dd className="mono">{sel.load_pct}%</dd>
                <dt>Current task</dt><dd>{sel.task_id || "None"}</dd>
                {task && <><dt>Route</dt><dd className="small">{locText(task.pickup, state.warehouse.zones)} → {locText(task.destination, state.warehouse.zones)}</dd></>}
                <dt>Route ahead</dt><dd className="mono">{Math.max(sel.route.length - 1, 0)} cells</dd>
                <dt>Tasks completed</dt><dd className="mono">{sel.tasks_completed}</dd>
                <dt>Distance travelled</dt><dd className="mono">{sel.distance_travelled} cells</dd>
                <dt>Working / idle / charging</dt><dd className="mono">{sel.busy_s} / {sel.idle_s} / {sel.charging_s} s</dd>
              </dl>
              <div>
                <div className="small muted" style={{ fontWeight: 500, marginBottom: 6 }}>Demonstration controls</div>
                <div className="row">
                  <input type="number" min="0" max="100" value={battery} onChange={(e) => setBattery(e.target.value)} style={{ width: 80 }} aria-label="Battery percentage" />
                  <button className="btn sm" disabled={fleet.busy} onClick={() => fleet.patchRobot(sel.id, { battery: Number(battery) })}>Set battery %</button>
                  {sel.status === "Offline" ? (
                    <button className="btn sm" disabled={fleet.busy} onClick={() => fleet.patchRobot(sel.id, { offline: false })}>Bring online</button>
                  ) : (
                    <button className="btn sm danger" disabled={fleet.busy} onClick={() => fleet.patchRobot(sel.id, { offline: true })}>Take offline</button>
                  )}
                </div>
                <p className="small muted" style={{ marginTop: 6 }}>Use these to test the rules: low-battery robots are rejected for long tasks; offline and charging robots are never assigned.</p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
