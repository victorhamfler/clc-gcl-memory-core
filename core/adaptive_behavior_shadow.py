from __future__ import annotations

import math
from typing import Any

from core.adaptive_behavior import normalize_adaptive_behavior_config


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sigmoid(value: float) -> float:
    if value < -40:
        return 0.0
    if value > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def _selected_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [row for row in (evidence or []) if isinstance(row, dict)]


def _resolver_actions(resolver_shadow: dict[str, Any] | None) -> set[str]:
    if not isinstance(resolver_shadow, dict):
        return set()
    return {str(item or "").strip() for item in resolver_shadow.get("actions") or [] if str(item or "").strip()}


def _ordinary_fact_lookup(query: str, diagnostics: dict[str, Any], resolver_shadow: dict[str, Any] | None) -> bool:
    resolver_diagnostics = resolver_shadow.get("diagnostics") if isinstance(resolver_shadow, dict) else {}
    if isinstance(resolver_diagnostics, dict) and resolver_diagnostics.get("ordinary_fact_lookup") is True:
        return True
    if _normalize(diagnostics.get("ogcf_intent")) == "ordinary_fact_lookup":
        return True
    text = _normalize(query)
    ordinary_terms = ("when is", "what is", "what was", "where is", "calendar", "scheduled", "location")
    return any(term in text for term in ordinary_terms)


def _advisory(probability: float, shadow_cfg: dict[str, Any], route_confidence: float) -> str:
    if route_confidence < float(shadow_cfg["min_route_confidence"]):
        return "uncertain_keep_symbolic"
    if probability >= float(shadow_cfg["positive_threshold"]):
        return "likely_helpful"
    if probability <= float(shadow_cfg["negative_threshold"]):
        return "likely_harmful"
    return "uncertain_keep_symbolic"


def _base_signal(
    *,
    top_score: float,
    claim_score: float,
    memory_bad_rate: float,
    stale_conflict: float,
    contradiction: float,
) -> float:
    return 1.0 * top_score + 0.7 * claim_score - 0.8 * memory_bad_rate - 0.8 * stale_conflict - 0.6 * contradiction


def _decision(
    *,
    behavior_family: str,
    probability: float,
    route_confidence: float,
    reasons: list[str],
    shadow_cfg: dict[str, Any],
) -> dict[str, Any]:
    advisory = _advisory(probability, shadow_cfg, route_confidence)
    return {
        "behavior_family": behavior_family,
        "route": "runtime_symbolic_adaptive_context",
        "route_confidence": round(float(route_confidence), 6),
        "shadow_probability": round(float(probability), 6),
        "advisory": advisory,
        "reasons": list(dict.fromkeys(reasons)),
        "mutates_runtime": False,
        "mutates_config": False,
    }


