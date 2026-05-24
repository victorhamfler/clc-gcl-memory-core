from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BRIDGE_TERMS = {
    "bridge",
    "cross-domain",
    "cross domain",
    "connect",
    "connection",
    "routing",
    "router",
    "selector refresh",
    "refresh policy",
    "policy",
    "synthesis",
}
GEOMETRY_TERMS = {
    "ogcf",
    "geometry",
    "geometric",
    "embedding",
    "embeddings",
    "cluster",
    "clusters",
    "overload",
    "loop",
    "loops",
    "defect",
    "interaction",
}
MAINTENANCE_TERMS = {
    "cleanup",
    "clean up",
    "dedup",
    "duplicate",
    "maintenance",
    "stale",
    "current",
    "correct",
    "correction",
    "conflict",
    "supersede",
    "superseded",
}
ORDINARY_FACT_TERMS = {
    "what is",
    "what was",
    "what does",
    "when is",
    "where does",
    "does victor",
    "prefer",
    "drink",
    "calendar",
    "scheduled",
    "robot",
    "routine",
    "codename",
    "weather checks",
}


@dataclass(frozen=True)
class OGCFIntentDecision:
    intent: str
    score: float
    reason: str


def _contains_any(text: str, terms: set[str]) -> set[str]:
    return {term for term in terms if term in text}


def classify_ogcf_intent(query: str | None = None, rows: list[dict[str, Any]] | None = None) -> OGCFIntentDecision:
    """Classify whether OGCF bridge pressure is semantically relevant.

    This is intentionally symbolic and conservative. It is the current safe
    target for a future learned intent gate: geometry may identify risky memory
    regions, but this gate decides whether bridge pressure is meaningful for
    the current question/evidence context.
    """

    query_text = " ".join(str(query or "").lower().split())
    row_text = " ".join(
        " ".join(str(row.get("text") or "").lower().split())
        for row in rows or []
        if isinstance(row, dict)
    )
    combined = f"{query_text} {row_text}".strip()

    query_bridge_hits = _contains_any(query_text, BRIDGE_TERMS)
    query_geometry_hits = _contains_any(query_text, GEOMETRY_TERMS)
    query_maintenance_hits = _contains_any(query_text, MAINTENANCE_TERMS)
    row_bridge_hits = _contains_any(row_text, BRIDGE_TERMS)
    row_geometry_hits = _contains_any(row_text, GEOMETRY_TERMS)
    ordinary_hits = _contains_any(query_text, ORDINARY_FACT_TERMS)

    if query_geometry_hits and (query_bridge_hits or "ogcf" in query_geometry_hits):
        return OGCFIntentDecision(
            intent="bridge_geometry_query",
            score=1.0,
            reason=f"query_geometry:{','.join(sorted(query_geometry_hits))}",
        )
    if query_bridge_hits and (query_geometry_hits or row_geometry_hits):
        return OGCFIntentDecision(
            intent="cross_domain_geometry_synthesis",
            score=0.88,
            reason=f"query_bridge_with_geometry:{','.join(sorted(query_bridge_hits))}",
        )
    if query_bridge_hits:
        return OGCFIntentDecision(
            intent="cross_domain_bridge_synthesis",
            score=0.78,
            reason=f"query_bridge:{','.join(sorted(query_bridge_hits))}",
        )
    if query_maintenance_hits and (row_bridge_hits or row_geometry_hits):
        return OGCFIntentDecision(
            intent="memory_maintenance",
            score=0.72,
            reason=f"maintenance_with_bridge_evidence:{','.join(sorted(query_maintenance_hits))}",
        )
    if ordinary_hits and not query_bridge_hits and not query_geometry_hits:
        return OGCFIntentDecision(
            intent="ordinary_fact_lookup",
            score=0.18,
            reason=f"ordinary_query:{','.join(sorted(ordinary_hits))}",
        )
    if row_bridge_hits and row_geometry_hits:
        return OGCFIntentDecision(
            intent="bridge_evidence_context",
            score=0.55,
            reason="retrieved_bridge_and_geometry_evidence",
        )
    if _contains_any(combined, GEOMETRY_TERMS):
        return OGCFIntentDecision(
            intent="weak_geometry_context",
            score=0.42,
            reason="weak_geometry_terms",
        )
    return OGCFIntentDecision(intent="ordinary_context", score=0.25, reason="default_low_ogcf_intent")
