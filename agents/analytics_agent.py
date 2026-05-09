from __future__ import annotations

import re
from typing import Optional

import httpx


__all__ = ["AnalyticsAgent"]


class AnalyticsAgent:
    """Layer 2 specialist — fleet operations queries via Dave's stream API."""

    def __init__(self, stream_url: str = "http://localhost:8000", timeout: float = 5.0):
        self.stream_url = stream_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def close(self):
        self.client.close()

    # ── Tool 1: list voyages ─────────────────────────────────────────────
    def list_voyages(self) -> list[dict]:
        """Return a compact summary of every voyage in the fleet."""
        r = self.client.get(f"{self.stream_url}/api/v1/voyages")
        r.raise_for_status()
        voyages = r.json()
        return [
            {
                "id": v["id"],
                "ship": v["ship"]["name"],
                "type": v["ship"]["type"],
                "from": v["origin"]["name"],
                "to": v["destination"]["name"],
                "progress_pct": v["progress"],
                "speed_kn": v["speedKnots"],
                "fuel_pct": v["fuelRemainingPct"],
                "status": v["status"],
                "risk_level": v["risk"]["level"],
                "has_incident": v["incident"] is not None,
            }
            for v in voyages
        ]

    # ── Tool 2: get full status for one voyage ───────────────────────────
    def get_voyage_status(self, voyage_id: str) -> Optional[dict]:
        """Return the full status object for one voyage."""
        r = self.client.get(f"{self.stream_url}/api/v1/voyages")
        r.raise_for_status()
        for v in r.json():
            if v["id"] == voyage_id:
                return v
        return None

    # ── Tool 3: get active incidents ─────────────────────────────────────
    def get_active_incidents(self, severity: Optional[str] = None) -> list[dict]:
        """Return incidents currently open. Optionally filter by severity."""
        r = self.client.get(f"{self.stream_url}/api/v1/incidents")
        r.raise_for_status()
        incidents = r.json()
        if severity:
            valid = {"Low", "Medium", "High", "Critical"}
            if severity not in valid:
                raise ValueError(f"severity must be one of {valid}, got {severity!r}")
            incidents = [i for i in incidents if i["severity"] == severity]
        return incidents

    # ── Tool 4: fleet-wide risk summary ──────────────────────────────────
    def get_fleet_risk(self) -> dict:
        """Aggregate risk view across all voyages."""
        r = self.client.get(f"{self.stream_url}/api/v1/voyages")
        r.raise_for_status()
        voyages = r.json()

        levels = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
        signals = []
        for v in voyages:
            levels[v["risk"]["level"]] += 1
            for sig in v["risk"]["signals"]:
                signals.append({
                    "voyage_id": v["id"],
                    "ship": v["ship"]["name"],
                    "level": sig["level"],
                    "message": sig["message"],
                    "source": sig["source"],
                })

        # Highest risk in fleet
        order = ["Critical", "High", "Medium", "Low"]
        highest = next((lvl for lvl in order if levels[lvl] > 0), "Low")

        return {
            "fleet_size": len(voyages),
            "risk_distribution": levels,
            "highest_risk_level": highest,
            "all_signals": signals,
        }

    # ── Tool 5: recommendations ──────────────────────────────────────────
    def get_recommendations(self) -> list[dict]:
        """Current AI recommendations from Dave's recommender."""
        r = self.client.get(f"{self.stream_url}/api/v1/recommendations")
        r.raise_for_status()
        return r.json()

    # ── Top-level query interface (used by Supervisor) ───────────────────
    def query(self, question: str) -> str:
        """
        Answer an operational question about the fleet.

        Uses simple keyword routing to pick the right tool. A real LLM
        tool-dispatch step replaces this once the LLM is wired in — same
        pattern as Layer 2 in x1025_IMPACT.
        """
        q = question.lower()

        # Specific voyage lookup
        m = re.search(r"voyage[_\s]*(\d{3})", q)
        if m:
            vid = f"voyage_{m.group(1)}"
            v = self.get_voyage_status(vid)
            if v is None:
                return f"No voyage found with id {vid}."
            return self._format_voyage(v)

        # Incident-related
        if any(w in q for w in ["incident", "emergency", "alert", "fire", "leak", "failure"]):
            incidents = self.get_active_incidents()
            if not incidents:
                return "No active incidents across the fleet."
            return self._format_incidents(incidents)

        # Risk-related
        if "risk" in q:
            risk = self.get_fleet_risk()
            return self._format_risk(risk)

        # Recommendation lookup
        if "recommend" in q or "suggest" in q or "what should" in q:
            recs = self.get_recommendations()
            if not recs:
                return "No active recommendations at this time."
            return self._format_recommendations(recs)

        # Default — fleet overview
        voyages = self.list_voyages()
        return self._format_fleet_overview(voyages)

    # ── Formatters (turn structured data into readable text) ─────────────
    @staticmethod
    def _format_voyage(v: dict) -> str:
        eta_iso = v.get("eta", "unknown")
        incident_str = ""
        if v.get("incident"):
            incident_str = f"\nActive incident: {v['incident']['type']} ({v['incident']['severity']})"
        return (
            f"{v['ship']['name']} ({v['id']})\n"
            f"  Route: {v['origin']['name']} → {v['destination']['name']}\n"
            f"  Progress: {v['progress']}% | Speed: {v['speedKnots']} kn | Fuel: {v['fuelRemainingPct']}%\n"
            f"  ETA: {eta_iso}\n"
            f"  Risk: {v['risk']['level']} (score {v['risk']['score']})"
            f"{incident_str}"
        )

    @staticmethod
    def _format_incidents(incidents: list[dict]) -> str:
        lines = [f"{len(incidents)} active incident(s):"]
        for i in incidents:
            lines.append(
                f"  • {i['shipName']}: {i['type']} ({i['severity']}) — {i['operationalImpact']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_risk(risk: dict) -> str:
        dist = risk["risk_distribution"]
        return (
            f"Fleet of {risk['fleet_size']} voyages.\n"
            f"Highest risk: {risk['highest_risk_level']}\n"
            f"Distribution: Low {dist['Low']}, Medium {dist['Medium']}, "
            f"High {dist['High']}, Critical {dist['Critical']}"
        )

    @staticmethod
    def _format_recommendations(recs: list[dict]) -> str:
        lines = [f"{len(recs)} active recommendation(s):"]
        for r in recs:
            summary = r.get("summary", "")
            lines.append(f"  • {summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_fleet_overview(voyages: list[dict]) -> str:
        lines = [f"Fleet overview ({len(voyages)} voyages):"]
        for v in voyages:
            warn = " ⚠" if v["has_incident"] or v["risk_level"] in {"High", "Critical"} else ""
            lines.append(
                f"  • {v['ship']} ({v['id']}): {v['from']} → {v['to']} | "
                f"{v['progress_pct']}% | {v['speed_kn']}kn | "
                f"fuel {v['fuel_pct']}% | risk {v['risk_level']}{warn}"
            )
        return "\n".join(lines)


# ── CLI for testing without LLM ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    agent = AnalyticsAgent()
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(agent.query(question))
    else:
        print("=" * 60)
        print("AnalyticsAgent quick test (no LLM)")
        print("=" * 60)
        print("\n--- list_voyages ---")
        for v in agent.list_voyages():
            print(f"  {v}")
        print("\n--- get_active_incidents ---")
        for i in agent.get_active_incidents():
            print(f"  {i['shipName']}: {i['type']} ({i['severity']})")
        print("\n--- get_fleet_risk ---")
        print(agent.get_fleet_risk())
        print("\n--- query: 'What's the status of voyage_001?' ---")
        print(agent.query("What's the status of voyage_001?"))
    agent.close()
