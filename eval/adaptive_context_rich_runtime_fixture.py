from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_dataset_guard import build_report as build_guard_report
from eval.adaptive_context_dataset_guard import write_report as write_guard_report
from eval.adaptive_context_outcome_dataset import build_report as build_dataset_report
from eval.adaptive_context_outcome_dataset import write_report as write_dataset_report
from eval.outcome_logging_regression import build_test_api


OUT_LOG = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_examples.jsonl"
OUT_DATASET_JSON = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
OUT_DATASET_MD = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_report.md"
OUT_GUARD_JSON = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_guard_results.json"
OUT_GUARD_MD = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_guard_report.md"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_fixture_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_fixture_report.md"


NAMESPACE = "agent:adaptive-context-rich-runtime"
AGENT_ID = "adaptive-context-rich-runtime-agent"


SCENARIOS = [
    {
        "name": "supported_grounding",
        "memories": [
            "Adaptive runtime supported grounding: Victor wants memory answers grounded in selected evidence ids.",
            "Adaptive runtime citation rule: supported answers should cite the selected memory evidence when possible.",
        ],
        "query": "What does Victor want for memory answers?",
        "answer_label": "answer_correct",
        "memory_label": "useful",
        "notes": "Positive supported-answer evidence grounding.",
    },
    {
        "name": "good_citation",
        "memories": [
            "Adaptive runtime citation quality: answers should not invent citations and should use retrieved evidence ids.",
            "Adaptive runtime evidence note: selected memory rows are the trusted source for grounded answers.",
        ],
        "query": "How should the system handle citations in grounded answers?",
        "answer_label": "answer_good_citation",
        "memory_label": "good",
        "notes": "Positive answer citation behavior.",
    },
    {
        "name": "missing_support",
        "memories": [
            "Adaptive runtime unrelated deployment note: the dashboard prefers a blue status color.",
            "Adaptive runtime unrelated lunch note: pizza orders should be counted before noon.",
        ],
        "query": "What exact hardware budget did Victor approve for the unlisted robotics test?",
        "answer_label": "answer_missing_support",
        "memory_label": "wrong_domain",
        "notes": "Negative missing-support case with retrieved but wrong-domain evidence.",
    },
    {
        "name": "bridge_warning_useful",
        "memories": [
            "Adaptive runtime OGCF bridge: selector refresh evidence and weather-risk evidence can form a cross-domain bridge.",
            "Adaptive runtime OGCF geometry: bridge overload appears when two clusters both affect the same answer plan.",
        ],
        "query": "Explain the bridge geometry between selector refresh evidence and weather-risk evidence.",
        "answer_label": "answer_bridge_warning_useful",
        "memory_label": "bridge_relevant",
        "ogcf": True,
        "notes": "Positive OGCF bridge-warning case.",
    },
    {
        "name": "bridge_warning_noise",
        "memories": [
            "Adaptive runtime ordinary fact: Bridge Room is the meeting location for Tuesday review.",
            "Adaptive runtime ordinary schedule: Tuesday review starts after lunch in Bridge Room.",
        ],
        "query": "Where is the Tuesday review meeting located?",
        "answer_label": "answer_bridge_warning_noise",
        "memory_label": "ogcf_false_positive",
        "ogcf": True,
        "ordinary": True,
        "notes": "Negative ordinary-lookup bridge-word suppression case.",
    },
    {
        "name": "stale_answer",
        "memories": [
            "Adaptive runtime stale policy: old bridge-risk answers can be treated like ordinary supported answers.",
            "Adaptive runtime current policy: bridge-risk answers should disclose uncertainty when OGCF pressure is high.",
        ],
        "query": "What is the current policy for bridge-risk answers under OGCF pressure?",
        "answer_label": "answer_stale",
        "memory_label": "stale",
        "notes": "Stale/conflict answer case.",
    },
    {
        "name": "conflict_not_disclosed",
        "memories": [
            "Adaptive runtime conflict note A: resolver calibration should use strict bridge thresholds.",
            "Adaptive runtime conflict note B: resolver calibration should use default bridge thresholds until live logs improve.",
        ],
        "query": "Which resolver bridge threshold policy should be used now?",
        "answer_label": "answer_conflict_not_disclosed",
        "memory_label": "stale",
        "notes": "Conflict disclosure negative case.",
    },
    {
        "name": "bad_citation",
        "memories": [
            "Adaptive runtime citation trap: only selected memories should be treated as citations.",
            "Adaptive runtime citation trap extra: unselected memories should not be cited as support.",
        ],
        "query": "What should count as citation support?",
        "answer_label": "answer_bad_citation",
        "memory_label": "useful",
        "notes": "Bad citation negative case.",
    },
]


