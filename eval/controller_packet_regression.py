from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.controller_packet import SCHEMA, build_controller_evidence_packet  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_regression_report.md"


def ask_event() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": "op_packet_ask",
        "event_type": "ask",
        "created_at": "2026-06-01T12:00:00+00:00",
        "payload": {
            "request": {
                "query": "Why should the selector keep policy mutation report-only?",
                "namespace": "global",
                "include_global": True,
                "agent_id": "packet-regression",
                "session_id": "sess_packet",
                "top_k": 5,
            },
            "response": {
                "answer": "The evidence says policy mutation remains report-only.",
                "confidence": 0.72,
                "conflict": False,
                "namespace": "global",
                "agent_id": "packet-regression",
                "session_id": "sess_packet",
                "evidence": [
                    {
                        "memory_id": "mem_current",
                        "rank": 1,
                        "namespace": "global",
                        "source": "packet_fixture/current",
                        "domain_name": "selector",
                        "memory_type": "semantic_note",
                        "score": 0.82,
                        "text_match_score": 0.66,
                        "intent_match_score": 0.2,
                        "answer_type_score": 0.1,
                        "claim_scope_score": 0.7,
                        "correction_relevance_score": 1.0,
                        "supersession_score": 0.35,
                        "relation_supersession_score": 0.0,
                        "summary_relation_score": 0.0,
                        "stored_contradiction_score": 0.0,
                        "canonical_is_keeper": True,
                        "canonical_support_count": 3,
                        "text": "Current selector policy mutation remains report-only until external validation passes.",
                    }
                ],
                "raw_results": [
                    {
                        "memory_id": "mem_current",
                        "score": 0.82,
                        "claim_scope_score": 0.7,
                        "supersession_score": 0.35,
                        "canonical_is_keeper": True,
                        "canonical_support_count": 3,
                        "text": "Current selector policy mutation remains report-only until external validation passes.",
                    },
                    {
                        "memory_id": "mem_stale",
                        "score": 0.44,
                        "claim_scope_score": 0.41,
                        "supersession_score": -0.4,
                        "canonical_is_keeper": False,
                        "canonical_support_count": 1,
                        "text": "Old policy memory said automatic mutation could be enabled.",
                    },
                ],
                "stale_context": [],
                "source_context": [],
            },
            "adaptive_memory_context": {
                "schema": "adaptive_memory_context/v1",
                "ok": True,
                "selector_snapshot": {
                    "ok": True,
                    "schema": "adaptive_memory_context/v1",
                    "ogcf_meta_present": True,
                    "decision": {
                        "policy": "periodic_baseline",
                        "action": "PROTECT_PERIODIC",
                        "reason": "fixture",
                        "confidence": 0.91,
                    },
                    "diagnostics": {
                        "retrieval_count": 2,
                        "stale_rows": 1,
                        "current_rows": 1,
                        "stale_current_conflict": 0.4,
                        "ogcf_intent": "cross_domain_bridge_synthesis",
                        "ogcf_bridge_overload_score": 0.81,
                        "ogcf_effective_affected_memory_ratio": 0.62,
                    },
                },
                "features": {
                    "memory_bad_rate": 0.33,
                    "probe_drop": 0.11,
                    "csd_ratio": 0.9,
                },
                "diagnostics": {
                    "retrieval_count": 2,
                    "stale_rows": 1,
                    "current_rows": 1,
                    "stale_current_conflict": 0.4,
                    "ogcf_intent": "cross_domain_bridge_synthesis",
                    "ogcf_bridge_overload_score": 0.81,
                    "ogcf_effective_affected_memory_ratio": 0.62,
                },
                "retrieval_context": [
                    {
                        "memory_id": "mem_current",
                        "score": 0.82,
                        "claim_scope_score": 0.7,
                        "supersession_score": 0.35,
                        "canonical_is_keeper": True,
                        "canonical_support_count": 3,
                        "text": "Current selector policy mutation remains report-only until external validation passes.",
                    },
                    {
                        "memory_id": "mem_stale",
                        "score": 0.44,
                        "claim_scope_score": 0.41,
                        "supersession_score": -0.4,
                        "canonical_is_keeper": False,
                        "canonical_support_count": 1,
                        "text": "Old policy memory said automatic mutation could be enabled.",
                    },
                ],
                "ogcf_meta_present": True,
            },
            "adaptive_residual_shadow": {
                "schema": "adaptive_residual_shadow/v1",
                "ok": True,
                "report_only": True,
                "mutates_answer": False,
                "mutates_selector_policy": False,
                "mutates_memory": False,
                "mutates_config": False,
                "decisions": [
                    {
                        "behavior_family": "supported_evidence",
                        "symbolic_advisory": "uncertain_keep_symbolic",
                        "report_only_advisory": "likely_helpful",
                        "would_override": True,
                        "learned_risk_label": "safe_supported_evidence_rescue",
                        "learned_risk_suppressed": False,
                        "learned_risk_disagrees_with_terms": True,
                    },
                    {
                        "behavior_family": "stale_conflict",
                        "symbolic_advisory": "likely_helpful",
                        "report_only_advisory": "likely_helpful",
                        "would_override": False,
                        "learned_risk_label": "stale_previous_lookup",
                        "learned_risk_suppressed": True,
                        "learned_risk_disagrees_with_terms": True,
                    },
                ],
            },
            "resolver_shadow": {
                "schema": "resolver_shadow/v1",
                "ok": True,
                "actions": ["require_evidence_backed_answer", "emit_ogcf_bridge_warning"],
                "report_only": True,
                "mutates_answer": False,
                "mutates_config": False,
            },
        },
    }


