import React from "react";
import { robotColor } from "./Common.jsx";

const CELL = 60;
const STATUS_RING = { Idle: "#3f8f5b", Assigned: "#e2a16f", Moving: "#e2a16f", Charging: "#d4b21a", Offline: "#c23b3b" };

// Top-down 2D map drawn as SVG from live simulation state.
// props: state, selectedRobot, onSelectRobot, onCellClick, editable, preview {pickup,destination}
export default function WarehouseMap({ state, selectedRobot, onSelectRobot, onCellClick, editable = false, preview = null, compact = false }) {
  const { warehouse: wh, robots, tasks } = state;
  const W = wh.width * CELL;
  const H = wh.height * CELL;
  const cx = (x) => x * CELL + CELL / 2;
  const cy = (y) => y * CELL + CELL / 2;

  const open = tasks.filter((t) => t.status !== "Completed");
  // package icon at the pickup of tasks whose cargo has not been collected; target at open destinations
  const pickups = open.filter((t) => t.status === "Pending" || t.status === "Assigned");
  const robotRoutes = robots.filter((r) => r.route && r.route.length > 1);
  const selected = robots.find((r) => r.id === selectedRobot);

  return (
    <div>
      <svg className={`map-svg ${editable ? "editable" : ""}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Warehouse map">
        <defs>
          <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="8" height="8" fill="#2b3a41" />
            <rect width="4" height="8" fill="#0d1417" />
          </pattern>
        </defs>

        {/* floor grid */}
        {Array.from({ length: wh.height }).map((_, y) =>
          Array.from({ length: wh.width }).map((_, x) => (
            <rect key={`g${x}-${y}`} className="cell" x={x * CELL} y={y * CELL} width={CELL} height={CELL} fill="none" stroke="#dcd6ca" strokeWidth="1"
              onClick={onCellClick ? () => onCellClick(x, y) : undefined} />
          ))
        )}

        {/* zones */}
        {wh.zones.map((z) => (
          <g key={z.id} pointerEvents="none">
            <rect x={z.x * CELL + 2} y={z.y * CELL + 2} width={z.w * CELL - 4} height={z.h * CELL - 4} rx="8" fill={z.color} stroke="#0d1417" strokeOpacity="0.35" strokeWidth="1.5" />
          </g>
        ))}

        {/* obstacles (click targets stay active in edit mode) */}
        {wh.obstacles.map((o) => (
          <g key={`o${o.x}-${o.y}`} onClick={onCellClick ? () => onCellClick(o.x, o.y) : undefined} style={onCellClick ? { cursor: "pointer" } : undefined}>
            <rect x={o.x * CELL + 3} y={o.y * CELL + 3} width={CELL - 6} height={CELL - 6} rx="6" fill="url(#hatch)" stroke="#0d1417" />
            <title>{`Obstacle at (${o.x},${o.y})`}</title>
          </g>
        ))}

        {/* routes */}
        <g pointerEvents="none" fill="none" strokeLinecap="round" strokeLinejoin="round">
          {robotRoutes.map((r) => {
            const isSel = r.id === selectedRobot;
            const color = robotColor(r.id);
            const pts = r.route.map((p) => `${cx(p.x)},${cy(p.y)}`).join(" ");
            return (
              <g key={`route-${r.id}`} opacity={selectedRobot && !isSel ? 0.35 : 1}>
                <polyline points={pts} stroke={color} strokeOpacity="0.22" strokeWidth={isSel ? 16 : 11} />
                <polyline points={pts} stroke={color} strokeWidth={isSel ? 4 : 2.5} strokeDasharray={r.route_kind === "returning" ? "3 7" : isSel ? "0" : "8 5"} />
              </g>
            );
          })}
        </g>

        {/* pickup (package) and destination (target) markers */}
        <g pointerEvents="none">
          {pickups.map((t) => (
            <g key={`p${t.id}`} transform={`translate(${cx(t.pickup.x)},${cy(t.pickup.y)})`}>
              <rect x="-11" y="-11" width="22" height="22" rx="4" fill="#e2a16f" stroke="#0d1417" strokeWidth="1.5" />
              <path d="M-11 -3h22M0 -11v8" stroke="#0d1417" strokeWidth="1.5" />
              <text y="23" textAnchor="middle" fontSize="9" fontWeight="700" fill="#0d1417">{t.id}</text>
            </g>
          ))}
          {open.map((t) => (
            <g key={`d${t.id}`} transform={`translate(${cx(t.destination.x)},${cy(t.destination.y)})`}>
              <circle r="11" fill="#fff" stroke="#c23b3b" strokeWidth="2.5" />
              <circle r="5" fill="none" stroke="#c23b3b" strokeWidth="2.5" />
              <circle r="1.6" fill="#c23b3b" />
            </g>
          ))}
          {preview?.pickup && (
            <g transform={`translate(${cx(preview.pickup.x)},${cy(preview.pickup.y)})`}>
              <rect x="-13" y="-13" width="26" height="26" rx="5" fill="none" stroke="#0d1417" strokeWidth="2" strokeDasharray="4 3" />
            </g>
          )}
          {preview?.destination && (
            <g transform={`translate(${cx(preview.destination.x)},${cy(preview.destination.y)})`}>
              <circle r="14" fill="none" stroke="#0d1417" strokeWidth="2" strokeDasharray="4 3" />
            </g>
          )}
        </g>

        {/* robots */}
        {robots.map((r) => {
          const color = r.status === "Offline" ? "#8c9498" : robotColor(r.id);
          const isSel = r.id === selectedRobot;
          return (
            <g key={r.id} className="robot" transform={`translate(${cx(r.x)},${cy(r.y)})`} onClick={onSelectRobot ? () => onSelectRobot(r.id) : undefined} style={onSelectRobot ? { cursor: "pointer" } : undefined}>
              <title>{`${r.id} · ${r.status} · battery ${r.battery}% · (${r.x},${r.y})`}</title>
              {isSel && <circle r="25" fill="none" stroke="#e2a16f" strokeWidth="3" />}
              <rect x="-17" y="-14" width="34" height="28" rx="7" fill={color} stroke="#0d1417" strokeWidth="1.5" />
              <rect x="-10" y="-17" width="20" height="5" rx="2.5" fill="#0d1417" opacity="0.8" />
              <circle cx="-9" cy="14" r="3.4" fill="#0d1417" />
              <circle cx="9" cy="14" r="3.4" fill="#0d1417" />
              <text y="4" textAnchor="middle" fontSize="11" fontWeight="700" fill="#fff">{r.id.replace("R", "")}</text>
              <circle cx="17" cy="-14" r="5.5" fill={STATUS_RING[r.status] || "#999"} stroke="#fff" strokeWidth="1.5" />
              {r.status === "Offline" && <path d="M-9 -8l18 16M9 -8l-18 16" stroke="#c23b3b" strokeWidth="3" />}
              {r.load_pct > 0 && <rect x="-8" y="-9" width="16" height="3" rx="1.5" fill="#fff0dd" />}
            </g>
          );
        })}
        {/* zone labels sit above robots, with a halo so they stay readable */}
        <g pointerEvents="none">
          {wh.zones.map((z) => (
            <text key={`l${z.id}`} x={z.x * CELL + 8} y={z.y * CELL + 13} fontSize="11" fontWeight="700" fill="#0d1417" stroke="#ffffff" strokeWidth="3" strokeOpacity="0.8" paintOrder="stroke">{z.name}</text>
          ))}
        </g>
      </svg>

      {!compact && (
        <>
          <div className="legend">
            <span><i style={{ background: "#2b6f8a" }} /> Robot (number = ID)</span>
            <span><i style={{ background: "#e2a16f" }} /> Pickup (package)</span>
            <span><i style={{ background: "#fff", borderColor: "#c23b3b", borderWidth: 2, borderRadius: 99 }} /> Destination (target)</span>
            <span><i style={{ background: "#0d1417" }} /> Obstacle</span>
            <span>Solid line = delivery route · dotted = returning</span>
            <span>Status dot: <b style={{ color: "#3f8f5b" }}>●</b> idle <b style={{ color: "#e2a16f" }}>●</b> working <b style={{ color: "#d4b21a" }}>●</b> charging <b style={{ color: "#c23b3b" }}>●</b> offline</span>
          </div>
          {selected && (
            <p className="small muted" style={{ marginTop: 8 }}>
              Selected: <b>{selected.id}</b> — {selected.status}
              {selected.task_id ? `, task ${selected.task_id}` : ""}
              {selected.route.length > 1 ? `, ${selected.route.length - 1} cells of route ahead (highlighted).` : "."}
            </p>
          )}
        </>
      )}
    </div>
  );
}
