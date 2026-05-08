import asyncio
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from models import Incident, Recommendation, SimulationResetResponse, Voyage
from simulator import (
    TICK_INTERVAL_SECONDS,
    get_incident_snapshot,
    get_recommendation_snapshot,
    get_voyage_snapshot,
    reset_simulation as reset_simulator,
    update_voyages,
)


class StreamConnectionManager:
    def __init__(self, snapshot: Callable[[], list[dict]]) -> None:
        self.snapshot = snapshot
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        await websocket.send_json(self.snapshot())

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload: list[dict]) -> None:
        stale_connections: list[WebSocket] = []

        for websocket in self.active_connections:
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(websocket)


voyage_manager = StreamConnectionManager(get_voyage_snapshot)
incident_manager = StreamConnectionManager(get_incident_snapshot)
recommendation_manager = StreamConnectionManager(get_recommendation_snapshot)


async def simulator_loop() -> None:
    while True:
        snapshot = update_voyages()
        await broadcast_snapshot(snapshot)
        await asyncio.sleep(TICK_INTERVAL_SECONDS)


async def broadcast_snapshot(snapshot: dict) -> None:
    await voyage_manager.broadcast(snapshot["voyages"])
    await incident_manager.broadcast(snapshot["incidents"])
    await recommendation_manager.broadcast(snapshot["recommendations"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulator_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Ship Voyage Demo API",
    description=(
        "Synthetic dynamic voyage data for a ship manager dashboard and AI agent integration. "
        "The stable integration surface is /api/v1/*."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check() -> dict:
    return {
        "status": "ok",
        "message": "Ship Voyage Demo API is running",
        "apiVersion": "v1",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/api/v1/voyages", response_model=list[Voyage], tags=["Voyages"])
@app.get("/voyages", response_model=list[Voyage], include_in_schema=False)
def get_voyages() -> list[dict]:
    return get_voyage_snapshot()


@app.get("/api/v1/incidents", response_model=list[Incident], tags=["Incidents"])
@app.get("/incidents", response_model=list[Incident], include_in_schema=False)
def get_incidents() -> list[dict]:
    return get_incident_snapshot()


@app.get("/api/v1/recommendations", response_model=list[Recommendation], tags=["Recommendations"])
@app.get("/recommendations", response_model=list[Recommendation], include_in_schema=False)
def get_recommendations() -> list[dict]:
    return get_recommendation_snapshot()


@app.post("/api/v1/simulation/reset", response_model=SimulationResetResponse, tags=["Simulation"])
async def reset_simulation() -> dict:
    snapshot = reset_simulator()
    await broadcast_snapshot(snapshot)
    return {"status": "reset", **snapshot}


@app.websocket("/api/v1/ws/voyages")
@app.websocket("/ws/voyages")
async def websocket_voyages(websocket: WebSocket) -> None:
    await connect_stream(websocket, voyage_manager)


@app.websocket("/api/v1/ws/incidents")
@app.websocket("/ws/incidents")
async def websocket_incidents(websocket: WebSocket) -> None:
    await connect_stream(websocket, incident_manager)


@app.websocket("/api/v1/ws/recommendations")
@app.websocket("/ws/recommendations")
async def websocket_recommendations(websocket: WebSocket) -> None:
    await connect_stream(websocket, recommendation_manager)


async def connect_stream(websocket: WebSocket, manager: StreamConnectionManager) -> None:
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
