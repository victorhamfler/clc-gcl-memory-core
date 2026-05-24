from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.outcome_log import OutcomeLogger  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.runtime import init_db  # noqa: E402
from serve import FEEDBACK_RATINGS, MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_workflow_results.json"
OUT_MD = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_workflow_report.md"
LOG_COPY = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_workflow.jsonl"
HOLDOUT_JSON = REPO_ROOT / "experiments" / "neural_symbolic_holdout_candidates.json"
HOLDOUT_MD = REPO_ROOT / "experiments" / "neural_symbolic_holdout_candidates.md"


FIXTURES = {
    "routine_preference": {
        "text": "Hermes day-one memory: Victor wants answers to cite evidence ids and say when support is weak.",
        "source": "neural_symbolic/day1_preference.md",
    },
    "bridge_weather": {
        "text": "Hermes bridge memory: weather uncertainty and selector refresh evidence can interact across project clusters.",
        "source": "neural_symbolic/bridge_weather_selector.md",
    },
    "bridge_geometry": {
        "text": "Hermes geometry memory: loop pressure can overload bridge-heavy memory paths during cross-domain retrieval.",
        "source": "neural_symbolic/bridge_geometry_loop.md",
    },
    "canonical_policy": {
        "text": "Hermes canonical memory: prefer current project policy over stale duplicated notes when both appear.",
        "source": "neural_symbolic/canonical_policy.md",
    },
}


CASES = [
    {
        "id": "ordinary_supported_answer",
        "query": "What does Victor want Hermes answers to cite?",
        "label": "answer_correct",
        "expected_behavior": "supported_answer_with_evidence_ids",
        "ogcf": False,
    },
    {
        "id": "bridge_risk_answer",
        "query": "How can weather uncertainty interact with selector refresh evidence across clusters?",
        "label": "answer_bridge_warning_useful",
        "expected_behavior": "bridge_risk_disclosed_with_support",
        "ogcf": True,
    },
    {
        "id": "unsupported_query_answer",
        "query": "What private launch code should Hermes use for Victor?",
        "label": "answer_missing_support",
        "expected_behavior": "refuse_or_mark_insufficient_support",
        "ogcf": False,
    },
]


def build_test_api(tmp: Path) -> MemoryApi:
    db_path = tmp / "neural_symbolic_holdout.db"
    init_db(ROOT, db_path)
    config = load_config(ROOT)
    api = object.__new__(MemoryApi)
    api.root = ROOT
    api.root_config = config
    api.pipeline = MemoryPipeline(
        ROOT,
        db_path,
        embedding_dim=128,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=config.get("retrieval_weights"),
        symbolic_config=config.get("symbolic"),
        claim_scope_config=config.get("claim_scope"),
        answer_type_config=config.get("answer_type"),
        retrieval_signal_config=config.get("retrieval_signals"),
        evidence_state_config=config.get("evidence_states"),
        canonical_memory_config=config.get("canonical_memory"),
        llm_config=config.get("llm"),
        clc_thresholds=config.get("thresholds"),
    )
    api.outcome_logger = OutcomeLogger(
        ROOT,
        {
            "outcome_log": {
                "enabled": True,
                "path": str(tmp / "neural_symbolic_outcomes.jsonl"),
                "max_text_chars": 1000,
                "max_list_items": 50,
            }
        },
    )
    return api


