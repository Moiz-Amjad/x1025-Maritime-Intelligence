"""Layer 3 agent. Watches the incident stream and writes an action plan
for each new incident, pulling live voyage state from analytics_agent
and (when wired) ISM procedures from safety_agent."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

import httpx

from agents.analytics_agent import AnalyticsAgent

if TYPE_CHECKING:
    from agents.safety_agent import SafetyAgent


__all__ = ["Superintendent", "ActionPlan"]


# ── Severity → Priority mapping ──────────────────────────────────────────────
SEVERITY_TO_PRIORITY = {
    "Critical": "P1 — Immediate",
    "High":     "P2 — Urgent",
    "Medium":   "P3 — Watch",
    "Low":      "P4 — Monitor",
}

# Map incident types to safety procedure questions.
# When SafetyAgent is connected, the superintendent uses these to retrieve
# the right ISM procedure for each incident type.
INCIDENT_TO_PROCEDURE_QUERY = {
    "Engine Failure":     "Engine failure response procedure and emergency checklist",
    "Fire":               "Fire emergency procedure including CO2 release",
    "Fuel Leak":          "Fuel leak containment procedure and pollution prevention",
    "Weather Delay":      "Heavy weather routing procedure and bridge watch protocol",
    "Port Congestion":    "Port arrival coordination procedure",
    "Navigation Warning": "Navigation warning response and bridge watch handover",
}


# ── ActionPlan: the output of the superintendent ─────────────────────────────
@dataclass
class ActionPlan:
    """A coordinated response to one incident, ready for the dashboard."""
    incident_id: str
    voyage_id: str
    ship_name: str
    incident_type: str
    severity: str
    priority: str
    title: str
    summary: str
    recommended_actions: list[str]
    operational_context: str
    safety_procedure_excerpt: Optional[str]
    source_recommendation_id: Optional[str]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


# ── The Superintendent itself ────────────────────────────────────────────────
class Superintendent:
    """Watches the fleet and produces action plans for new incidents."""

    def __init__(
        self,
        stream_url: str = "http://localhost:8000",
        analytics_agent: Optional[AnalyticsAgent] = None,
        safety_agent: Optional["SafetyAgent"] = None,
        poll_interval_seconds: float = 3.0,
    ):
        self.stream_url = stream_url.rstrip("/")
        self.analytics_agent = analytics_agent or AnalyticsAgent(stream_url=stream_url)
        self.safety_agent = safety_agent
        self.poll_interval = poll_interval_seconds
        self.client = httpx.Client(timeout=5.0)

        # Track which incidents we've already produced plans for
        self._handled_incident_ids: set[str] = set()
        # Store the plans we've generated for the dashboard
        self.action_plans: list[ActionPlan] = []

    def close(self):
        self.client.close()
        self.analytics_agent.close()

    # ── Single-pass incident check ───────────────────────────────────────────
    def check_incidents(self) -> list[ActionPlan]:
        """Poll once, generate action plans for any new incidents, return them."""
        try:
            r = self.client.get(f"{self.stream_url}/api/v1/incidents")
            r.raise_for_status()
            incidents = r.json()
        except httpx.HTTPError as e:
            print(f"[superintendent] failed to fetch incidents: {e}")
            return []

        new_plans = []
        for incident in incidents:
            iid = incident["id"]
            if iid in self._handled_incident_ids:
                continue

            plan = self._generate_action_plan(incident)
            if plan:
                self.action_plans.append(plan)
                self._handled_incident_ids.add(iid)
                new_plans.append(plan)

        return new_plans

    # ── Generate a plan for one incident ─────────────────────────────────────
    def _generate_action_plan(self, incident: dict) -> Optional[ActionPlan]:
        """Combine recommendation + voyage context + procedure into one plan."""
        voyage_id = incident["voyageId"]
        ship_name = incident["shipName"]
        itype = incident["type"]
        severity = incident["severity"]

        # 1. Get Dave's recommendation (if one exists)
        recommendation = self._fetch_recommendation_for(incident["id"])

        # 2. Get operational context from Layer 2
        voyage = self.analytics_agent.get_voyage_status(voyage_id)
        if voyage is None:
            print(f"[superintendent] voyage {voyage_id} not found, skipping")
            return None

        operational_context = (
            f"{ship_name} ({voyage_id}): {voyage['origin']['name']} → "
            f"{voyage['destination']['name']}, "
            f"{voyage['progress']}% complete, speed {voyage['speedKnots']} kn, "
            f"fuel {voyage['fuelRemainingPct']}%, "
            f"risk {voyage['risk']['level']} (score {voyage['risk']['score']})."
        )

        # 3. Get ISM procedure from SafetyAgent (only if connected)
        procedure_excerpt = None
        if self.safety_agent is not None:
            query = INCIDENT_TO_PROCEDURE_QUERY.get(itype)
            if query:
                try:
                    procedure_excerpt = self.safety_agent.query(query)[:800]
                except Exception as e:
                    procedure_excerpt = f"[SafetyAgent error: {e}]"

        # 4. Build action items, preferring Dave's runbook when available
        if recommendation:
            actions = recommendation.get("checklist", [])
            title = recommendation.get("title", f"{itype} response — {ship_name}")
            summary = recommendation.get("summary", incident["operationalImpact"])
            source_rec_id = recommendation.get("incidentId")
        else:
            actions = self._fallback_actions(incident, voyage)
            title = f"{itype} response — {ship_name}"
            summary = incident["operationalImpact"]
            source_rec_id = None

        return ActionPlan(
            incident_id=incident["id"],
            voyage_id=voyage_id,
            ship_name=ship_name,
            incident_type=itype,
            severity=severity,
            priority=SEVERITY_TO_PRIORITY.get(severity, "Unknown"),
            title=title,
            summary=summary,
            recommended_actions=actions,
            operational_context=operational_context,
            safety_procedure_excerpt=procedure_excerpt,
            source_recommendation_id=source_rec_id,
        )

    def _fetch_recommendation_for(self, incident_id: str) -> Optional[dict]:
        try:
            r = self.client.get(f"{self.stream_url}/api/v1/recommendations")
            r.raise_for_status()
            for rec in r.json():
                if rec.get("incidentId") == incident_id:
                    return rec
        except httpx.HTTPError:
            pass
        return None

    @staticmethod
    def _fallback_actions(incident: dict, voyage: dict) -> list[str]:
        """If Dave's recommender hasn't fired yet, generate basic actions."""
        return [
            f"Verify {incident['type']} report on {incident['shipName']}.",
            f"Reduce speed by ~{incident.get('speedReductionPct', 0)}% per impact assessment.",
            "Notify shore-side superintendent and DPA.",
            "Activate ISM procedure relevant to incident type.",
            "Document timeline in the official log book.",
        ]

    # ── Continuous polling loop (for demo) ───────────────────────────────────
    def run_forever(self, max_iterations: Optional[int] = None):
        """Poll continuously and print action plans as they're generated."""
        i = 0
        try:
            while True:
                i += 1
                new_plans = self.check_incidents()
                for plan in new_plans:
                    self._print_plan(plan)

                if max_iterations is not None and i >= max_iterations:
                    break

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\n[superintendent] stopped by user")

    @staticmethod
    def _print_plan(plan: ActionPlan):
        print()
        print("=" * 70)
        print(f"  ACTION PLAN — {plan.priority}")
        print("=" * 70)
        print(f"  {plan.title}")
        print(f"  Incident: {plan.incident_type}  Severity: {plan.severity}")
        print(f"  Vessel:   {plan.ship_name}  ({plan.voyage_id})")
        print(f"  Generated: {plan.generated_at}")
        print()
        print(f"  Summary:")
        print(f"    {plan.summary}")
        print()
        print(f"  Operational context:")
        print(f"    {plan.operational_context}")
        if plan.safety_procedure_excerpt:
            print()
            print(f"  ISM procedure (Layer 1):")
            print(f"    {plan.safety_procedure_excerpt[:300]}...")
        print()
        print(f"  Recommended actions:")
        for i, action in enumerate(plan.recommended_actions, 1):
            print(f"    {i}. {action}")
        print("=" * 70)


# ── CLI for testing ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Superintendent against a running stream API"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run one polling cycle and exit (default: poll forever)"
    )
    parser.add_argument(
        "--iterations", type=int, default=None,
        help="Run N polling cycles and exit"
    )
    parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Polling interval in seconds (default: 3.0)"
    )
    parser.add_argument(
        "--stream-url", default="http://localhost:8000",
        help="Stream API base URL (default: http://localhost:8000)"
    )
    args = parser.parse_args()

    super_agent = Superintendent(
        stream_url=args.stream_url,
        poll_interval_seconds=args.interval,
    )

    print("=" * 70)
    print("  x1025 Superintendent — Layer 3 Autonomous Workflow Agent")
    print("=" * 70)
    print(f"  Stream URL:    {args.stream_url}")
    print(f"  Poll interval: {args.interval}s")
    print("=" * 70)

    try:
        if args.once:
            plans = super_agent.check_incidents()
            print(f"\nFound {len(plans)} new incident(s).")
            for plan in plans:
                Superintendent._print_plan(plan)
        else:
            super_agent.run_forever(max_iterations=args.iterations)
    finally:
        super_agent.close()