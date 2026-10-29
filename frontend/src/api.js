// Thin client for the FleetPilot AI REST API. Every function returns parsed JSON
// or throws an Error whose message is safe to show to the user.
export const API_BASE = import.meta.env?.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    const err = new Error(`Cannot reach the backend at ${API_BASE}. Is it running? (uvicorn app.main:app --port 8000)`);
    err.offline = true;
    throw err;
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    const detail = data && data.detail;
    const message = typeof detail === "string" ? detail : `Request failed (HTTP ${response.status}).`;
    const err = new Error(message);
    err.status = response.status;
    throw err;
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  state: () => request("/api/state"),
  createTask: (body) => request("/api/tasks", { method: "POST", body }),
  dispatch: (dispatcher, taskId) =>
    request("/api/dispatch/next", { method: "POST", body: { dispatcher, task_id: taskId || null } }),
  step: (steps, autoDispatch, dispatcher) =>
    request("/api/simulation/step", { method: "POST", body: { steps, auto_dispatch: autoDispatch, dispatcher } }),
  reset: (safetyReserve) =>
    request("/api/simulation/reset", { method: "POST", body: safetyReserve == null ? {} : { safety_reserve: safetyReserve } }),
  metrics: () => request("/api/metrics"),
  compare: (body) => request("/api/experiments/compare", { method: "POST", body }),
  patchRobot: (id, body) => request(`/api/robots/${id}`, { method: "PATCH", body }),
  setObstacle: (x, y, blocked) => request("/api/map/obstacles", { method: "POST", body: { x, y, blocked } }),
  setReserve: (safety_reserve) => request("/api/config", { method: "PATCH", body: { safety_reserve } }),
};