def adaptive_behavior_shadow_advisories(
    *,
    query: str,
    answer: str,
    evidence: list[dict[str, Any]] | None,
    stale_context: list[dict[str, Any]] | None,
    adaptive_context: Any,
    resolver_shadow: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return report-only adaptive behavior advisories for live runtime logs.

    This surface deliberately does not import eval-time models or mutate answers.
    It exposes the same semantic behavior-family language used by the learned
    shadow experiments, while staying conservative enough for live collection.
    """

    behavior_config = normalize_adaptive_behavior_config(config)
    shadow_cfg = behavior_config["shadow"]
    diagnostics = getattr(adaptive_context, "diagnostics", {}) if adaptive_context is not None else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    features = adaptive_context.feature_dict() if getattr(adaptive_context, "ok", False) else {}
    selected = _selected_evidence(evidence)
    stale_rows = _selected_evidence(stale_context)
    actions = _resolver_actions(resolver_shadow)

    retrieval_rows = getattr(adaptive_context, "retrieval_context", []) if adaptive_context is not None else []
    top_score = max((_float(row.get("score"), 0.0) for row in retrieval_rows if isinstance(row, dict)), default=0.0)
    claim_score = max((_float(row.get("claim_scope_score"), 0.0) for row in retrieval_rows if isinstance(row, dict)), default=0.0)
    memory_bad_rate = _float(diagnostics.get("memory_bad_rate"), _float(features.get("memory_bad_rate"), 0.18))
    stale_conflict = _float(diagnostics.get("stale_current_conflict"), 0.0)
    contradiction = _float(diagnostics.get("contradiction_peak"), 0.0)
    base = _base_signal(
        top_score=top_score,
        claim_score=claim_score,
        memory_bad_rate=memory_bad_rate,
        stale_conflict=stale_conflict,
        contradiction=contradiction,
    )
    ordinary = _ordinary_fact_lookup(query, diagnostics, resolver_shadow)
    ogcf_score = _float(diagnostics.get("ogcf_bridge_overload_score"), 0.0)
    ogcf_effective = _float(diagnostics.get("ogcf_effective_affected_memory_ratio"), 0.0)
    answer_text = _normalize(answer)

    decisions: list[dict[str, Any]] = []

    supported_prob = _sigmoid(2.2 * (base - 0.25))
    supported_reasons = ["selected_evidence_present"] if selected else ["no_selected_evidence"]
    decisions.append(
        _decision(
            behavior_family="supported_evidence",
            probability=supported_prob if selected else min(supported_prob, 0.34),
            route_confidence=0.52 if selected else 0.42,
            reasons=supported_reasons,
            shadow_cfg=shadow_cfg,
        )
    )

    missing_markers = ("not enough", "insufficient", "cannot answer", "no memory evidence", "do not have enough")
    has_refusal = any(marker in answer_text for marker in missing_markers)
    missing_prob = 0.80 if not selected and has_refusal else 0.30 if selected else 0.58
    decisions.append(
        _decision(
            behavior_family="missing_support",
            probability=missing_prob,
            route_confidence=0.50,
            reasons=(["no_selected_evidence"] if not selected else ["selected_evidence_present"])
            + (["answer_has_refusal_language"] if has_refusal else []),
            shadow_cfg=shadow_cfg,
        )
    )

    stale_present = stale_conflict > 0.0 or bool(stale_rows) or "disclose_stale_conflict" in actions
    stale_prob = 0.82 if stale_present else 0.28
    decisions.append(
        _decision(
            behavior_family="stale_conflict",
            probability=stale_prob,
            route_confidence=0.54 if stale_present else 0.44,
            reasons=["stale_conflict_present"] if stale_present else ["no_stale_conflict_signal"],
            shadow_cfg=shadow_cfg,
        )
    )

    ogcf_present = bool(getattr(adaptive_context, "ogcf_meta_present", False))
    bridge_pressure = max(ogcf_score, ogcf_effective)
    if ogcf_present or "emit_ogcf_bridge_warning" in actions or bridge_pressure > 0.0:
        if ordinary:
            bridge_prob = 0.22
            bridge_reasons = ["ordinary_fact_lookup_suppresses_bridge_warning"]
        else:
            bridge_prob = _sigmoid(4.0 * (bridge_pressure - 0.45))
            bridge_reasons = ["ogcf_bridge_pressure"] if bridge_pressure > 0 else ["ogcf_meta_present"]
        decisions.append(
            _decision(
                behavior_family="ogcf_bridge_warning",
                probability=bridge_prob,
                route_confidence=0.58 if ogcf_present else 0.42,
                reasons=bridge_reasons,
                shadow_cfg=shadow_cfg,
            )
        )

    advisory_counts: dict[str, int] = {}
    for row in decisions:
        advisory_counts[row["advisory"]] = advisory_counts.get(row["advisory"], 0) + 1

    return {
        "schema": "adaptive_behavior_shadow/v1",
        "enabled": bool(shadow_cfg.get("enabled")),
        "report_only": True,
        "mutates_answer": False,
        "mutates_selector_policy": False,
        "mutates_memory": False,
        "mutates_config": False,
        "behavior_config_schema": behavior_config["schema"],
        "advisory_counts": dict(sorted(advisory_counts.items())),
        "decisions": decisions,
        "diagnostics": {
            "selected_evidence_count": len(selected),
            "stale_context_count": len(stale_rows),
            "ordinary_fact_lookup": ordinary,
            "ogcf_meta_present": ogcf_present,
            "ogcf_bridge_overload_score": ogcf_score,
            "ogcf_effective_affected_memory_ratio": ogcf_effective,
        },
    }
