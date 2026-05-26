from __future__ import annotations

import math
from typing import Any

from core.adaptive_behavior import normalize_adaptive_behavior_config
from core.evidence_context import (
    build_evidence_context_features,
    build_evidence_context_summary,
    contains_any,
    evidence_context_features_dict,
    float_value,
    max_row_signal,
    normalize_text,
    ordinary_fact_lookup,
    resolver_actions,
    selected_evidence,
)


def _float(value: Any, default: float = 0.0) -> float:
    return float_value(value, default)


def _normalize(value: Any) -> str:
    return normalize_text(value)


def _sigmoid(value: float) -> float:
    if value < -40:
        return 0.0
    if value > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def _selected_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return selected_evidence(evidence)


def _resolver_actions(resolver_shadow: dict[str, Any] | None) -> set[str]:
    return resolver_actions(resolver_shadow)


def _ordinary_fact_lookup(query: str, diagnostics: dict[str, Any], resolver_shadow: dict[str, Any] | None) -> bool:
    return ordinary_fact_lookup(query, diagnostics=diagnostics, resolver_shadow=resolver_shadow)


def _contains_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    return contains_any(text, terms)


def _max_row_signal(rows: list[dict[str, Any]], key: str) -> float:
    return max_row_signal(rows, key)


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
    retrieval_rows = getattr(adaptive_context, "retrieval_context", []) if adaptive_context is not None else []
    evidence_summary = build_evidence_context_summary(
        query=query,
        answer=answer,
        evidence=evidence,
        stale_context=stale_context,
        retrieval_context=retrieval_rows,
        diagnostics=diagnostics,
        resolver_shadow=resolver_shadow,
    )
    selected = evidence_summary.selected_evidence
    stale_rows = evidence_summary.stale_context
    actions = evidence_summary.resolver_actions
    evidence_features = build_evidence_context_features(evidence_summary, fallback_features=features)

    top_score = evidence_features.top_score
    claim_score = evidence_features.claim_scope_score
    selected_top_score = evidence_features.selected_top_score
    selected_claim_score = evidence_features.selected_claim_scope_score
    selected_answer_type_score = evidence_features.selected_answer_type_score
    selected_text_score = evidence_features.selected_text_match_score
    selected_intent_score = evidence_features.selected_intent_match_score
    raw_answer_type_score = evidence_features.answer_type_score
    scope_deflection = evidence_features.scope_deflection_penalty
    memory_bad_rate = evidence_features.memory_bad_rate
    stale_conflict = evidence_features.stale_current_conflict
    contradiction = evidence_features.contradiction_peak
    base = _base_signal(
        top_score=top_score,
        claim_score=claim_score,
        memory_bad_rate=memory_bad_rate,
        stale_conflict=stale_conflict,
        contradiction=contradiction,
    )
    ordinary = evidence_summary.ordinary_fact_lookup
    ogcf_score = evidence_features.ogcf_bridge_overload_score
    ogcf_effective = evidence_features.ogcf_effective_affected_memory_ratio
    answer_text = evidence_summary.answer_text
    query_text = evidence_summary.query_text
    sensitive_terms = shadow_cfg.get("sensitive_support_terms") if isinstance(shadow_cfg.get("sensitive_support_terms"), list) else []
    stale_terms = shadow_cfg.get("stale_support_terms") if isinstance(shadow_cfg.get("stale_support_terms"), list) else []
    current_terms = (
        shadow_cfg.get("current_support_terms") if isinstance(shadow_cfg.get("current_support_terms"), list) else []
    )
    ordinary_bridge_terms = (
        shadow_cfg.get("ordinary_bridge_terms") if isinstance(shadow_cfg.get("ordinary_bridge_terms"), list) else []
    )
    support_sensitive = _contains_any(query_text, sensitive_terms)
    support_stale = _contains_any(query_text, stale_terms)
    support_current = _contains_any(query_text, current_terms)
    support_ordinary_bridge_lookup = _contains_any(query_text, ordinary_bridge_terms)

    decisions: list[dict[str, Any]] = []

    supported_prob = _sigmoid(2.2 * (base - 0.25))
    supported_reasons = ["selected_evidence_present"] if selected else ["no_selected_evidence"]
    if selected:
        support_quality = max(
            selected_top_score,
            0.55 * selected_claim_score + 0.35 * selected_text_score + 0.25 * selected_intent_score,
            0.50 * selected_answer_type_score + 0.35 * selected_top_score,
        )
        if support_sensitive or support_stale or support_ordinary_bridge_lookup:
            supported_prob = min(supported_prob, 0.32)
            supported_reasons.append("selected_evidence_context_risk_cap")
        elif selected_top_score >= 0.50 and (
            selected_claim_score >= 0.50
            or selected_text_score >= 0.50
            or selected_intent_score >= 0.80
            or selected_answer_type_score >= 0.80
        ):
            supported_prob = max(supported_prob, 0.72)
            supported_reasons.append("selected_evidence_high_quality_match")
        elif selected_answer_type_score >= 0.80 and selected_top_score >= 0.45:
            supported_prob = max(supported_prob, 0.70)
            supported_reasons.append("selected_evidence_answer_type_match")
        elif selected_top_score < 0.40:
            supported_prob = min(supported_prob, 0.32)
            supported_reasons.append("selected_evidence_low_retrieval_support")
        elif support_quality >= 0.52:
            supported_prob = max(supported_prob, 0.58)
            supported_reasons.append("selected_evidence_partial_quality_match")
        elif supported_prob < float(shadow_cfg["negative_threshold"]):
            supported_prob = float(shadow_cfg["negative_threshold"]) + 0.04
            supported_reasons.append("selected_evidence_low_confidence_floor")
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
    missing_no_evidence_refusal_prob = _float(shadow_cfg.get("missing_support_no_evidence_refusal_probability"), 0.80)
    missing_selected_sensitive_prob = _float(shadow_cfg.get("missing_support_selected_sensitive_probability"), 0.76)
    missing_selected_evidence_prob = _float(shadow_cfg.get("missing_support_selected_evidence_probability"), 0.50)
    missing_no_evidence_prob = _float(shadow_cfg.get("missing_support_no_evidence_probability"), 0.58)
    if not selected and has_refusal:
        missing_prob = missing_no_evidence_refusal_prob
    elif support_sensitive:
        missing_prob = missing_selected_sensitive_prob
    elif selected:
        missing_prob = missing_selected_evidence_prob
    else:
        missing_prob = missing_no_evidence_prob
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
    explicit_stale_signal = stale_conflict > 0.0 or support_stale
    requires_explicit_stale_signal = bool(shadow_cfg.get("stale_conflict_requires_explicit_signal"))
    stale_positive_prob = _float(shadow_cfg.get("stale_conflict_positive_probability"), 0.82)
    stale_neutral_prob = _float(shadow_cfg.get("stale_conflict_neutral_probability"), 0.50)
    if stale_present and (explicit_stale_signal or not requires_explicit_stale_signal) and not support_current:
        stale_prob = stale_positive_prob
        stale_reasons = ["stale_conflict_present"]
        if not requires_explicit_stale_signal and not explicit_stale_signal:
            stale_reasons.append("config_allows_incidental_stale_context")
    elif stale_present:
        stale_prob = stale_neutral_prob
        stale_reasons = ["stale_context_present_without_explicit_conflict"]
        if support_current:
            stale_reasons.append("current_query_suppresses_stale_advisory")
    else:
        stale_prob = stale_neutral_prob
        stale_reasons = ["no_stale_conflict_signal"]
    decisions.append(
        _decision(
            behavior_family="stale_conflict",
            probability=stale_prob,
            route_confidence=0.54 if stale_present else 0.44,
            reasons=stale_reasons,
            shadow_cfg=shadow_cfg,
        )
    )

    scope_terms = shadow_cfg.get("scope_sensitive_terms") if isinstance(shadow_cfg.get("scope_sensitive_terms"), list) else []
    scope_sensitive = _contains_any(query_text, scope_terms)
    weak_selected_scope = bool(selected) and max(selected_claim_score, selected_answer_type_score) < 0.20
    better_raw_scope_available = max(claim_score, raw_answer_type_score) >= 0.65
    explicit_scope_deflection = scope_deflection >= 0.20
    if scope_sensitive or weak_selected_scope or explicit_scope_deflection:
        wrong_scope_deflection_prob = _float(shadow_cfg.get("wrong_scope_deflection_probability"), 0.78)
        wrong_scope_no_evidence_github_prob = _float(shadow_cfg.get("wrong_scope_no_evidence_github_probability"), 0.68)
        wrong_scope_no_evidence_prob = _float(shadow_cfg.get("wrong_scope_no_evidence_probability"), 0.54)
        wrong_scope_selected_evidence_prob = _float(shadow_cfg.get("wrong_scope_selected_evidence_probability"), 0.46)
        wrong_scope_route_confidence = _float(shadow_cfg.get("wrong_scope_route_confidence"), 0.56)
        wrong_scope_low_route_confidence = _float(shadow_cfg.get("wrong_scope_low_route_confidence"), 0.42)
        if explicit_scope_deflection or (weak_selected_scope and better_raw_scope_available):
            wrong_scope_prob = wrong_scope_deflection_prob
            wrong_scope_reasons = ["scope_deflection_signal"]
        elif not selected and ("github" in query_text and ("upload" in query_text or "approval" in query_text)):
            wrong_scope_prob = wrong_scope_no_evidence_github_prob
            wrong_scope_reasons = ["scope_sensitive_query_without_selected_evidence"]
        elif not selected:
            wrong_scope_prob = wrong_scope_no_evidence_prob
            wrong_scope_reasons = ["scope_sensitive_query_without_selected_evidence"]
        else:
            wrong_scope_prob = wrong_scope_selected_evidence_prob
            wrong_scope_reasons = ["scope_sensitive_query_with_selected_evidence"]
        if better_raw_scope_available:
            wrong_scope_reasons.append("candidate_scope_match_available")
        decisions.append(
            _decision(
                behavior_family="wrong_scope",
                probability=wrong_scope_prob,
                route_confidence=wrong_scope_route_confidence
                if (explicit_scope_deflection or scope_sensitive)
                else wrong_scope_low_route_confidence,
                reasons=wrong_scope_reasons,
                shadow_cfg=shadow_cfg,
            )
        )

    ogcf_present = bool(getattr(adaptive_context, "ogcf_meta_present", False))
    bridge_pressure = max(ogcf_score, ogcf_effective)
    bridge_terms = shadow_cfg.get("bridge_intent_terms") if isinstance(shadow_cfg.get("bridge_intent_terms"), list) else []
    bridge_intent = _contains_any(query_text, bridge_terms)
    ordinary_bridge_lookup = ordinary or support_ordinary_bridge_lookup
    if ogcf_present or "emit_ogcf_bridge_warning" in actions or bridge_pressure > 0.0 or bridge_intent:
        if ordinary:
            bridge_prob = 0.22
            bridge_reasons = ["ordinary_fact_lookup_suppresses_bridge_warning"]
        elif ordinary_bridge_lookup:
            bridge_prob = 0.28
            bridge_reasons = ["ordinary_bridge_lookup_suppresses_bridge_warning"]
        elif bridge_intent and not ogcf_present and bridge_pressure <= 0.0:
            bridge_prob = 0.68
            bridge_reasons = ["bridge_intent_query_without_ogcf_metadata"]
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
            "scope_sensitive_query": scope_sensitive,
            "scope_deflection_penalty": scope_deflection,
            "bridge_intent_query": bridge_intent,
            "support_sensitive_query": support_sensitive,
            "support_stale_query": support_stale,
            "support_current_query": support_current,
            "evidence_context_features": evidence_context_features_dict(evidence_features),
        },
    }
