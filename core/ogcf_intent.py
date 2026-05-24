from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_BRIDGE_TERMS = {
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
DEFAULT_GEOMETRY_TERMS = {
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
DEFAULT_MAINTENANCE_TERMS = {
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
DEFAULT_ORDINARY_FACT_TERMS = {
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
DEFAULT_OGCF_INTENT_SCORES = {
    "bridge_geometry_query": 1.0,
    "cross_domain_geometry_synthesis": 0.88,
    "cross_domain_bridge_synthesis": 0.78,
    "memory_maintenance": 0.72,
    "ordinary_fact_lookup": 0.18,
    "bridge_evidence_context": 0.55,
    "weak_geometry_context": 0.42,
    "ordinary_context": 0.25,
}
DEFAULT_OGCF_INTENT_GATE = {
    "high_intent_threshold": 0.75,
    "medium_intent_threshold": 0.55,
    "high_affected_multiplier": 0.75,
    "medium_min_weighted_ratio": 0.35,
    "low_min_weighted_ratio": 0.55,
}
DEFAULT_OGCF_INTENT_CONFIG = {
    "bridge_terms": tuple(sorted(DEFAULT_BRIDGE_TERMS)),
    "geometry_terms": tuple(sorted(DEFAULT_GEOMETRY_TERMS)),
    "maintenance_terms": tuple(sorted(DEFAULT_MAINTENANCE_TERMS)),
    "ordinary_fact_terms": tuple(sorted(DEFAULT_ORDINARY_FACT_TERMS)),
    "scores": dict(DEFAULT_OGCF_INTENT_SCORES),
    "gate": dict(DEFAULT_OGCF_INTENT_GATE),
}


@dataclass(frozen=True)
class OGCFIntentDecision:
    intent: str
    score: float
    reason: str


def parse_term_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(term).strip().lower() for term in value if str(term).strip())
    raw = str(value or "")
    for separator in ("|", ";"):
        raw = raw.replace(separator, ",")
    return tuple(term.strip().lower() for term in raw.split(",") if term.strip())


def normalize_ogcf_intent_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})

    def terms(name: str, defaults: set[str]) -> tuple[str, ...]:
        configured = parse_term_sequence(cfg.get(name))
        if not configured:
            return tuple(sorted(defaults))
        return tuple(sorted(set(defaults) | set(configured)))

    scores = dict(DEFAULT_OGCF_INTENT_SCORES)
    raw_scores = cfg.get("scores")
    if isinstance(raw_scores, dict):
        for key, value in raw_scores.items():
            if str(key) in scores:
                scores[str(key)] = _float_value(value, scores[str(key)])

    gate = dict(DEFAULT_OGCF_INTENT_GATE)
    raw_gate = cfg.get("gate")
    if isinstance(raw_gate, dict):
        for key, value in raw_gate.items():
            if str(key) in gate:
                gate[str(key)] = _float_value(value, gate[str(key)])

    return {
        "bridge_terms": terms("bridge_terms", DEFAULT_BRIDGE_TERMS),
        "geometry_terms": terms("geometry_terms", DEFAULT_GEOMETRY_TERMS),
        "maintenance_terms": terms("maintenance_terms", DEFAULT_MAINTENANCE_TERMS),
        "ordinary_fact_terms": terms("ordinary_fact_terms", DEFAULT_ORDINARY_FACT_TERMS),
        "scores": scores,
        "gate": gate,
    }


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _contains_any(text: str, terms: set[str]) -> set[str]:
    return {term for term in terms if term in text}


def classify_ogcf_intent(
    query: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> OGCFIntentDecision:
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

    cfg = normalize_ogcf_intent_config(config)
    bridge_terms = set(cfg["bridge_terms"])
    geometry_terms = set(cfg["geometry_terms"])
    maintenance_terms = set(cfg["maintenance_terms"])
    ordinary_fact_terms = set(cfg["ordinary_fact_terms"])
    scores = cfg["scores"]

    query_bridge_hits = _contains_any(query_text, bridge_terms)
    query_geometry_hits = _contains_any(query_text, geometry_terms)
    query_maintenance_hits = _contains_any(query_text, maintenance_terms)
    row_bridge_hits = _contains_any(row_text, bridge_terms)
    row_geometry_hits = _contains_any(row_text, geometry_terms)
    ordinary_hits = _contains_any(query_text, ordinary_fact_terms)

    if query_geometry_hits and (query_bridge_hits or "ogcf" in query_geometry_hits):
        return OGCFIntentDecision(
            intent="bridge_geometry_query",
            score=float(scores["bridge_geometry_query"]),
            reason=f"query_geometry:{','.join(sorted(query_geometry_hits))}",
        )
    if query_bridge_hits and (query_geometry_hits or row_geometry_hits):
        return OGCFIntentDecision(
            intent="cross_domain_geometry_synthesis",
            score=float(scores["cross_domain_geometry_synthesis"]),
            reason=f"query_bridge_with_geometry:{','.join(sorted(query_bridge_hits))}",
        )
    if query_bridge_hits:
        return OGCFIntentDecision(
            intent="cross_domain_bridge_synthesis",
            score=float(scores["cross_domain_bridge_synthesis"]),
            reason=f"query_bridge:{','.join(sorted(query_bridge_hits))}",
        )
    if query_maintenance_hits and (row_bridge_hits or row_geometry_hits):
        return OGCFIntentDecision(
            intent="memory_maintenance",
            score=float(scores["memory_maintenance"]),
            reason=f"maintenance_with_bridge_evidence:{','.join(sorted(query_maintenance_hits))}",
        )
    if ordinary_hits and not query_bridge_hits and not query_geometry_hits:
        return OGCFIntentDecision(
            intent="ordinary_fact_lookup",
            score=float(scores["ordinary_fact_lookup"]),
            reason=f"ordinary_query:{','.join(sorted(ordinary_hits))}",
        )
    if row_bridge_hits and row_geometry_hits:
        return OGCFIntentDecision(
            intent="bridge_evidence_context",
            score=float(scores["bridge_evidence_context"]),
            reason="retrieved_bridge_and_geometry_evidence",
        )
    if _contains_any(combined, geometry_terms):
        return OGCFIntentDecision(
            intent="weak_geometry_context",
            score=float(scores["weak_geometry_context"]),
            reason="weak_geometry_terms",
        )
    return OGCFIntentDecision(
        intent="ordinary_context",
        score=float(scores["ordinary_context"]),
        reason="default_low_ogcf_intent",
    )