def bridge_meta(memory_ids: list[str]) -> dict[str, Any]:
    memory_cluster_map = {memory_id: 15 for memory_id in memory_ids}
    return {
        "bridge_overload_score": 0.94,
        "max_interaction_z": 2.82,
        "loop_count": 9,
        "risk_region_count": 2,
        "cluster_count": 2,
        "affected_memory_ratio": 0.86,
        "weighted_affected_memory_ratio": 0.91,
        "effective_affected_memory_ratio": 0.88,
        "risk_regions": [
            {
                "clusters": "15-31",
                "memory_ids": memory_ids[:2],
                "interaction_z": 2.82,
                "loop_count": 6,
            },
            {
                "clusters": "15",
                "memory_ids": memory_ids[1:],
                "interaction_z": 2.31,
                "loop_count": 3,
            },
        ],
        "bridge_clusters": [
            {"cluster_id": 15, "size": len(memory_ids), "unique_domains": 3, "pressure": 0.91},
        ],
        "cluster_summary": [{"cluster_id": 15, "size": len(memory_ids), "local_defect": 0.08}],
        "memory_cluster_map": memory_cluster_map,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_holdout_markdown(candidates: list[dict[str, Any]]) -> None:
    lines = [
        "# Neural-Symbolic Holdout Candidates",
        "",
        "Schema: `memory_neural_symbolic_holdout/v1`.",
        "",
    ]
    for item in candidates:
        lines.extend(
            [
                f"## {item['id']}",
                "",
                f"- Query: {item['query']}",
                f"- Expected behavior: {item['expected_behavior']}",
                f"- Feedback label: `{item['feedback_label']}`",
                f"- Linked operation: `{item['linked_operation_id']}`",
                f"- OGCF metadata present: `{item['ogcf_meta_present']}`",
                f"- Selected memories: {', '.join(item['selected_memory_ids']) or 'none'}",
                "",
            ]
        )
    HOLDOUT_MD.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any]) -> None:
    lines = [
        "# Neural-Symbolic Outcome Holdout Workflow",
        "",
        f"- Overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- Ask events: {report['counts']['ask_events']}",
        f"- Feedback events: {report['counts']['feedback_events']}",
        f"- Answer-level feedback events: {report['counts']['answer_level_feedback_events']}",
        f"- Memory-level feedback events: {report['counts']['memory_level_feedback_events']}",
        f"- Holdout candidates: {report['counts']['holdout_candidates']}",
        f"- OGCF bridge diagnostics non-empty: {report['checks']['bridge_case_has_non_empty_ogcf_diagnostics']}",
        f"- Answer feedback DB mutation avoided: {report['checks']['answer_feedback_did_not_add_retrieval_rows']}",
        "",
        "## Checks",
        "",
    ]
    for key, value in report["checks"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Artifacts", ""])
    for key, value in report["artifacts"].items():
        lines.append(f"- {key}: `{value}`")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="neural_symbolic_holdout_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught_by_ref: dict[str, dict[str, Any]] = {}
            namespace = "agent:neural-symbolic-holdout"
            for ref, fixture in FIXTURES.items():
                taught_by_ref[ref] = api.teach(
                    {
                        "text": fixture["text"],
                        "namespace": namespace,
                        "agent_id": "neural-symbolic-holdout-agent",
                        "source": fixture["source"],
                        "memory_type": "semantic_note",
                    }
                )

            taught_memory_ids = [item["memory"]["memory_id"] for item in taught_by_ref.values()]
            initial_feedback_count = len(api.pipeline.db.recent_feedback(limit=100))
            holdout_candidates: list[dict[str, Any]] = []
            case_results: list[dict[str, Any]] = []

            for case in CASES:
                ask_payload = {
                    "query": case["query"],
                    "namespace": namespace,
                    "include_global": False,
                    "agent_id": "neural-symbolic-holdout-agent",
                    "top_k": 8,
                    "store_session": False,
                    "include_selector_snapshot": True,
                }
                if case["ogcf"]:
                    ask_payload["ogcf_meta"] = bridge_meta(taught_memory_ids)
                asked = api.ask(ask_payload)
                selected_memory_ids = [row["memory_id"] for row in asked.get("evidence") or [] if row.get("memory_id")]
                feedback = api.feedback(
                    {
                        "feedback_scope": "answer",
                        "label": case["label"],
                        "query": case["query"],
                        "operation_id": asked["operation_id"],
                        "answer": asked.get("answer"),
                        "answer_summary": str(asked.get("answer") or "")[:240],
                        "selected_memory_ids": selected_memory_ids,
                        "notes": f"neural-symbolic holdout workflow: {case['id']}",
                    }
                )
                case_results.append(
                    {
                        "id": case["id"],
                        "ask_operation_id": asked.get("operation_id"),
                        "feedback_operation_id": feedback.get("operation_id"),
                        "linked_operation_id": feedback.get("linked_operation_id"),
                        "feedback_label": case["label"],
                        "feedback_rating": feedback["feedback"]["rating"],
                        "expected_rating": FEEDBACK_RATINGS[case["label"]],
                        "feedback_scope": feedback["feedback"].get("feedback_scope"),
                        "selector_snapshot": asked.get("selector_snapshot"),
                    }
                )
                holdout_candidates.append(
                    {
                        "schema": "memory_neural_symbolic_holdout/v1",
                        "id": case["id"],
                        "query": case["query"],
                        "expected_behavior": case["expected_behavior"],
                        "feedback_label": case["label"],
                        "feedback_rating": feedback["feedback"]["rating"],
                        "linked_operation_id": asked["operation_id"],
                        "feedback_operation_id": feedback["operation_id"],
                        "selected_memory_ids": selected_memory_ids,
                        "ogcf_meta_present": bool(case["ogcf"]),
                        "answer_preview": str(asked.get("answer") or "")[:500],
                        "reason": "held out for answer-level label and selector-diagnostic learning",
                    }
                )

            bridge_row = next(item for item in case_results if item["id"] == "bridge_risk_answer")
            diagnostics = ((bridge_row.get("selector_snapshot") or {}).get("diagnostics") or {})

            # Existing memory-level feedback path still works and remains the only DB feedback mutation here.
            memory_feedback = api.feedback(
                {
                    "memory_id": taught_by_ref["bridge_geometry"]["memory"]["memory_id"],
                    "label": "ogcf_geometry",
                    "query": "Does bridge geometry show loop pressure?",
                    "operation_id": case_results[1]["ask_operation_id"],
                    "rank": 1,
                    "retrieval_score": None,
                    "notes": "memory-level OGCF label retained for compatibility",
                }
            )

            final_feedback_count = len(api.pipeline.db.recent_feedback(limit=100))
            log_path = api.outcome_logger.path
        finally:
            api.close()

        rows = read_jsonl(log_path)
        LOG_COPY.parent.mkdir(parents=True, exist_ok=True)
        LOG_COPY.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
        write_json(HOLDOUT_JSON, holdout_candidates)
        write_holdout_markdown(holdout_candidates)

        feedback_events = [row for row in rows if row.get("event_type") == "feedback"]
        answer_feedback_events = [
            row
            for row in feedback_events
            if ((row.get("payload") or {}).get("feedback") or {}).get("feedback_scope") == "answer"
        ]
        memory_feedback_events = [
            row
            for row in feedback_events
            if ((row.get("payload") or {}).get("feedback") or {}).get("feedback_scope") == "memory"
        ]
        checks = {
            "all_cases_linked": all(item["linked_operation_id"] == item["ask_operation_id"] for item in case_results),
            "answer_labels_have_expected_ratings": all(
                float(item["feedback_rating"]) == float(item["expected_rating"]) for item in case_results
            ),
            "answer_feedback_logged_as_answer_scope": len(answer_feedback_events) == len(CASES),
            "memory_feedback_logged_as_memory_scope": len(memory_feedback_events) == 1,
            "answer_feedback_did_not_add_retrieval_rows": final_feedback_count - initial_feedback_count == 1,
            "bridge_case_has_non_empty_ogcf_diagnostics": bool(
                diagnostics.get("ogcf_bridge_overload_score")
                and diagnostics.get("ogcf_effective_affected_memory_ratio")
                and diagnostics.get("ogcf_cluster_count")
            ),
            "holdout_artifact_written": HOLDOUT_JSON.exists() and HOLDOUT_MD.exists(),
            "log_copy_written": LOG_COPY.exists(),
            "memory_feedback_linked": memory_feedback.get("linked_operation_id") == case_results[1]["ask_operation_id"],
        }
        report = {
            "ok": all(checks.values()),
            "checks": checks,
            "counts": {
                "ask_events": len([row for row in rows if row.get("event_type") == "ask"]),
                "feedback_events": len(feedback_events),
                "answer_level_feedback_events": len(answer_feedback_events),
                "memory_level_feedback_events": len(memory_feedback_events),
                "holdout_candidates": len(holdout_candidates),
            },
            "case_results": case_results,
            "bridge_ogcf_diagnostics_sample": {
                key: diagnostics.get(key)
                for key in (
                    "ogcf_bridge_overload_score",
                    "ogcf_max_interaction_z",
                    "ogcf_loop_count",
                    "ogcf_cluster_count",
                    "ogcf_effective_affected_memory_ratio",
                )
            },
            "artifacts": {
                "results_json": str(OUT_JSON),
                "report_md": str(OUT_MD),
                "log_copy": str(LOG_COPY),
                "holdout_json": str(HOLDOUT_JSON),
                "holdout_md": str(HOLDOUT_MD),
            },
        }
        write_json(OUT_JSON, report)
        write_report(report)
        print(json.dumps(report, indent=2), flush=True)
        return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
