import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Optional

from recommender import build_recommendation
from seed_data import INCIDENT_TEMPLATES, SCENARIO_EVENTS, SCENARIO_ID, VOYAGE_SEEDS


SIMULATED_MINUTES_PER_TICK = 36
TICK_INTERVAL_SECONDS = 3

SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
RISK_SCORE_WEIGHTS = {"Low": 8, "Medium": 18, "High": 32, "Critical": 45}

voyages: list[dict] = []
incidents: dict[str, dict] = {}
recommendations: dict[str, dict] = {}
incident_counter = 0
simulation_tick = 0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def haversine_nm(start: list[float], end: list[float]) -> float:
    earth_radius_nm = 3440.065
    start_lat, start_lng = math.radians(start[0]), math.radians(start[1])
    end_lat, end_lng = math.radians(end[0]), math.radians(end[1])
    delta_lat = end_lat - start_lat
    delta_lng = end_lng - start_lng

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(start_lat) * math.cos(end_lat) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * earth_radius_nm * math.asin(math.sqrt(a))


def route_distance_nm(route: list[list[float]]) -> float:
    return sum(haversine_nm(route[index], route[index + 1]) for index in range(len(route) - 1))


def position_on_route(route: list[list[float]], progress: float) -> dict:
    progress = max(0, min(progress, 1))
    total_distance = route_distance_nm(route)
    target_distance = total_distance * progress
    covered_distance = 0.0

    for index in range(len(route) - 1):
        start = route[index]
        end = route[index + 1]
        segment_distance = haversine_nm(start, end)

        if covered_distance + segment_distance >= target_distance:
            segment_progress = (target_distance - covered_distance) / segment_distance
            lat = start[0] + (end[0] - start[0]) * segment_progress
            lng_delta = end[1] - start[1]
            if lng_delta > 180:
                lng_delta -= 360
            elif lng_delta < -180:
                lng_delta += 360

            lng = start[1] + lng_delta * segment_progress
            if lng > 180:
                lng -= 360
            elif lng < -180:
                lng += 360

            return {"lat": round(lat, 4), "lng": round(lng, 4)}

        covered_distance += segment_distance

    final_lat, final_lng = route[-1]
    return {"lat": final_lat, "lng": final_lng}


def format_eta(progress: float, total_distance_nm: float, speed_knots: float) -> str:
    if progress >= 1 or speed_knots <= 0:
        return iso_now()

    remaining_nm = total_distance_nm * (1 - progress)
    hours_remaining = remaining_nm / speed_knots
    return (utc_now() + timedelta(hours=hours_remaining)).isoformat()


def public_copy(item: dict) -> dict:
    return deepcopy({key: value for key, value in item.items() if not key.startswith("_")})


def public_incident_summary(incident: dict) -> dict:
    return {
        "id": incident["id"],
        "type": incident["type"],
        "severity": incident["severity"],
    }


def find_voyage(voyage_id: str) -> Optional[dict]:
    return next((voyage for voyage in voyages if voyage["id"] == voyage_id), None)


def find_incident_template(incident_type: str) -> dict:
    return next(template for template in INCIDENT_TEMPLATES if template["type"] == incident_type)


def highest_severity(levels: list[str]) -> str:
    if not levels:
        return "Low"

    return max(levels, key=lambda level: SEVERITY_RANK[level])


def build_destination_port_status(seed: dict) -> dict:
    now = utc_now()
    port = seed["destinationPort"]
    start_hours, end_hours = port["arrivalWindowHours"]

    return {
        "berthName": port["berthName"],
        "berthStatus": port["berthStatus"],
        "congestionLevel": port["congestionLevel"],
        "arrivalWindowStart": (now + timedelta(hours=start_hours)).isoformat(),
        "arrivalWindowEnd": (now + timedelta(hours=end_hours)).isoformat(),
    }


