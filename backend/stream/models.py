from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["Low", "Medium", "High", "Critical"]
IncidentType = Literal[
    "Engine Failure",
    "Fire",
    "Fuel Leak",
    "Weather Delay",
    "Port Congestion",
    "Navigation Warning",
]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(ApiModel):
    lat: float = Field(description="Latitude in decimal degrees.")
    lng: float = Field(description="Longitude in decimal degrees.")


class Port(Position):
    name: str
    country: str
    unLocode: str


class Ship(ApiModel):
    id: str
    name: str
    type: str
    imo: str
    flag: str
    operator: str


class Cargo(ApiModel):
    type: str
    weightTons: int
    hazardClass: str


class WeatherContext(ApiModel):
    condition: str
    waveHeightM: float
    windSpeedKnots: float
    visibilityNm: float
    riskLevel: Severity
    updatedAt: str


class DestinationPortStatus(ApiModel):
    berthName: str
    berthStatus: Literal["On Schedule", "Watch", "Delayed"]
    congestionLevel: Severity
    arrivalWindowStart: str
    arrivalWindowEnd: str


class RiskSignal(ApiModel):
    id: str
    level: Severity
    message: str
    source: str


class RiskAssessment(ApiModel):
    level: Severity
    score: int = Field(ge=0, le=100)
    signals: list[RiskSignal]


class IncidentSummary(ApiModel):
    id: str
    type: IncidentType
    severity: Severity


class Voyage(ApiModel):
    id: str
    ship: Ship
    origin: Port
    destination: Port
    route: list[tuple[float, float]]
    currentPosition: Position
    progress: float = Field(ge=0, le=100)
    status: Literal["Underway", "Arrived"]
    speedKnots: float
    eta: str
    incident: Optional[IncidentSummary]
    updatedAt: str
    cargo: Cargo
    weather: WeatherContext
    destinationPortStatus: DestinationPortStatus
    distanceCoveredNm: float
    distanceRemainingNm: float
    fuelRemainingPct: float = Field(ge=0, le=100)
    risk: RiskAssessment


class Incident(ApiModel):
    id: str
    voyageId: str
    shipId: str
    shipName: str
    type: IncidentType
    severity: Severity
    description: str
    status: Literal["Open"]
    startedAt: str
    updatedAt: str
    operationalImpact: str
    speedReductionPct: int = Field(ge=0, le=100)
    scenarioTick: int


class Recommendation(ApiModel):
    id: str
    incidentId: str
    voyageId: str
    shipName: str
    incidentType: IncidentType
    severity: Severity
    title: str
    priority: Severity
    summary: str
    checklist: list[str]
    context: str
    source: str
    confidence: float = Field(ge=0, le=1)
    relatedRiskSignals: list[str]
    generatedAt: str


class SimulationMetadata(ApiModel):
    scenarioId: str
    tick: int
    tickIntervalSeconds: int
    simulatedMinutesPerTick: int
    deterministic: bool
    generatedAt: str


class SimulationResetResponse(ApiModel):
    status: Literal["reset"]
    simulation: SimulationMetadata
    voyages: list[Voyage]
    incidents: list[Incident]
    recommendations: list[Recommendation]
