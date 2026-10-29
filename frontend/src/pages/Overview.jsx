import React, { useState } from "react";
import { Card, StatCard } from "../components/Common.jsx";
import { BatteryBar } from "../components/Common.jsx";
import WarehouseMap from "../components/WarehouseMap.jsx";
import { ActivityFeed, DecisionSummary, QuickDispatch, SimControls } from "../components/Panels.jsx";

export default function Overview({ fleet, state }) {
  const s = state.summary;
  const [preview, setPreview] = useState(null);
  const setPreviewStable = React.useCallback((p) => setPreview(p), []);
  const lastTask = fleet.lastMessage;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Live summary of the simulated warehouse. All figures come from the backend simulation state.</p>
        </div>
        <SimControls fleet={fleet} state={state} />
      </div>

      <div className="grid cols-6" style={{ marginBottom: 16 }}>
        <StatCard icon="robot" label="Total robots" value={s.total_robots} sub={`${s.robots_by_status.Offline} offline`} />
        <StatCard icon="check" label="Available robots" value={s.available_robots} sub={`${s.robots_by_status.Charging} charging`} />
        <StatCard icon="play" label="Active tasks" value={s.active_tasks} sub={`${s.robots_by_status.Moving + s.robots_by_status.Assigned} robots working`} />
        <StatCard icon="clock" label="Pending tasks" value={s.pending_tasks} sub="waiting for a robot" />
        <StatCard icon="package" label="Completed tasks" value={s.completed_tasks} sub={`of ${s.total_tasks} created`} />
        <StatCard icon="battery" label="Fleet battery" value={`${s.battery_avg}%`} sub={`min ${s.battery_min}% · max ${s.battery_max}%`}>
          <div style={{ marginTop: 8 }}><BatteryBar value={s.battery_avg} /></div>
        </StatCard>
      </div>

      <div className="grid overview-grid">
        <div className="stack">
          <Card title="Warehouse Map Preview" subtitle="Top-down view · click a robot to highlight its route"
            actions={<button className="btn sm" onClick={() => fleet.navigate("map")}>Open full map</button>}>
            <WarehouseMap state={state} selectedRobot={fleet.selectedRobot} onSelectRobot={fleet.selectRobot} preview={preview} />
          </Card>
          <ActivityFeed events={state.events} />
        </div>
        <div className="stack">
          <QuickDispatch fleet={fleet} state={state} onPreview={setPreviewStable} />
          <DecisionSummary decision={state.last_decision} message={lastTask && !lastTask.assigned ? lastTask.message : null} />
        </div>
      </div>
    </>
  );
}
