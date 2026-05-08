# Ship Management SaaS MVP

A simple maritime voyage demo with synthetic data.

The MVP shows three active voyages on a map. Each ship moves along a planned route in real time, and the dashboard updates through a WebSocket connection.

## Current Scope

Built:

- FastAPI backend
- In-memory synthetic voyage data
- Typed `/api/v1/*` API contract generated into FastAPI OpenAPI docs
- `GET /voyages`
- `WS /ws/voyages`
- `GET /incidents`
- `WS /ws/incidents`
- `GET /recommendations`
- `WS /ws/recommendations`
- Simulator that updates voyages every 3 seconds
- Demo time accelerated to 36 simulated minutes per tick
- Deterministic scenario events and `POST /api/v1/simulation/reset`
- Operational context: cargo, weather, destination port status, fuel, distance, and risk signals
- Backend-generated incident response recommendations
- Next.js + TypeScript + Tailwind frontend
- Leaflet map with route lines and moving ship markers
- Voyage summary cards
- Incident panel
- AI response assistant window
- Voyage cards



## Data Model

The MVP is voyage-centric:

```text
Voyage = ship + origin + destination + route + current position + status + optional incident + operational context
```

`status` and `incident` are intentionally separate.

- `status` describes the voyage lifecycle: `Underway` or `Arrived`
- `incident` is nullable and describes an operational issue, such as `Weather Delay` or `Engine Failure`
- An incident can slow a ship down, but it does not replace the voyage status
- Operational context includes cargo, weather, destination port status, fuel, distance, and risk signals

Shortened example:

```json
{
  "id": "voyage_001",
  "ship": {
    "id": "ship_001",
    "name": "MT Oceanic Explorer",
    "type": "Tanker",
    "imo": "IMO 9387421",
    "flag": "Marshall Islands",
    "operator": "Oceanic Maritime"
  },
  "origin": {
    "name": "Boston",
    "country": "USA",
    "unLocode": "USBOS",
    "lat": 42.3601,
    "lng": -71.0589
  },
  "destination": {
    "name": "Rotterdam",
    "country": "Netherlands",
    "unLocode": "NLRTM",
    "lat": 51.9244,
    "lng": 4.4777
  },
  "route": [
    [42.3601, -71.0589],
    [43.1, -58.0],
    [45.0, -42.5],
    [49.2, -18.0],
    [51.9244, 4.4777]
  ],
  "currentPosition": {
    "lat": 44.2,
    "lng": -49.5
  },
  "progress": 34.6,
  "status": "Underway",
  "speedKnots": 16.5,
  "eta": "2026-05-14T08:00:00+00:00",
  "incident": null,
  "updatedAt": "2026-05-08T20:00:00+00:00",
  "distanceRemainingNm": 2142.8,
  "fuelRemainingPct": 68.0,
  "risk": {
    "level": "Medium",
    "score": 36
  }
}
```

See `API_CONTRACT.md` or `/openapi.json` for the complete response schema.

## Backend Shape

The backend is split into small modules:

```text
backend/
  main.py          REST and WebSocket endpoints
  models.py        typed API response models
  simulator.py     dynamic voyage and incident stream logic
  seed_data.py     three voyages and incident templates
  recommender.py   backend-generated response suggestions
```

The recommendation engine is intentionally local and deterministic for the MVP. It reads active incidents and generates suggested response checklists. A real AI service can later replace `recommender.py` without changing the dashboard contract.

## API

```text
GET /api/v1/voyages
```

Returns the latest state of all three voyages. Legacy alias: `GET /voyages`.

```text
WS /api/v1/ws/voyages
```

Streams updated voyage data every 3 seconds. Legacy alias: `WS /ws/voyages`.

```text
GET /api/v1/incidents
WS /api/v1/ws/incidents
```

Returns or streams active incidents.

```text
GET /api/v1/recommendations
WS /api/v1/ws/recommendations
```

Returns or streams response suggestions for active incidents.

```text
POST /api/v1/simulation/reset
```

Resets the deterministic simulation and returns simulation metadata plus current snapshots.

For the AI agent hand-off contract, see `API_CONTRACT.md`. The formal machine-readable schema is available at `http://localhost:8000/openapi.json`.

## Run Locally

Backend:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The map uses OpenStreetMap tiles, so the browser needs internet access to show the background map.
