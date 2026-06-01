from __future__ import annotations

from typing import Any

from core.evidence_states import classify_memory_state, evidence_is_too_weak, requires_sensitive_evidence


SCHEMA = "controller_evidence_packet/v1"

RETRIEVAL_FIELDS = (
    "memory_id",
    "rank",
    "namespace",
    "source",
    "domain_name",
    "memory_type",
    "score",
    "cosine",
    "feedback_score",
    "source_reliability",
    "domain_reliability",
    "usage_count",
    "text_match_score",
    "intent_match_score",
    "answer_type_score",
    "claim_scope_score",
    "identifier_match_score",
    "correction_relevance_score",
    "correction_chain_score",
    "authority_state",
    "supersession_score",
    "relation_supersession_score",
    "summary_relation_score",
    "stored_contradiction_score",
    "canonical_is_keeper",
    "canonical_support_count",
)


def build_controller_evidence_packet(
    ask_event: dict[str, Any],
    feedback_events: list[dict[str, Any]] | None = None,
    *,
    evidence_state_config: dict[str, Any] | None = None,
    text_limit: int = 280,
) -> dict[str, Any]:
    """Build a stable replay/training packet from an ask event and linked feedback.

    The packet is intentionally compact and report-only. It normalizes the
    fields that selector, resolver, OGCF, and adaptive-shadow evaluations need
    without modifying runtime memory, config, or policy.
    """

    ask_payload = _payload(ask_event)
    request = _dict(ask_payload.get("request"))
    response = _dict(ask_payload.get("response"))
    adaptive_context = _adaptive_context(ask_payload)
    selector_snapshot = _selector_snapshot(ask_payload, adaptive_context)
    diagnostics = _dict(adaptive_context.get("diagnostics")) or _dict(selector_snapshot.get("diagnostics"))
    retrieval_context = _retrieval_context(ask_payload, response, adaptive_context)
    evidence_rows = _compact_rows(response.get("evidence"), evidence_state_config, text_limit=text_limit)
    retrieval_rows = _compact_rows(retrieval_context, evidence_state_config, text_limit=text_limit)
    feedback = [_feedback_summary(item) for item in (feedback_events or []) if isinstance(item, dict)]
    residual = _dict(ask_payload.get("adaptive_residual_shadow")) or _dict(response.get("adaptive_residual_shadow"))
    behavior = _dict(ask_payload.get("adaptive_behavior_shadow")) or _dict(response.get("adaptive_behavior_shadow"))
    resolver = _dict(ask_payload.get("resolver_shadow")) or _dict(response.get("resolver_shadow"))

    return {
        "schema": SCHEMA,
        "operation_id": str(ask_event.get("operation_id") or ""),
        "created_at": ask_event.get("created_at"),
        "event_type": ask_event.get("event_type"),
        "request": {
            "query": str(request.get("query") or response.get("query") or ""),
            "namespace": request.get("namespace") or response.get("namespace"),
            "include_global": request.get("include_global"),
            "agent_id": request.get("agent_id") or response.get("agent_id"),
            "session_id": request.get("session_id") or response.get("session_id"),
            "top_k": request.get("top_k"),
        },
        "answer": {
            "confidence": response.get("confidence"),
            "conflict": bool(response.get("conflict")),
            "evidence_count": len(evidence_rows),
            "raw_result_count": len(_list(response.get("raw_results"))),
            "stale_context_count": len(_list(response.get("stale_context"))),
            "source_context_count": len(_list(response.get("source_context"))),
        },
        "evidence": {
            "selected": evidence_rows,
            "retrieval_context": retrieval_rows,
            "state_summary": _state_summary(retrieval_rows or evidence_rows),
            "too_weak": evidence_is_too_weak(retrieval_rows or evidence_rows, evidence_state_config),
            "requires_sensitive_evidence": requires_sensitive_evidence(
                str(request.get("query") or response.get("query") or ""),
                config=evidence_state_config,
            ),
        },
        "canonical": _canonical_summary(retrieval_rows or evidence_rows),
        "ogcf": _ogcf_summary(diagnostics, selector_snapshot, adaptive_context),
        "selector": {
            "features": _dict(adaptive_context.get("features")),
            "diagnostics": diagnostics,
            "decision": _dict(selector_snapshot.get("decision")),
            "ogcf_meta_present": bool(selector_snapshot.get("ogcf_meta_present") or adaptive_context.get("ogcf_meta_present")),
        },
        "resolver_shadow": _shadow_summary(resolver),
        "adaptive_behavior_shadow": _shadow_summary(behavior),
        "adaptive_residual_shadow": _residual_summary(residual),
        "feedback": feedback,
        "feedback_summary": _feedback_aggregate(feedback),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    return _dict(event.get("payload"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _adaptive_context(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("adaptive_memory_context")
    return value if isinstance(value, dict) else {}


def _selector_snapshot(payload: dict[str, Any], adaptive_context: dict[str, Any]) -> dict[str, Any]:
    value = adaptive_context.get("selector_snapshot")
    if isinstance(value, dict):
        return value
    value = payload.get("selector_snapshot")
    return value if isinstance(value, dict) else {}


def _retrieval_context(
    payload: dict[str, Any],
    response: dict[str, Any],
    adaptive_context: dict[str, Any],
) -> list[dict[str, Any]]:
    for value in (
        adaptive_context.get("retrieval_context"),
        response.get("raw_results"),
        response.get("evidence"),
        payload.get("retrieval_context"),
    ):
        rows = [row for row in _list(value) if isinstance(row, dict)]
        if rows:
            return rows
    return []


def _compact_rows(
    rows: Any,
    evidence_state_config: dict[str, Any] | None,
    *,
    text_limit: int,
) -> list[dict[str, Any]]:
    compacted = []
    for rank, row in enumerate([item for item in _list(rows) if isinstance(item, dict)], start=1):
        item = {field: row.get(field) for field in RETRIEVAL_FIELDS if field in row}
        item["rank"] = item.get("rank") or rank
        item["memory_state"] = str(row.get("memory_state") or classify_memory_state(row, evidence_state_config))
        text = str(row.get("text") or row.get("text_preview") or "")
        if text:
            item["text_preview"] = text[:text_limit]
        compacted.append(item)
    return compacted


def _state_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        state = str(row.get("memory_state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    return {
        "counts": counts,
        "has_current": counts.get("current", 0) > 0,
        "has_stale": counts.get("stale", 0) > 0,
        "has_disputed": counts.get("disputed", 0) > 0,
        "has_summary": counts.get("summary", 0) > 0,
    }


def _canonical_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    support_counts = [int(row.get("canonical_support_count") or 1) for row in rows]
    nonkeepers = sum(1 for row in rows if row.get("canonical_is_keeper") is False)
    total = max(1, len(rows))
    return {
        "max_support_count": max(support_counts or [0]),
        "supported_rows": sum(1 for value in support_counts if value > 1),
        "nonkeeper_rows": nonkeepers,
        "duplicate_pressure": nonkeepers / total,
    }


def _ogcf_summary(
    diagnostics: dict[str, Any],
    selector_snapshot: dict[str, Any],
    adaptive_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "meta_present": bool(selector_snapshot.get("ogcf_meta_present") or adaptive_context.get("ogcf_meta_present")),
        "intent": diagnostics.get("ogcf_intent"),
        "bridge_overload_score": diagnostics.get("ogcf_bridge_overload_score"),
        "effective_affected_memory_ratio": diagnostics.get("ogcf_effective_affected_memory_ratio"),
        "maintenance_pressure": diagnostics.get("ogcf_maintenance_pressure"),
    }


def _shadow_summary(shadow: dict[str, Any]) -> dict[str, Any]:
    if not shadow:
        return {"present": False}
    actions = shadow.get("actions")
    return {
        "present": True,
        "schema": shadow.get("schema"),
        "ok": shadow.get("ok"),
        "actions": actions if isinstance(actions, list) else [],
        "report_only": shadow.get("report_only", True),
        "mutates_answer": bool(shadow.get("mutates_answer", False)),
        "mutates_config": bool(shadow.get("mutates_config", False)),
    }


def _residual_summary(shadow: dict[str, Any]) -> dict[str, Any]:
    if not shadow:
        return {"present": False, "decision_count": 0, "would_override_count": 0}
    decisions = [item for item in _list(shadow.get("decisions")) if isinstance(item, dict)]
    return {
        "present": True,
        "schema": shadow.get("schema"),
        "ok": shadow.get("ok"),
        "decision_count": len(decisions),
        "would_override_count": sum(1 for item in decisions if item.get("would_override")),
        "learned_risk_suppressed_count": sum(1 for item in decisions if item.get("learned_risk_suppressed")),
        "learned_beyond_terms_count": sum(1 for item in decisions if item.get("learned_risk_disagrees_with_terms")),
        "report_only": shadow.get("report_only", True),
        "mutates_answer": bool(shadow.get("mutates_answer", False)),
        "mutates_selector_policy": bool(shadow.get("mutates_selector_policy", False)),
        "mutates_memory": bool(shadow.get("mutates_memory", False)),
        "mutates_config": bool(shadow.get("mutates_config", False)),
        "decisions": [
            {
                "behavior_family": item.get("behavior_family"),
                "symbolic_advisory": item.get("symbolic_advisory"),
                "report_only_advisory": item.get("report_only_advisory"),
                "would_override": bool(item.get("would_override")),
                "learned_risk_label": item.get("learned_risk_label"),
                "learned_risk_suppressed": bool(item.get("learned_risk_suppressed")),
            }
            for item in decisions
        ],
    }


def _feedback_summary(event: dict[str, Any]) -> dict[str, Any]:
    data = _payload(event)
    feedback = _dict(data.get("feedback")) or _dict(data.get("request"))
    return {
        "operation_id": event.get("operation_id"),
        "linked_operation_id": event.get("linked_operation_id") or feedback.get("linked_operation_id"),
        "scope": feedback.get("feedback_scope") or feedback.get("target_type") or feedback.get("scope"),
        "label": feedback.get("label"),
        "rating": feedback.get("rating"),
        "memory_id": feedback.get("memory_id"),
        "selected_memory_ids": feedback.get("selected_memory_ids") if isinstance(feedback.get("selected_memory_ids"), list) else [],
    }


def _feedback_aggregate(feedback: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, int] = {}
    scopes: dict[str, int] = {}
    for item in feedback:
        label = str(item.get("label") or "")
        scope = str(item.get("scope") or "")
        if label:
            labels[label] = labels.get(label, 0) + 1
        if scope:
            scopes[scope] = scopes.get(scope, 0) + 1
    return {
        "count": len(feedback),
        "labels": labels,
        "scopes": scopes,
        "has_answer_feedback": any(str(item.get("scope") or "") == "answer" for item in feedback),
        "has_memory_feedback": any(str(item.get("scope") or "") not in {"", "answer", "response"} for item in feedback),
    }
