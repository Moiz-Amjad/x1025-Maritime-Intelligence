# Voyage Synthetic Data API v1

This API provides synthetic dynamic voyage data for two consumers:

- The ship manager dashboard UI
- An AI agent that analyzes the same operational data

The stable integration surface is `/api/v1/*`. Legacy top-level paths still work for the existing demo, but new integrations should use the v1 paths.

## Contract Sources

- Interactive docs: `http://localhost:8000/docs`
- Machine-readable OpenAPI: `http://localhost:8000/openapi.json`
- Base URL for local development: `http://localhost:8000`

The OpenAPI document is generated from typed FastAPI/Pydantic response models.

## REST Endpoints

```bash
curl http://localhost:8000/api/v1/voyages
curl http://localhost:8000/api/v1/incidents
curl http://localhost:8000/api/v1/recommendations
curl -X POST http://localhost:8000/api/v1/simulation/reset
```

Legacy aliases:

```text
GET /voyages
GET /incidents
GET /recommendations
WS  /ws/voyages
WS  /ws/incidents
WS  /ws/recommendations
```

## WebSocket Streams

```text
ws://localhost:8000/api/v1/ws/voyages
ws://localhost:8000/api/v1/ws/incidents
ws://localhost:8000/api/v1/ws/recommendations
```

Each stream sends the current snapshot on connect, then sends a full replacement snapshot every simulation tick. The default tick interval is 3 seconds, and each tick advances simulated voyage time by 36 minutes.

## Voyage Shape

`GET /api/v1/voyages` returns a list of voyage objects. Important fields:

- `id`, `ship`, `origin`, `destination`
- `route`, `currentPosition`, `progress`, `status`, `speedKnots`, `eta`
- `incident`: nullable summary of the active incident for that voyage
- `cargo`, `weather`, `destinationPortStatus`
- `distanceCoveredNm`, `distanceRemainingNm`, `fuelRemainingPct`
- `risk`: simple risk score, level, and source signals

Example excerpt:

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
  "progress": 32.0,
  "status": "Underway",
  "speedKnots": 16.5,
  "incident": null,
  "distanceRemainingNm": 2166.7,
  "fuelRemainingPct": 68.0,
  "risk": {
    "level": "Medium",
    "score": 36,
    "signals": [
      {
        "id": "voyage_001_weather",
        "level": "Medium",
        "message": "Moderate Atlantic swell with 3.2 m waves.",
        "source": "weather"
      }
    ]
  }
}
```

## Incident Shape

`GET /api/v1/incidents` returns active incidents only. Incidents are separate from voyage lifecycle status.

Important fields:

- `voyageId`, `shipId`, `shipName`
- `type`, `severity`, `description`, `operationalImpact`
- `speedReductionPct`
- `scenarioTick`: deterministic tick when the incident opened

## Recommendation Shape

`GET /api/v1/recommendations` returns deterministic runbook-style recommendations for active incidents.

Important fields:

- `incidentId`, `voyageId`, `shipName`
- `incidentType`, `severity`, `priority`
- `title`, `summary`, `checklist`, `context`
- `confidence`
- `relatedRiskSignals`

The recommendation engine is local and deterministic. A real AI service can later replace `backend/recommender.py` without changing the v1 response contract.

## Deterministic Scenario

The simulator uses scenario `ops-core-voyages-v1`.

Baseline state:

- Three active voyages
- One initial weather delay on `voyage_003`
- Operational context on every voyage: cargo, weather, destination port status, fuel, distance, and risk

Scheduled events:

```text
tick 2   open Engine Failure on voyage_001
tick 4   resolve initial Weather Delay on voyage_003
tick 6   open Fuel Leak on voyage_002
tick 9   resolve Engine Failure on voyage_001
tick 11  open Navigation Warning on voyage_003
tick 14  resolve Fuel Leak on voyage_002
```

Use reset before repeatable demos or tests:

```bash
curl -X POST http://localhost:8000/api/v1/simulation/reset
```

The reset response includes simulation metadata plus current voyages, incidents, and recommendations.

## Integration Notes for the AI Agent Team

- Poll REST endpoints for simple integration, or subscribe to WebSockets for live analysis.
- Treat each WebSocket message as a full replacement snapshot, not a partial patch.
- Join data by `voyage.id`, `incident.voyageId`, and `recommendation.incidentId`.
- Prefer `/openapi.json` for generated clients or schema validation.
- The API is intentionally unauthenticated and in-memory for the MVP.
