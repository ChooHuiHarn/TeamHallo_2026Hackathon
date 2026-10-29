# FleetPilot AI — Autonomous Warehouse Fleet Dispatcher

FleetPilot AI is a **computer simulation** of a smart warehouse. Six simulated autonomous mobile robots (R01–R06) carry packages between six zones. A **TensorFlow/Keras regression model** predicts how long each candidate robot would take, and a dispatcher assigns the task to the feasible robot with the lowest predicted time. A non-AI **baseline dispatcher** runs the same scenarios for comparison.

> **This is a simulation. It does not control real robots.** The TensorFlow model is trained on **synthetic data** generated from the simulator's own documented rules, so its accuracy does not establish real-world warehouse accuracy.

## What is in the box

| Folder | Contents |
| --- | --- |
| `backend/app/` | FastAPI app, warehouse grid, A* routing, deterministic simulation, dispatch, baseline, experiments |
| `backend/app/ml/` | Loads the trained model once at startup and runs real TensorFlow inference |
| `backend/tests/` | Pytest suite |
| `ml/` | Synthetic dataset generator and training/evaluation script |
| `models/` | Saved model + preprocessing + metadata (created by training) |
| `frontend/` | React + Vite interface (five pages) |
| `docs/` | Architecture, API, QA log, executive summary, pitch script, demo instructions |

## Setup

Requirements: Python 3.10–3.12 (3.12 recommended for TensorFlow), Node.js 18+.

```bash
# 1. Python environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Train the TensorFlow model (about a minute on a laptop CPU)
python ml/train_model.py
#    -> writes models/duration_model.keras, preprocessing.json, metadata.json, test_predictions.json
#    -> prints MAE / RMSE / R2 on the held-out synthetic test split

# 3. Start the backend (from the backend/ folder)
cd backend
uvicorn app.main:app --reload --port 8000
#    API docs: http://localhost:8000/docs

# 4. Start the frontend (new terminal)
cd frontend
npm install
npm run dev
#    Open http://localhost:5173
```

If the backend is not on `http://localhost:8000`, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL`.

## Run the tests

```bash
cd backend
pytest -v
```

Tests that need TensorFlow, a trained model, or FastAPI skip themselves with a clear message if those are missing. After step 2 above, the model tests run for real.

## Quick demo (2 minutes)

1. Open **Overview**. Click **Create Task** (Receiving → Shipping, Normal), then **Assign Best Robot**. Read the AI Dispatch Summary: selected robot, predicted time, route, battery and the reason.
2. Click **Run**. Watch robots move on the map, batteries drop, tasks complete, robots return or charge.
3. Go to **Robot Fleet**, select a robot, set its battery to 12 %, then dispatch a long task: that robot is rejected with a battery explanation.
4. Go to **AI Analytics** and click **Run comparison** to measure AI vs baseline on identical scenarios.
5. Click **Reset Simulation** and repeat. The starting state is always the same.

See `docs/demo_instructions.md` for the full script.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Red banner “Backend unavailable” | Start the backend (`uvicorn app.main:app --port 8000` inside `backend/`) and click Retry. |
| Yellow banner “TensorFlow model not loaded” | Run `python ml/train_model.py`, then restart the backend. The Baseline dispatcher still works meanwhile. |
| `ModuleNotFoundError: tensorflow` | Install it: `pip install tensorflow`. Use Python 3.10–3.12; very new Python versions may lack TensorFlow wheels. |
| Browser shows CORS errors | The backend allows `localhost:5173` and `127.0.0.1:5173`. For another origin set `FLEETPILOT_CORS_ORIGINS=http://host:port`. |
| `models/` is empty | Training has not been run yet (step 2). |
| Task stays Pending | Expected when no robot is feasible (battery, charging, offline, blocked route). The reason is shown in the banner and the queue table. |
| Port already in use | Use `--port 8001` for uvicorn and set `VITE_API_URL` accordingly. |

## Honest limitations

- The model learns the simulator's rules from synthetic data. Low error here means it agrees with the simulator, not that it would predict a real warehouse.
- The comparison between AI and baseline is only as meaningful as the scenarios; results are reported as measured, including ties and cases where the baseline wins.
- State is held in memory in one process; restarting the backend resets everything.