def feedback_events() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            "operation_id": "op_packet_answer_feedback",
            "linked_operation_id": "op_packet_ask",
            "event_type": "feedback",
            "payload": {
                "feedback": {
                    "feedback_scope": "answer",
                    "label": "answer_correct",
                    "rating": 1.0,
                    "linked_operation_id": "op_packet_ask",
                    "selected_memory_ids": ["mem_current"],
                }
            },
        },
        {
            "schema_version": 1,
            "operation_id": "op_packet_memory_feedback",
            "linked_operation_id": "op_packet_ask",
            "event_type": "feedback",
            "payload": {
                "feedback": {
                    "feedback_scope": "memory",
                    "label": "useful",
                    "rating": 1.0,
                    "memory_id": "mem_current",
                    "linked_operation_id": "op_packet_ask",
                }
            },
        },
    ]


def main() -> int:
    packet = build_controller_evidence_packet(ask_event(), feedback_events())
    context_features = ((packet.get("evidence_context") or {}).get("features") or {})
    checks = {
        "schema": packet.get("schema") == SCHEMA,
        "request_preserved": packet["request"]["query"].startswith("Why should the selector"),
        "evidence_states": packet["evidence"]["state_summary"]["has_current"]
        and packet["evidence"]["state_summary"]["has_stale"],
        "canonical_summary": packet["canonical"]["max_support_count"] == 3
        and packet["canonical"]["nonkeeper_rows"] == 1,
        "ogcf_fields": packet["ogcf"]["meta_present"] is True
        and packet["ogcf"]["intent"] == "cross_domain_bridge_synthesis",
        "evidence_context_view": packet["evidence_context"]["schema"] == "evidence_context_packet_view/v1"
        and packet["evidence_context"]["selected_count"] == 1
        and packet["evidence_context"]["retrieval_count"] == 2
        and packet["evidence_context"]["stale_conflict_present"] is True
        and context_features.get("selected_count") == 1
        and context_features.get("retrieval_count") == 2
        and context_features.get("ogcf_bridge_overload_score") == 0.81
        and context_features.get("ogcf_effective_affected_memory_ratio") == 0.62,
        "selector_decision": packet["selector"]["decision"]["policy"] == "periodic_baseline",
        "residual_summary": packet["adaptive_residual_shadow"]["would_override_count"] == 1
        and packet["adaptive_residual_shadow"]["learned_risk_suppressed_count"] == 1,
        "feedback_join": packet["feedback_summary"]["has_answer_feedback"]
        and packet["feedback_summary"]["has_memory_feedback"],
        "report_only": packet["report_only"] is True
        and packet["mutates_runtime"] is False
        and packet["mutates_config"] is False,
    }
    report = {
        "schema": "controller_packet_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "packet": packet,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Evidence Packet Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