def build_risk_assessment(voyage: dict, incident: Optional[dict]) -> dict:
    signals = []
    weather = voyage["weather"]
    port_status = voyage["destinationPortStatus"]

    if SEVERITY_RANK[weather["riskLevel"]] >= SEVERITY_RANK["Medium"]:
        signals.append(
            {
                "id": f"{voyage['id']}_weather",
                "level": weather["riskLevel"],
                "message": f"{weather['condition']} with {weather['waveHeightM']} m waves.",
                "source": "weather",
            }
        )

    if SEVERITY_RANK[port_status["congestionLevel"]] >= SEVERITY_RANK["Medium"]:
        signals.append(
            {
                "id": f"{voyage['id']}_port",
                "level": port_status["congestionLevel"],
                "message": f"{port_status['berthName']} congestion level is {port_status['congestionLevel']}.",
                "source": "port",
            }
        )

    if incident:
        signals.append(
            {
                "id": incident["id"],
                "level": incident["severity"],
                "message": incident["operationalImpact"],
                "source": "incident",
            }
        )

    if voyage["fuelRemainingPct"] < 40:
        fuel_level = "High" if voyage["fuelRemainingPct"] < 25 else "Medium"
        signals.append(
            {
                "id": f"{voyage['id']}_fuel",
                "level": fuel_level,
                "message": f"Fuel remaining is {voyage['fuelRemainingPct']}%.",
                "source": "fuel",
            }
        )

    if not signals:
        signals.append(
            {
                "id": f"{voyage['id']}_normal",
                "level": "Low",
                "message": "No active operational risk signals.",
                "source": "simulator",
            }
        )

    level = highest_severity([signal["level"] for signal in signals])
    score = min(100, sum(RISK_SCORE_WEIGHTS[signal["level"]] for signal in signals))

    return {"level": level, "score": score, "signals": signals}


def refresh_operational_fields(voyage: dict, incident: Optional[dict] = None) -> None:
    now = iso_now()
    total_distance_nm = voyage["_totalDistanceNm"]
    progress_ratio = voyage["_progressRatio"]

    voyage["currentPosition"] = position_on_route(voyage["route"], progress_ratio)
    voyage["progress"] = round(progress_ratio * 100, 1)
    voyage["eta"] = format_eta(progress_ratio, total_distance_nm, voyage["speedKnots"])
    voyage["updatedAt"] = now
    voyage["weather"]["updatedAt"] = now
    voyage["distanceCoveredNm"] = round(total_distance_nm * progress_ratio, 1)
    voyage["distanceRemainingNm"] = round(max(0, total_distance_nm - voyage["distanceCoveredNm"]), 1)
    voyage["risk"] = build_risk_assessment(voyage, incident)


def create_voyage(seed: dict) -> dict:
    total_distance_nm = route_distance_nm(seed["route"])
    now = iso_now()
    voyage = {
        "id": seed["id"],
        "ship": seed["ship"],
        "origin": seed["origin"],
        "destination": seed["destination"],
        "route": seed["route"],
        "currentPosition": position_on_route(seed["route"], seed["progress"]),
        "progress": round(seed["progress"] * 100, 1),
        "status": "Underway",
        "speedKnots": seed["speedKnots"],
        "eta": format_eta(seed["progress"], total_distance_nm, seed["speedKnots"]),
        "incident": None,
        "updatedAt": now,
        "cargo": seed["cargo"],
        "weather": {**seed["weather"], "updatedAt": now},
        "destinationPortStatus": build_destination_port_status(seed),
        "distanceCoveredNm": round(total_distance_nm * seed["progress"], 1),
        "distanceRemainingNm": round(total_distance_nm * (1 - seed["progress"]), 1),
        "fuelRemainingPct": seed["fuelRemainingPct"],
        "risk": {"level": "Low", "score": 0, "signals": []},
        "_progressRatio": seed["progress"],
        "_baseSpeedKnots": seed["speedKnots"],
        "_fuelBurnPctPerTick": max(0.08, seed["speedKnots"] / 120),
        "_totalDistanceNm": total_distance_nm,
        "_activeIncidentId": None,
    }
    refresh_operational_fields(voyage)
    return voyage


def open_incident(voyage: dict, template: dict) -> None:
    global incident_counter

    if voyage["_activeIncidentId"] is not None or voyage["status"] == "Arrived":
        return

    incident_counter += 1
    now = iso_now()
    incident = {
        "id": f"incident_{incident_counter:03d}",
        "voyageId": voyage["id"],
        "shipId": voyage["ship"]["id"],
        "shipName": voyage["ship"]["name"],
        "type": template["type"],
        "severity": template["severity"],
        "description": template["description"],
        "status": "Open",
        "startedAt": now,
        "updatedAt": now,
        "operationalImpact": template["operationalImpact"],
        "speedReductionPct": template["speedReductionPct"],
        "scenarioTick": simulation_tick,
        "_speedMultiplier": template["speedMultiplier"],
    }

    incidents[incident["id"]] = incident
    voyage["_activeIncidentId"] = incident["id"]
    voyage["incident"] = public_incident_summary(incident)
    voyage["speedKnots"] = round(voyage["_baseSpeedKnots"] * incident["_speedMultiplier"], 1)
    refresh_operational_fields(voyage, incident)
    recommendations[incident["id"]] = build_recommendation(public_copy(incident), public_copy(voyage))


