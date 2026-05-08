Hey team, we now have a clean synthetic voyage data API ready for the UI and AI agent integration.

The API is built with FastAPI and exposes a stable v1 contract under:

/api/v1/*
It uses typed Pydantic models, so the API automatically generates formal docs and schemas at:

http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
The API provides synthetic but realistic voyage data for ships in transit. Each voyage includes:

ship details
origin and destination ports
planned route
current position
progress
speed
ETA
cargo
weather context
destination port status
fuel remaining
distance remaining
risk score and risk signals
active incident, if any
The main endpoints are:

GET /api/v1/voyages
GET /api/v1/incidents
GET /api/v1/recommendations
POST /api/v1/simulation/reset
There are also WebSocket streams for live data:

WS /api/v1/ws/voyages
WS /api/v1/ws/incidents
WS /api/v1/ws/recommendations
The REST endpoints are best for simple polling or initial integration. The WebSockets are best if the agent needs live updates. Each WebSocket message is a full replacement snapshot, not a partial patch.

The simulation is deterministic, which means the same scenario can be replayed for testing and demos. Use:

POST /api/v1/simulation/reset
to reset the data back to the starting state.

For joining data:

voyage.id = incident.voyageId
incident.id = recommendation.incidentId
The recommendation endpoint returns deterministic runbook-style guidance for active incidents. It is not calling a real AI model yet, but it is shaped so a real AI system can consume the same contract or replace the backend recommendation logic later.

There is also a hand-off document in the repo:

API_CONTRACT.md
That file explains the endpoints, sample payloads, WebSocket behavior, deterministic scenario, and integration notes. The recommended implementation path is:

Start by calling GET /api/v1/voyages.
Add GET /api/v1/incidents and GET /api/v1/recommendations.
Join records using voyageId and incidentId.
Use /openapi.json if you want to generate a client or validate schemas.
Switch to WebSockets later if live analysis is needed.
Legacy endpoints like /voyages, /incidents, and /recommendations still work, but new integrations should use /api/v1/*.