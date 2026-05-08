# Ship Management SaaS MVP Setup

This project has two local apps:

- `backend`: FastAPI API with three in-memory synthetic voyages, incidents, and response recommendations
- `frontend`: Next.js dashboard that consumes the REST and WebSocket APIs

No database, authentication, billing, Docker, Kafka, external AI agents, or real maritime APIs are included in this MVP.

## Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API runs at:

```text
http://localhost:8000
```

Useful endpoints:

```text
GET  http://localhost:8000/api/v1/voyages
WS   ws://localhost:8000/api/v1/ws/voyages
GET  http://localhost:8000/api/v1/incidents
WS   ws://localhost:8000/api/v1/ws/incidents
GET  http://localhost:8000/api/v1/recommendations
WS   ws://localhost:8000/api/v1/ws/recommendations
POST http://localhost:8000/api/v1/simulation/reset
```

Legacy aliases (`/voyages`, `/incidents`, `/recommendations`, and `/ws/*`) still work. The stable integration contract for new UI and AI-agent consumers is `/api/v1/*`.

## Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at:

```text
http://localhost:3000
```

## How Live Updates Work

The backend keeps three voyages in memory. A deterministic simulator loop updates them every 3 seconds by advancing each ship along its planned route, recalculating current position, progress, ETA, fuel, distance, risk, and speed. Demo time is accelerated so each tick advances 36 simulated minutes.

`status` is the voyage lifecycle, currently `Underway` or `Arrived`. `incident` is separate and nullable. An incident can slow a ship down, but it does not replace the voyage status.

Incidents flow through their own endpoint and WebSocket. The backend also generates simple response recommendations for active incidents through `recommender.py`, which is designed to be replaced by a real AI service later.

For the AI agent team, use:

```text
http://localhost:8000/docs
http://localhost:8000/openapi.json
API_CONTRACT.md
```

The frontend fetches the first snapshots from `/voyages`, `/incidents`, and `/recommendations`, then connects to all three matching WebSocket streams. Every WebSocket message replaces that part of dashboard state so the map, summary cards, incident panel, AI response assistant, and voyage cards update live.

The map plots each ship from `currentPosition.lat` and `currentPosition.lng` and draws route lines from `route`. Browser internet access is required for the OpenStreetMap background tiles.