def resolve_incident(voyage: dict) -> None:
    incident_id = voyage["_activeIncidentId"]
    if incident_id is None:
        return

    incidents.pop(incident_id, None)
    recommendations.pop(incident_id, None)
    voyage["_activeIncidentId"] = None
    voyage["incident"] = None
    voyage["speedKnots"] = voyage["_baseSpeedKnots"]
    refresh_operational_fields(voyage)


def apply_scenario_events(current_tick: int) -> None:
    for event in SCENARIO_EVENTS:
        if event["tick"] != current_tick:
            continue

        voyage = find_voyage(event["voyageId"])
        if voyage is None:
            continue

        if event["action"] == "open":
            open_incident(voyage, find_incident_template(event["incidentType"]))
        elif event["action"] == "resolve":
            resolve_incident(voyage)


def get_voyage_snapshot() -> list[dict]:
    return [public_copy(voyage) for voyage in voyages]


def get_incident_snapshot() -> list[dict]:
    return [public_copy(incident) for incident in incidents.values()]


def get_recommendation_snapshot() -> list[dict]:
    return [deepcopy(recommendation) for recommendation in recommendations.values()]


def get_simulation_metadata() -> dict:
    return {
        "scenarioId": SCENARIO_ID,
        "tick": simulation_tick,
        "tickIntervalSeconds": TICK_INTERVAL_SECONDS,
        "simulatedMinutesPerTick": SIMULATED_MINUTES_PER_TICK,
        "deterministic": True,
        "generatedAt": iso_now(),
    }


def get_stream_snapshot() -> dict:
    return {
        "simulation": get_simulation_metadata(),
        "voyages": get_voyage_snapshot(),
        "incidents": get_incident_snapshot(),
        "recommendations": get_recommendation_snapshot(),
    }


def reset_simulation() -> dict:
    global incident_counter, incidents, recommendations, simulation_tick, voyages

    simulation_tick = 0
    incident_counter = 0
    incidents = {}
    recommendations = {}
    voyages = [create_voyage(seed) for seed in VOYAGE_SEEDS]

    for seed in VOYAGE_SEEDS:
        if "initialIncidentType" in seed:
            voyage = find_voyage(seed["id"])
            if voyage:
                open_incident(voyage, find_incident_template(seed["initialIncidentType"]))

    return get_stream_snapshot()


def update_voyages() -> dict:
    global simulation_tick

    simulation_tick += 1
    apply_scenario_events(simulation_tick)

    for voyage in voyages:
        incident = incidents.get(voyage["_activeIncidentId"])
        speed_multiplier = incident["_speedMultiplier"] if incident else 1
        voyage["speedKnots"] = round(voyage["_baseSpeedKnots"] * speed_multiplier, 1)

        distance_advanced_nm = voyage["speedKnots"] * (SIMULATED_MINUTES_PER_TICK / 60)
        voyage["_progressRatio"] = min(
            1,
            voyage["_progressRatio"] + distance_advanced_nm / voyage["_totalDistanceNm"],
        )
        voyage["fuelRemainingPct"] = round(
            max(0, voyage["fuelRemainingPct"] - voyage["_fuelBurnPctPerTick"] * speed_multiplier),
            1,
        )

        if voyage["_progressRatio"] >= 1:
            voyage["status"] = "Arrived"
            resolve_incident(voyage)
            incident = None
        else:
            voyage["status"] = "Underway"

        if incident:
            incident["updatedAt"] = iso_now()
            refresh_operational_fields(voyage, incident)
            recommendations[incident["id"]] = build_recommendation(public_copy(incident), public_copy(voyage))
        else:
            refresh_operational_fields(voyage)

    return get_stream_snapshot()


reset_simulation()
