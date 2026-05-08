from datetime import datetime, timezone


RUNBOOKS = {
    "Engine Failure": {
        "title": "Stabilize propulsion and notify operations",
        "priority": "High",
        "summary": "Treat this as a propulsion reliability event. Reduce operational risk first, then update ETA and escalation paths.",
        "checklist": [
            "Confirm engine room status and safe operating speed.",
            "Notify fleet operations and destination port of possible ETA change.",
            "Request engineering assessment and next update interval.",
            "Prepare nearest suitable port options if speed continues to fall.",
        ],
    },
    "Fire": {
        "title": "Activate emergency response protocol",
        "priority": "Critical",
        "summary": "Prioritize crew safety and containment. Keep the vessel at minimum safe speed until the fire response status is confirmed.",
        "checklist": [
            "Confirm muster status and location of fire alarm.",
            "Verify containment, suppression system status, and smoke boundaries.",
            "Escalate to emergency operations lead immediately.",
            "Prepare external assistance request if containment is not confirmed.",
        ],
    },
    "Fuel Leak": {
        "title": "Reduce fuel-system risk and monitor reserves",
        "priority": "Medium",
        "summary": "Proceed under caution while the crew verifies the leak source, remaining fuel, and environmental risk.",
        "checklist": [
            "Confirm fuel pressure readings and isolated tanks or lines.",
            "Calculate remaining range at reduced speed.",
            "Notify operations and environmental response contact.",
            "Update voyage plan if reserve margin drops below threshold.",
        ],
    },
    "Weather Delay": {
        "title": "Recalculate ETA and monitor weather window",
        "priority": "Low",
        "summary": "The vessel can remain underway, but operations should track speed loss and communicate the ETA impact.",
        "checklist": [
            "Confirm latest weather forecast for the active route segment.",
            "Reduce speed only as needed for safe passage.",
            "Update ETA and notify destination operations.",
            "Review alternate waypoint options if delay continues.",
        ],
    },
    "Port Congestion": {
        "title": "Coordinate berth window and speed plan",
        "priority": "Medium",
        "summary": "Destination congestion may make current arrival timing inefficient. Align berth availability, ETA, and operating speed.",
        "checklist": [
            "Confirm latest berth availability with destination port operations.",
            "Review whether speed adjustment can reduce anchorage time.",
            "Notify commercial operations of possible schedule impact.",
            "Recalculate ETA after the next port status update.",
        ],
    },
    "Navigation Warning": {
        "title": "Review route segment and increase bridge watch",
        "priority": "High",
        "summary": "Treat the warning as a route-safety event. Confirm waypoints, traffic context, and bridge team readiness.",
        "checklist": [
            "Confirm the affected route segment and nearest waypoint.",
            "Increase bridge watch cadence until the warning clears.",
            "Check traffic separation, notices to mariners, and local guidance.",
            "Escalate to operations if route deviation becomes likely.",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_recommendation(incident: dict, voyage: dict) -> dict:
    runbook = RUNBOOKS[incident["type"]]
    risk = voyage.get("risk", {})
    risk_signals = risk.get("signals", [])
    related_risk_signals = [signal["id"] for signal in risk_signals if signal["source"] in {"incident", "weather", "port"}]

    return {
        "id": f"rec_{incident['id']}",
        "incidentId": incident["id"],
        "voyageId": incident["voyageId"],
        "shipName": incident["shipName"],
        "incidentType": incident["type"],
        "severity": incident["severity"],
        "title": runbook["title"],
        "priority": runbook["priority"],
        "summary": runbook["summary"],
        "checklist": runbook["checklist"],
        "context": (
            f"{voyage['ship']['name']} is {voyage['progress']}% complete from "
            f"{voyage['origin']['name']} to {voyage['destination']['name']}, "
            f"moving at {voyage['speedKnots']} kn with {voyage['distanceRemainingNm']} nm remaining. "
            f"Current risk level is {risk.get('level', 'Low')}."
        ),
        "source": "AI Response Assistant",
        "confidence": 0.86,
        "relatedRiskSignals": related_risk_signals,
        "generatedAt": utc_now(),
    }