EXPANSION_PROFILES = [
    {
        "suffix": "plain",
        "query_prefix": "",
        "memory_prefix": "Plain evidence variant",
    },
    {
        "suffix": "audit",
        "query_prefix": "In an audit note, ",
        "memory_prefix": "Audit evidence variant",
    },
    {
        "suffix": "handover",
        "query_prefix": "For a handover summary, ",
        "memory_prefix": "Handover evidence variant",
    },
]


def scenario_namespace(scenario: dict[str, Any]) -> str:
    return f"{NAMESPACE}:{scenario['name']}"


def expanded_scenarios() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for profile in EXPANSION_PROFILES:
            item = dict(scenario)
            item["name"] = f"{scenario['name']}_{profile['suffix']}"
            item["query"] = f"{profile['query_prefix']}{scenario['query']}"
            item["notes"] = f"{scenario['notes']} Variant={profile['suffix']}."
            item["memories"] = [
                f"{profile['memory_prefix']} {index}: {memory}"
                for index, memory in enumerate(scenario["memories"], start=1)
            ]
            scenarios.append(item)
    return scenarios


def teach_scenario(api: Any, scenario: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for index, text in enumerate(scenario["memories"], start=1):
        taught = api.teach(
            {
                "text": text,
                "namespace": scenario_namespace(scenario),
                "agent_id": AGENT_ID,
                "source": f"eval/adaptive_context_rich_runtime_fixture/{scenario['name']}.md",
                "memory_type": "semantic_note",
                "domain_name": "adaptive_context_runtime",
                "metadata": {"scenario": scenario["name"], "fixture_index": index},
            }
        )
        ids.append(str(taught["memory"]["memory_id"]))
    return ids


def ogcf_meta(memory_ids: list[str], *, ordinary: bool = False) -> dict[str, Any]:
    return {
        "bridge_overload_score": 0.86 if not ordinary else 0.72,
        "max_interaction_z": 2.7,
        "loop_count": 5,
        "cluster_summary": [{"cluster_id": 1}, {"cluster_id": 2}],
        "bridge_clusters": [{"cluster_id": 1}],
        "risk_regions": [{"clusters": "1-2", "interaction_z": 2.6}],
        "memory_cluster_map": {memory_id: 1 if index == 0 else 2 for index, memory_id in enumerate(memory_ids)},
    }


def ask_and_feedback(api: Any, scenario: dict[str, Any], memory_ids: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": scenario["query"],
        "namespace": scenario_namespace(scenario),
        "include_global": False,
        "agent_id": AGENT_ID,
        "top_k": 5,
        "include_resolver_shadow": True,
        "condition_name": "hard_budget144",
    }
    if scenario.get("ogcf"):
        payload["ogcf_meta"] = ogcf_meta(memory_ids, ordinary=bool(scenario.get("ordinary")))

    asked = api.ask(payload)
    evidence = asked.get("evidence") or []
    selected_ids = [str(row.get("memory_id")) for row in evidence if row.get("memory_id")]
    target_memory_id = selected_ids[0] if selected_ids else memory_ids[0]
    retrieval_score = evidence[0].get("score") if evidence else None

    answer_feedback = api.feedback(
        {
            "feedback_scope": "answer",
            "label": scenario["answer_label"],
            "query": scenario["query"],
            "operation_id": asked["operation_id"],
            "selected_memory_ids": selected_ids,
            "answer": asked.get("answer"),
            "notes": scenario["notes"],
        }
    )
    memory_feedback = api.feedback(
        {
            "memory_id": target_memory_id,
            "label": scenario["memory_label"],
            "query": scenario["query"],
            "operation_id": asked["operation_id"],
            "rank": 1,
            "retrieval_score": retrieval_score,
            "notes": scenario["notes"],
        }
    )
    return {
        "scenario": scenario["name"],
        "ask_operation_id": asked["operation_id"],
        "answer_feedback_operation_id": answer_feedback["operation_id"],
        "memory_feedback_operation_id": memory_feedback["operation_id"],
        "selected_memory_count": len(selected_ids),
        "ogcf": bool(scenario.get("ogcf")),
    }


def write_summary(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Rich Runtime Fixture",
        "",
        "This fixture generates fresh runtime `adaptive_memory_context/v1` examples through the real local API.",
        "",
        f"Passed: **{report['ok']}**",
        f"Generated examples: `{report['dataset'].get('example_count')}`",
        f"Guard readiness: `{report['guard'].get('readiness')}`",
        "",
        "## Counts",
        "",
        "```json",
        json.dumps(
            {
                "contexts": report["dataset"].get("context_source_counts"),
                "scopes": report["dataset"].get("feedback_scope_counts"),
                "families": report["dataset"].get("outcome_family_counts"),
                "guard_checks": report["guard"].get("checks"),
            },
            indent=2,
        ),
        "```",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_context_rich_runtime_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        scenario_runs: list[dict[str, Any]] = []
        try:
            for scenario in expanded_scenarios():
                memory_ids = teach_scenario(api, scenario)
                scenario_runs.append(ask_and_feedback(api, scenario, memory_ids))
            log_path = api.outcome_logger.path
            OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log_path, OUT_LOG)
        finally:
            api.close()

    dataset = build_dataset_report([OUT_LOG])
    write_dataset_report(dataset, OUT_DATASET_JSON, OUT_DATASET_MD)
    guard = build_guard_report(OUT_DATASET_JSON)
    write_guard_report(guard, OUT_GUARD_JSON, OUT_GUARD_MD)

    checks = {
        "dataset_ok": dataset.get("ok") is True,
        "guard_ok": guard.get("ok") is True,
        "promotion_candidate": guard.get("readiness") == "promotion_candidate",
        "all_adaptive_context": dataset.get("context_source_counts") == {"adaptive_memory_context": dataset.get("example_count")},
        "has_answer_feedback": dataset.get("feedback_scope_counts", {}).get("answer", 0) >= 24,
        "has_memory_feedback": dataset.get("feedback_scope_counts", {}).get("memory", 0) >= 24,
        "has_ogcf_family": guard.get("capability_checks", {}).get("has_ogcf_family") is True,
        "no_guard_errors": guard.get("error_count") == 0,
    }
    report = {
        "schema": "adaptive_context_rich_runtime_fixture/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "scenario_runs": scenario_runs,
        "log_path": str(OUT_LOG),
        "dataset_json": str(OUT_DATASET_JSON),
        "dataset_md": str(OUT_DATASET_MD),
        "guard_json": str(OUT_GUARD_JSON),
        "guard_md": str(OUT_GUARD_MD),
        "dataset": {
            "example_count": dataset.get("example_count"),
            "skipped_count": dataset.get("skipped_count"),
            "context_source_counts": dataset.get("context_source_counts"),
            "feedback_scope_counts": dataset.get("feedback_scope_counts"),
            "outcome_family_counts": dataset.get("outcome_family_counts"),
        },
        "guard": {
            "readiness": guard.get("readiness"),
            "error_count": guard.get("error_count"),
            "warning_count": guard.get("warning_count"),
            "checks": guard.get("checks"),
        },
    }
    write_summary(report)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
