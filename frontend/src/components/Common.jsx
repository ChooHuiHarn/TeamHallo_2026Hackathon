import React from "react";
import Icon from "./Icons.jsx";

export const ROBOT_COLORS = ["#2b6f8a", "#c9722d", "#5a7d3a", "#7c5aa6", "#1f9d8f", "#8a6d1d"];
export const robotColor = (id) => ROBOT_COLORS[(parseInt(String(id).slice(1), 10) - 1) % ROBOT_COLORS.length] || "#2b6f8a";

export function Badge({ kind, children }) {
  return <span className={`badge ${kind}`}>{children ?? kind}</span>;
}

export function BatteryBar({ value }) {
  const cls = value < 15 ? "crit" : value < 35 ? "low" : "";
  return (
    <div className={`bar ${cls}`} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100} aria-label="Battery">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Banner({ kind = "info", children, onClose }) {
  return (
    <div className={`banner ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon name={kind === "info" ? "info" : "alert"} />
      <div>{children}</div>
      {onClose && (
        <button className="btn sm" onClick={onClose} aria-label="Dismiss">
          <Icon name="x" size={14} />
        </button>
      )}
    </div>
  );
}

export function StatCard({ icon, label, value, sub, children }) {
  return (
    <div className="card stat">
      <div className="label">
        <Icon name={icon} size={15} /> {label}
      </div>
      <div className={`value mono${String(value).length > 9 ? " long" : ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
      {children}
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header>
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export const fmtTime = (s) => (s == null ? "—" : `${Math.round(s)} s`);
export const fmtNum = (v, d = 1) => (v == null || Number.isNaN(v) ? "Not evaluated" : Number(v).toFixed(d));
export const zoneName = (zones, id) => zones.find((z) => z.id === id)?.name || null;
export const locText = (loc, zones) => {
  const z = loc.zone ? zoneName(zones, loc.zone) : null;
  return z ? `${z} (${loc.x},${loc.y})` : `(${loc.x},${loc.y})`;
};
