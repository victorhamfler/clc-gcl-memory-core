from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.evidence_context import (  # noqa: E402
    authority_states,
    build_evidence_context_features,
    build_evidence_context_summary,
    contains_any,
    evidence_context_features_dict,
    diagnostics_from_selector_snapshot,
    float_value,
    max_row_signal,
    normalize_text,
    ordinary_fact_lookup,
    resolver_actions,
    retrieval_row_state,
    selected_evidence,
    stale_conflict_present,
)


OUT_JSON = REPO_ROOT / "experiments" / "evidence_context_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_context_regression_report.md"


def build_report() -> dict:
    evidence = [
        {"memory_id": "mem_current", "score": 0.62, "authority_state": "current"},
        {"memory_id": "mem_stale", "score": 0.58, "memory_state": "stale"},
        "not-a-row",
        {"memory_id": "mem_low", "score": "bad"},
    ]
    retrieval_context = evidence + [{"memory_id": "mem_scope", "claim_scope_score": 0.81}]
    selector_snapshot = {
        "diagnostics": {
            "ogcf_intent": "ordinary_fact_lookup",
            "stale_current_conflict": 0.25,
            "contradiction_peak": 0.40,
            "ogcf_bridge_overload_score": 0.35,
            "ogcf_effective_affected_memory_ratio": 0.45,
            "ogcf_structural_pressure": 0.1575,
        }
    }
    resolver_shadow = {"actions": ["emit_ogcf_bridge_warning", "", None, "disclose_stale_conflict"]}
    summary = build_evidence_context_summary(
        query="When is the bridge meeting?",
        answer="Answer text",
        evidence=evidence,
        stale_context=[{"memory_id": "mem_old"}],
        retrieval_context=retrieval_context,
        selector_snapshot=selector_snapshot,
        resolver_shadow=resolver_shadow,
        conflict=True,
    )
    feature_summary = build_evidence_context_features(summary, fallback_features={"memory_bad_rate": 0.27})
    feature_dict = evidence_context_features_dict(feature_summary)
    stale_state = retrieval_row_state(
        {
            "authority_state": "standalone",
            "score": 0.72,
            "cosine": 0.66,
            "text_match_score": 0.44,
            "claim_scope_score": 0.52,
            "answer_type_score": 0.33,
            "intent_match_score": -0.25,
            "feedback_score": 0.40,
            "summary_relation_score": 0.30,
            "correction_relevance_score": 0.60,
            "supersession_score": -0.20,
        }
    )
    current_state = retrieval_row_state(
        {
            "authority_state": "current",
            "cosine": 0.63,
            "text_match_score": 0.31,
            "supersedes_memory_ids": ["mem_old"],
        }
    )
    standalone_state = retrieval_row_state(
        {
            "authority_state": "unknown",
            "cosine": 0.51,
            "text_match_score": 0.37,
        }
    )
    checks = {
        "normalize_text": normalize_text("  What   IS  This?  ") == "what is this?",
        "selected_evidence_filters_rows": len(selected_evidence(evidence)) == 3,
        "resolver_actions_filters_blank": resolver_actions(resolver_shadow)
        == {"emit_ogcf_bridge_warning", "disclose_stale_conflict"},
        "contains_any": contains_any("Bridge geometry query", ("bridge", "calendar")),
        "float_default": float_value("bad", 0.25) == 0.25,
        "max_row_signal": max_row_signal(selected_evidence(evidence), "score") == 0.62,
        "diagnostics_from_snapshot": diagnostics_from_selector_snapshot(selector_snapshot).get("ogcf_intent")
        == "ordinary_fact_lookup",
        "ordinary_from_selector_snapshot": ordinary_fact_lookup("Tell me anything", selector_snapshot=selector_snapshot),
        "ordinary_from_resolver_shadow": ordinary_fact_lookup(
            "Tell me anything",
            resolver_shadow={"diagnostics": {"ordinary_fact_lookup": True}},
        ),
        "authority_states": authority_states(evidence) == {"current", "stale", ""},
        "stale_conflict_from_states": stale_conflict_present(evidence=evidence),
        "stale_conflict_from_diagnostics": stale_conflict_present(
            evidence=[],
            diagnostics={"stale_current_conflict": 1.0},
        ),
        "stale_conflict_from_conflict_context": stale_conflict_present(
            evidence=[],
            stale_context=[{"memory_id": "mem_old"}],
            conflict=True,
        ),
        "stale_conflict_negative": not stale_conflict_present(evidence=[{"memory_state": "current"}]),
        "summary_selected_count": summary.selected_count == 3,
        "summary_stale_context_count": summary.stale_context_count == 1,
        "summary_query_text": summary.query_text == "when is the bridge meeting?",
        "summary_answer_text": summary.answer_text == "answer text",
        "summary_actions": summary.resolver_actions == {"emit_ogcf_bridge_warning", "disclose_stale_conflict"},
        "summary_ordinary_lookup": summary.ordinary_fact_lookup is True,
        "summary_stale_conflict": summary.stale_conflict_present is True,
        "summary_max_selected_signal": summary.max_selected_signal("score") == 0.62,
        "summary_max_retrieval_signal": summary.max_retrieval_signal("claim_scope_score") == 0.81,
        "summary_contains_query_term": summary.contains_query_term(("bridge", "calendar")) is True,
        "feature_summary_counts": feature_summary.retrieval_count == 4
        and feature_summary.selected_count == 3
        and feature_summary.stale_context_count == 1,
        "feature_summary_retrieval_signals": feature_summary.top_score == 0.62
        and feature_summary.claim_scope_score == 0.81,
        "feature_summary_selected_signals": feature_summary.selected_top_score == 0.62,
        "feature_summary_diagnostics": feature_summary.memory_bad_rate == 0.27
        and feature_summary.stale_current_conflict == 0.25
        and feature_summary.contradiction_peak == 0.40,
        "feature_summary_ogcf": feature_summary.ogcf_bridge_overload_score == 0.35
        and feature_summary.ogcf_effective_affected_memory_ratio == 0.45
        and feature_summary.ogcf_structural_pressure == 0.1575,
        "feature_summary_export_dict": feature_dict.get("retrieval_count") == 4
        and feature_dict.get("memory_bad_rate") == 0.27
        and "selected_claim_scope_score" in feature_dict,
        "row_state_stale_by_supersession": stale_state.is_stale is True and stale_state.is_current is False,
        "row_state_score_prefers_score": stale_state.score == 0.72,
        "row_state_current_by_authority": current_state.is_current is True and current_state.explicit_current is True,
        "row_state_score_falls_back_to_cosine": current_state.score == 0.63,
        "row_state_standalone": standalone_state.is_standalone is True and standalone_state.is_topical_anchor is True,
        "row_state_claim_scope_fallback": standalone_state.claim_scope_score == 0.37,
        "row_state_answer_type": stale_state.answer_type_score == 0.33,
        "row_state_intent_match": stale_state.intent_match_score == -0.25,
        "row_state_feedback": stale_state.feedback_score == 0.40,
        "row_state_summary_relation": stale_state.summary_relation_score == 0.30,
        "row_state_correction_relevance": stale_state.correction_relevance_score == 0.60,
    }
    return {
        "schema": "evidence_context_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Evidence Context Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
