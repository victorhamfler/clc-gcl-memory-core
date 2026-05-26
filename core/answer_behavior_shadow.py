from __future__ import annotations

from typing import Any

from core.evidence_context import (
    build_evidence_context_summary,
    diagnostics_from_selector_snapshot,
    float_value,
    normalize_text,
    ordinary_fact_lookup,
    selected_evidence,
    stale_conflict_present,
)


DEFAULT_RESOLVER_SHADOW_CONFIG = {
    "enabled": False,
    "include_in_outcome_log": False,
    "bridge_warning_score_threshold": 0.70,
    "bridge_warning_effective_ratio_threshold": 0.50,
    "refusal_markers": (
        "do not have enough",
        "not enough memory evidence",
        "insufficient",
        "cannot answer",
        "no memory evidence",
        "not have memory evidence",
    ),
}


def normalize_resolver_shadow_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    defaults = dict(DEFAULT_RESOLVER_SHADOW_CONFIG)
    refusal_markers = cfg.get("refusal_markers", defaults["refusal_markers"])
    if isinstance(refusal_markers, str):
        refusal_markers = tuple(part.strip().lower() for part in refusal_markers.split(",") if part.strip())
    elif isinstance(refusal_markers, (list, tuple, set)):
        refusal_markers = tuple(str(part).strip().lower() for part in refusal_markers if str(part).strip())
    else:
        refusal_markers = defaults["refusal_markers"]
    return {
        "enabled": bool(cfg.get("enabled", defaults["enabled"])),
        "include_in_outcome_log": bool(cfg.get("include_in_outcome_log", defaults["include_in_outcome_log"])),
        "bridge_warning_score_threshold": _float(
            cfg.get("bridge_warning_score_threshold"),
            defaults["bridge_warning_score_threshold"],
        ),
        "bridge_warning_effective_ratio_threshold": _float(
            cfg.get("bridge_warning_effective_ratio_threshold"),
            defaults["bridge_warning_effective_ratio_threshold"],
        ),
        "refusal_markers": refusal_markers,
    }


def _float(value: Any, default: float) -> float:
    return float_value(value, default)


def _normalize(value: Any) -> str:
    return normalize_text(value)


def _diagnostics(selector_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return diagnostics_from_selector_snapshot(selector_snapshot)


def _selected_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return selected_evidence(evidence)


def _has_refusal_language(answer: str, markers: tuple[str, ...]) -> bool:
    text = _normalize(answer)
    return any(marker in text for marker in markers)


def _ordinary_fact_lookup(query: str, selector_snapshot: dict[str, Any] | None) -> bool:
    return ordinary_fact_lookup(query, selector_snapshot=selector_snapshot)


def _stale_conflict_present(
    *,
    evidence: list[dict[str, Any]],
    stale_context: list[dict[str, Any]] | None,
    selector_snapshot: dict[str, Any] | None,
    conflict: bool,
) -> bool:
    return stale_conflict_present(
        evidence=evidence,
        stale_context=stale_context,
        selector_snapshot=selector_snapshot,
        conflict=conflict,
    )


def resolver_shadow_actions(
    *,
    query: str,
    answer: str,
    evidence: list[dict[str, Any]] | None,
    stale_context: list[dict[str, Any]] | None = None,
    selector_snapshot: dict[str, Any] | None = None,
    conflict: bool = False,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = normalize_resolver_shadow_config(config)
    evidence_summary = build_evidence_context_summary(
        query=query,
        answer=answer,
        evidence=evidence,
        stale_context=stale_context,
        selector_snapshot=selector_snapshot,
        conflict=conflict,
    )
    selected_evidence = evidence_summary.selected_evidence
    diagnostics = evidence_summary.diagnostics
    snapshot = selector_snapshot if isinstance(selector_snapshot, dict) else {}
    actions: list[str] = []
    reasons: list[str] = []
    annotations: list[dict[str, Any]] = []

    if selected_evidence:
        actions.append("require_evidence_backed_answer")
        reasons.append("selected_evidence_present")
        annotations.append(
            {
                "kind": "selected_evidence_requirement",
                "severity": "info",
                "message": "Answer should stay grounded in selected evidence.",
                "selected_memory_ids": [
                    str(row.get("memory_id"))
                    for row in selected_evidence
                    if row.get("memory_id")
                ],
            }
        )

    stale_conflict = evidence_summary.stale_conflict_present
    if stale_conflict:
        actions.append("disclose_stale_conflict")
        reasons.append("stale_conflict_present")
        annotations.append(
            {
                "kind": "stale_conflict_disclosure",
                "severity": "warning",
                "message": "Retrieved evidence includes stale/current conflict; answer should disclose that current evidence is preferred.",
            }
        )

    if selected_evidence and bool(snapshot.get("ogcf_meta_present")) and not evidence_summary.ordinary_fact_lookup:
        ogcf_score = _float(diagnostics.get("ogcf_bridge_overload_score"), 0.0)
        ogcf_effective = _float(diagnostics.get("ogcf_effective_affected_memory_ratio"), 0.0)
        if (
            ogcf_score >= cfg["bridge_warning_score_threshold"]
            or ogcf_effective >= cfg["bridge_warning_effective_ratio_threshold"]
        ):
            actions.append("emit_ogcf_bridge_warning")
            reasons.append("ogcf_bridge_pressure_with_selected_evidence")
            annotations.append(
                {
                    "kind": "ogcf_bridge_warning",
                    "severity": "warning",
                    "message": "OGCF diagnostics suggest bridge pressure; answer should mention cross-domain uncertainty when relevant.",
                    "ogcf_bridge_overload_score": ogcf_score,
                    "ogcf_effective_affected_memory_ratio": ogcf_effective,
                }
            )

    if not selected_evidence:
        actions.append("preserve_missing_support_refusal")
        reasons.append("no_selected_evidence")
        annotations.append(
            {
                "kind": "missing_support_refusal",
                "severity": "info",
                "message": "No selected evidence supports the query; answer should preserve refusal or insufficient-support language.",
                "answer_has_refusal_language": _has_refusal_language(answer, cfg["refusal_markers"]),
            }
        )

    unique_actions = list(dict.fromkeys(actions))
    return {
        "schema": "resolver_shadow_actions/v1",
        "enabled": bool(cfg["enabled"]),
        "report_only": True,
        "mutates_answer": False,
        "mutates_config": False,
        "actions": unique_actions,
        "reasons": list(dict.fromkeys(reasons)),
        "annotations": annotations,
        "diagnostics": {
            "selected_evidence_count": len(selected_evidence),
            "stale_context_count": evidence_summary.stale_context_count,
            "ordinary_fact_lookup": evidence_summary.ordinary_fact_lookup,
            "stale_conflict": stale_conflict,
            "ogcf_meta_present": bool(snapshot.get("ogcf_meta_present")),
        },
    }
