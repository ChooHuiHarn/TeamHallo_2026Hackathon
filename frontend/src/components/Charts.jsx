import React from "react";

const AI = "#e2a16f";
const BASE = "#86b0bd";
export { AI as AI_COLOR, BASE as BASE_COLOR };

// Grouped horizontal bars: one row per metric, AI vs baseline. Values are real run results.
export function CompareBars({ metrics }) {
  const rows = metrics.filter((m) => m.ai != null && m.baseline != null);
  if (!rows.length) return <div className="empty">Not evaluated</div>;
  return (
    <div className="chart" role="img" aria-label="AI versus baseline comparison">
      {rows.map((m) => {
        const max = Math.max(m.ai, m.baseline, 1e-9);
        return (
          <div key={m.key} style={{ marginBottom: 14 }}>
            <div className="row small" style={{ justifyContent: "space-between" }}>
              <b>{m.label}</b>
              <span className="muted">{m.better === "lower" ? "lower is better" : "higher is better"}</span>
            </div>
            {[["AI", m.ai, AI], ["Baseline", m.baseline, BASE]].map(([name, v, color]) => (
              <div key={name} className="row" style={{ gap: 8, marginTop: 3, flexWrap: "nowrap" }}>
                <span className="small muted" style={{ width: 56 }}>{name}</span>
                <div className="bar" style={{ flex: 1, height: 12 }}>
                  <span style={{ width: `${(v / max) * 100}%`, background: color }} />
                </div>
                <span className="small mono" style={{ width: 70, textAlign: "right" }}>{Number(v).toFixed(1)} {m.unit}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// Scatter of predicted vs actual seconds with the ideal y = x line.
export function Scatter({ points, width = 460, height = 320 }) {
  if (!points || !points.length) return <div className="empty">Not evaluated</div>;
  const pad = { l: 44, r: 12, t: 10, b: 36 };
  const max = Math.ceil(Math.max(...points.map((p) => Math.max(p.actual, p.predicted))) / 20) * 20 || 20;
  const sx = (v) => pad.l + (v / max) * (width - pad.l - pad.r);
  const sy = (v) => height - pad.b - (v / max) * (height - pad.t - pad.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * max));
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Predicted versus actual duration">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={width - pad.r} y1={sy(t)} y2={sy(t)} stroke="#e4e5e6" />
          <line y1={pad.t} y2={height - pad.b} x1={sx(t)} x2={sx(t)} stroke="#f0f1f1" />
          <text x={pad.l - 6} y={sy(t) + 4} textAnchor="end" fontSize="10" fill="#5b676c">{t}</text>
          <text x={sx(t)} y={height - pad.b + 14} textAnchor="middle" fontSize="10" fill="#5b676c">{t}</text>
        </g>
      ))}
      <line x1={sx(0)} y1={sy(0)} x2={sx(max)} y2={sy(max)} stroke="#0d1417" strokeDasharray="5 4" strokeWidth="1.2" />
      {points.map((p, i) => (
        <circle key={i} cx={sx(p.actual)} cy={sy(p.predicted)} r="3" fill={AI} fillOpacity="0.65" stroke="#c9722d" strokeWidth="0.6" />
      ))}
      <text x={(pad.l + width - pad.r) / 2} y={height - 4} textAnchor="middle" fontSize="11" fill="#0d1417">Actual duration (s)</text>
      <text transform={`translate(12 ${(height - pad.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fill="#0d1417">Predicted (s)</text>
    </svg>
  );
}

// One horizontal stacked bar per robot: busy / charging / idle / offline seconds.
export function UtilizationBars({ perRobot }) {
  const rows = perRobot || [];
  if (!rows.length) return <div className="empty">Not evaluated</div>;
  const parts = [["busy_s", "Working", "#e2a16f"], ["charging_s", "Charging", "#d4b21a"], ["idle_s", "Idle", "#86b0bd"], ["offline_s", "Offline", "#c23b3b"]];
  return (
    <div className="chart">
      {rows.map((r) => {
        const total = parts.reduce((s, [k]) => s + (r[k] || 0), 0);
        return (
          <div key={r.id} className="row" style={{ flexWrap: "nowrap", marginBottom: 8 }}>
            <b className="small" style={{ width: 34 }}>{r.id}</b>
            <div style={{ flex: 1, display: "flex", height: 14, borderRadius: 99, overflow: "hidden", background: "#eceded" }}>
              {total > 0 && parts.map(([k, label, color]) => (
                <div key={k} title={`${label}: ${r[k]} s`} style={{ width: `${(r[k] / total) * 100}%`, background: color }} />
              ))}
            </div>
            <span className="small mono muted" style={{ width: 120, textAlign: "right" }}>
              {r.utilization_pct == null ? "—" : `${r.utilization_pct}% working`}
            </span>
          </div>
        );
      })}
      <div className="legend">
        {parts.map(([k, label, color]) => (
          <span key={k}><i style={{ background: color }} /> {label}</span>
        ))}
      </div>
    </div>
  );
}
