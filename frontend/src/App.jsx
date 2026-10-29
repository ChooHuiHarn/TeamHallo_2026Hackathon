import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE } from "./api.js";
import Icon from "./components/Icons.jsx";
import { Banner } from "./components/Common.jsx";
import Overview from "./pages/Overview.jsx";
import MapPage from "./pages/MapPage.jsx";
import FleetPage from "./pages/FleetPage.jsx";
import DispatchPage from "./pages/DispatchPage.jsx";
import AnalyticsPage from "./pages/AnalyticsPage.jsx";

const NAV = [
  ["overview", "Overview", "overview"],
  ["map", "Warehouse Map", "map"],
  ["fleet", "Robot Fleet", "robot"],
  ["dispatch", "Task Dispatch", "dispatch"],
  ["analytics", "AI Analytics", "chart"],
];

export default function App() {
  const [page, setPage] = useState("overview");
  const [state, setState] = useState(null);
  const [offline, setOffline] = useState(null);       // message when the backend cannot be reached
  const [busy, setBusy] = useState(false);
  const [selectedRobot, setSelectedRobot] = useState(null);
  const [dispatcher, setDispatcher] = useState("ai");
  const [autoDispatch, setAutoDispatch] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);
  const runRef = useRef(false);

  const toast = useCallback((message, kind = "ok") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setState(await api.state());
      setOffline(null);
      return true;
    } catch (e) {
      setOffline(e.message);
      return false;
    }
  }, []);

  // initial load and a light connection check every 6 s
  useEffect(() => {
    refresh();
    const t = setInterval(() => { if (!runRef.current) refresh(); }, 6000);
    return () => clearInterval(t);
  }, [refresh]);

  // run an API action, then reload state; surface real errors (never fake successes)
  const act = useCallback(async (fn, { onOk, silent } = {}) => {
    setBusy(true);
    try {
      const res = await fn();
      await refresh();
      if (onOk) onOk(res);
      return res;
    } catch (e) {
      if (e.offline) setOffline(e.message);
      if (!silent) toast(e.message, "error");
      return null;
    } finally {
      setBusy(false);
    }
  }, [refresh, toast]);

  const fleet = {
    busy, running, dispatcher, autoDispatch, selectedRobot, lastMessage,
    setDispatcher, setAutoDispatch,
    navigate: setPage,
    selectRobot: setSelectedRobot,
    createTask: (body) => act(() => api.createTask(body), { onOk: (t) => toast(`Task ${t.id} created.`) }),
    dispatch: (taskId) => act(() => api.dispatch(dispatcher, taskId), {
      onOk: (r) => {
        setLastMessage(r);
        if (r.assigned) { setSelectedRobot(r.robot_id); toast(r.message); } else toast(r.message, "warn");
      },
    }),
    step: (n) => act(() => api.step(n, autoDispatch, dispatcher), {
      onOk: (r) => {
        const done = r.events.filter((e) => e.type === "task_completed").length;
        if (done) toast(`${done} task${done > 1 ? "s" : ""} completed.`);
        if (r.assignments.length) setLastMessage({ assigned: true });
      },
    }),
    startRun: () => {
      runRef.current = true;
      setRunning(true);
      const loop = async () => {
        while (runRef.current) {
          try {
            const r = await api.step(1, autoDispatch, dispatcher);
            if (r.assignments.length) setLastMessage({ assigned: true });
            const s = await api.state();
            setState(s);
            if (s.summary.pending_tasks + s.summary.active_tasks === 0 && s.robots.every((x) => x.status !== "Moving" && x.status !== "Assigned")) {
              runRef.current = false;
              toast("Run finished: no pending or active tasks left.");
            }
          } catch (e) {
            runRef.current = false;
            toast(e.message, "error");
            if (e.offline) setOffline(e.message);
          }
          await new Promise((res) => setTimeout(res, 450));
        }
        setRunning(false);
      };
      loop();
    },
    stopRun: () => { runRef.current = false; },
    reset: async () => {
      runRef.current = false;
      const ok = await act(() => api.reset(), { onOk: () => { setLastMessage(null); setSelectedRobot(null); toast("Simulation reset to the starting state."); } });
      return ok;
    },
    patchRobot: (id, body) => act(() => api.patchRobot(id, body), { onOk: () => toast(`${id} updated.`) }),
    toggleObstacle: (x, y, blocked) => act(() => api.setObstacle(x, y, blocked), { onOk: () => toast(blocked ? `Obstacle placed at (${x},${y}).` : `Obstacle removed at (${x},${y}).`) }),
    setReserve: (v) => act(() => api.setReserve(v), { onOk: () => toast(`Safety reserve set to ${v}%.`) }),
  };

  const Page = { overview: Overview, map: MapPage, fleet: FleetPage, dispatch: DispatchPage, analytics: AnalyticsPage }[page];
  const simStatus = offline ? "Backend offline" : state ? state.sim.status : "Connecting…";
  const pillClass = offline ? "bad" : state ? state.sim.status.toLowerCase() : "";
  const model = state?.model;

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          <div className="logo-mark"><Icon name="robot" size={18} strokeWidth={2.2} /></div>
          <div>FleetPilot AI<small>Simulation</small></div>
        </div>
        <div className="spacer" />
        <span className={`pill ${pillClass}`} title="Simulation status"><span className="dot" /> Simulation: {simStatus}{state && !offline ? ` · tick ${state.sim.tick}` : ""}</span>
        {model && (
          <span className={`pill hide-sm ${model.available ? "ok" : "bad"}`} title={model.error || "TensorFlow model"}>
            <span className="dot" /> Model: {model.status}
          </span>
        )}
        <button className="btn ghost-dark" disabled={busy || !state} onClick={fleet.reset}><Icon name="reset" size={15} /> Reset Simulation</button>
      </header>

      <nav className="sidebar" aria-label="Main navigation">
        {NAV.map(([id, label, icon]) => (
          <button key={id} className={`nav-btn ${page === id ? "active" : ""}`} onClick={() => setPage(id)} aria-current={page === id ? "page" : undefined} title={label}>
            <Icon name={icon} /> <span>{label}</span>
          </button>
        ))}
        <div className="note">Computer simulation only. No real robots are controlled.</div>
      </nav>

      <main className="main">
        {offline && (
          <Banner kind="error">
            <b>Backend unavailable.</b> {offline} <button className="btn sm" style={{ marginLeft: 8 }} onClick={refresh}>Retry</button>
          </Banner>
        )}
        {model && !model.available && !offline && (
          <Banner kind="warn">
            <b>TensorFlow model not loaded.</b> {model.error} Use the <b>Baseline</b> dispatcher meanwhile.
          </Banner>
        )}
        {!state ? (
          <div className="empty">{offline ? `Could not load data from ${API_BASE}.` : "Loading simulation state…"}</div>
        ) : (
          <Page fleet={fleet} state={state} />
        )}
      </main>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.kind === "ok" ? "" : t.kind}`}>{t.message}</div>)}
      </div>
    </div>
  );
}
