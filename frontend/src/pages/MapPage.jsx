import React, { useState } from "react";
import { Badge, Card, locText, robotColor } from "../components/Common.jsx";
import WarehouseMap from "../components/WarehouseMap.jsx";

export default function MapPage({ fleet, state }) {
  const [editing, setEditing] = useState(false);
  const robots = state.robots;
  const sel = robots.find((r) => r.id === fleet.selectedRobot);
  const zones = state.warehouse.zones;
  const blockedSet = new Set(state.warehouse.obstacles.map((o) => `${o.x},${o.y}`));

  const onCell = editing ? (x, y) => fleet.toggleObstacle(x, y, !blockedSet.has(`${x},${y}`)) : undefined;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Warehouse Map</h1>
          <p>10 × 8 grid with six zones. Select a robot to see its assigned route.</p>
        </div>
        <label className="row small" style={{ gap: 6 }}>
          <input type="checkbox" checked={editing} onChange={(e) => setEditing(e.target.checked)} />
          Edit obstacles (click a cell to block / unblock it)
        </label>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.7fr) minmax(0,1fr)", alignItems: "start" }}>
        <Card title="Interactive map" subtitle={editing ? "Edit mode: blocked cells are avoided by A*. Changes that would strand a robot are refused." : "Positions update every time the simulation advances."}>
          <WarehouseMap state={state} selectedRobot={fleet.selectedRobot} onSelectRobot={fleet.selectRobot} onCellClick={onCell} editable={editing} />
        </Card>
        <div className="stack">
          <Card title="Robots" subtitle="Click to highlight a route">
            <div className="stack" style={{ gap: 6 }}>
              {robots.map((r) => (
                <button key={r.id} className={`btn ${fleet.selectedRobot === r.id ? "primary" : ""}`} style={{ justifyContent: "flex-start", gap: 10 }} onClick={() => fleet.selectRobot(fleet.selectedRobot === r.id ? null : r.id)}>
                  <span className="swatch" style={{ background: robotColor(r.id) }} />
                  <b>{r.id}</b>
                  <Badge kind={r.status} />
                  <span className="right small mono">({r.x},{r.y}) · {r.battery}%</span>
                </button>
              ))}
            </div>
          </Card>
          <Card title={sel ? `${sel.id} route` : "Route details"}>
            {!sel ? (
              <div className="empty">Select a robot.</div>
            ) : sel.route.length > 1 ? (
              <>
                <p className="small muted" style={{ marginBottom: 6 }}>
                  {sel.route_kind === "returning" ? "Returning to a charging bay" : `Delivering ${sel.task_id}`} · {sel.route.length - 1} cells ahead · phase: {sel.phase.replace("_", " ")}
                </p>
                <p className="mono small">{sel.route.map((p) => `(${p.x},${p.y})`).join(" → ")}</p>
              </>
            ) : (
              <div className="empty">{sel.id} has no active route ({sel.status.toLowerCase()}).</div>
            )}
          </Card>
          <Card title="Zones">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {zones.map((z) => (
                <li key={z.id} className="small" style={{ marginBottom: 4 }}>
                  <b>{z.name}</b> — {z.description} <span className="muted">Dock {locText({ x: z.dock.x, y: z.dock.y }, [])}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
