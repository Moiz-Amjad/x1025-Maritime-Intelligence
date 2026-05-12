"""Routes a question to the right specialist agent. Picks between the
safety RAG and the analytics layer, or runs both when needed."""
from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

from agents.analytics_agent import AnalyticsAgent

if TYPE_CHECKING:
    from agents.safety_agent import SafetyAgent


_VALID = {"procedural", "operational", "both", "none"}

_OPS_HINTS = re.compile(
    r"\b(eta|rob|fuel|speed|consum|charter\s*part|cp\b|noon\s*report|"
    r"position|knots?|mt/day|certificate.*(expir|valid)|fleet|vessel\s+\w+|"
    r"voyage[_\s]*\d+|voyage|incident|risk|recommendation|status|"
    r"ship[_\s]*\w+|issue|alert|imo\s*\d+)\b",
    re.I,
)
_PROC_HINTS = re.compile(
    r"\b(procedure|protocol|how\s+do\s+i|how\s+to|sms|ism|emergency|"
    r"checklist|man\s*overboard|fire|safety|abandon|drill|co2)\b",
    re.I,
)


class Supervisor:
    """Routes questions to the right specialist agent."""

    def __init__(
        self,
        safety_agent: Optional["SafetyAgent"] = None,
        analytics_agent: Optional[AnalyticsAgent] = None,
    ):
        self.safety_agent = safety_agent
        self.analytics_agent = analytics_agent or AnalyticsAgent()

    def classify(self, question: str) -> str:
        """Classify question into one of: procedural, operational, both, none."""
        ops = bool(_OPS_HINTS.search(question))
        proc = bool(_PROC_HINTS.search(question))
        if ops and proc:
            return "both"
        if ops:
            return "operational"
        if proc:
            return "procedural"
        return "none"

    def route(self, question: str) -> dict:
        """Dispatch a question to the right specialist(s)."""
        label = self.classify(question)

        if label == "procedural":
            if self.safety_agent is None:
                return {
                    "route": "procedural",
                    "answer": "[SafetyAgent not connected — Moiz's RAG would answer this in production]",
                    "sources": [],
                }
            return {
                "route": "procedural",
                "answer": self.safety_agent.query(question),
                "sources": ["safety_agent"],
            }

        if label == "operational":
            return {
                "route": "operational",
                "answer": self.analytics_agent.query(question),
                "sources": ["analytics_agent"],
            }

        if label == "both":
            parts = []
            sources = []
            if self.safety_agent:
                parts.append(f"[Procedural — Layer 1]\n{self.safety_agent.query(question)}")
                sources.append("safety_agent")
            else:
                parts.append("[Procedural — SafetyAgent not connected]")
            parts.append(f"[Operational — Layer 2]\n{self.analytics_agent.query(question)}")
            sources.append("analytics_agent")
            return {"route": "both", "answer": "\n\n".join(parts), "sources": sources}

        return {
            "route": "none",
            "answer": (
                "I can help with maritime safety procedures and live vessel operations. "
                "Could you rephrase your question to be about one of those?"
            ),
            "sources": [],
        }


# ── CLI for testing ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    supervisor = Supervisor()

    test_questions = [
        "What's the procedure for releasing the fixed CO2 system?",
        "What's the status of voyage_001?",
        "Are there any active incidents in the fleet?",
        "What's the highest risk in the fleet right now?",
        "Is voyage_003 having issues and what should we do about it?",
        "What's the weather forecast?",
    ]

    print("=" * 60)
    print("Supervisor Routing Test")
    print("=" * 60)
    for q in test_questions:
        result = supervisor.route(q)
        print(f"\n[{result['route']:>11}] {q}")
        print(f"  → {result['answer'][:150]}{'...' if len(result['answer']) > 150 else ''}")