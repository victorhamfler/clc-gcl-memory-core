from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.outcome_log import OutcomeLogger  # noqa: E402
from eval.adaptive_behavior_shadow_real_log_calibration import build_report, write_report  # noqa: E402
from serve import MemoryApi  # noqa: E402


SOURCE_DB = ROOT / "memory_experiment_180_best.db"
RUN_DB = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_test.db"
OUTCOME_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_report.md"
CALIBRATION_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_calibration_results.json"
CALIBRATION_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_calibration_report.md"

NAMESPACE = "global"
AGENT_ID = "adaptive-behavior-local-rerun"


QUERIES = [
    {"query": "What should Hermes cite in answers?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "How does Victor prefer answers?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is the CSD score used for?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What method should be used for weather radar?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What does Victor prefer to drink?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "How does the selector decide which memory to retrieve?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is the combined mechanism for text input?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is the engineering design for robustness?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What mistake should be avoided with CSD?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is the approved operation list?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is Victor's favorite color?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is the database password?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "How old is Victor?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is the server hostname?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is Victor's shoe size?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is the API key?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is the private launch code?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "Where does Victor live?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What is the old project policy?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What was the previous backend port?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What is the current project policy after the correction?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "What is the updated selector behavior?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "Who approves GitHub uploads?", "family": "wrong_scope", "feedback": "answer_wrong_scope"},
    {"query": "What requires Victor's sign-off?", "family": "wrong_scope", "feedback": "answer_correct"},
    {"query": "Does calendar approval need Victor?", "family": "wrong_scope", "feedback": "answer_correct"},
    {"query": "Is GitHub approval automatic?", "family": "wrong_scope", "feedback": "answer_correct"},
    {"query": "How does weather uncertainty interact with memory refresh?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "Should cross-domain use verified refresh?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "What should cross-domain synthesis use?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "What is the calendar location named Bridge Room?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "What does the memory bridge do?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Can lookups cross namespaces?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Where is the conference room?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "What is the bridge between modules?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
]


def prepare_run_db() -> None:
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f"Missing source DB: {SOURCE_DB}")
    RUN_DB.parent.mkdir(parents=True, exist_ok=True)
    if RUN_DB.exists():
        RUN_DB.unlink()
    shutil.copy2(SOURCE_DB, RUN_DB)


def configure_outcome_log(api: MemoryApi) -> None:
    if OUTCOME_LOG.exists():
        OUTCOME_LOG.unlink()
    api.outcome_logger = OutcomeLogger(
        ROOT,
        {
            "outcome_log": {
                "enabled": True,
                "path": str(OUTCOME_LOG),
                "max_text_chars": 900,
                "max_list_items": 16,
            }
        },
    )


def evidence_ids(answer: dict[str, Any]) -> list[str]:
    evidence = answer.get("evidence") if isinstance(answer.get("evidence"), list) else []
    return [str(item.get("memory_id")) for item in evidence if isinstance(item, dict) and item.get("memory_id")]


def shadow_counts(answer: dict[str, Any]) -> tuple[Counter[str], Counter[str], list[str]]:
    advisory_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    mutation_flags = []
    shadow = answer.get("adaptive_behavior_shadow") if isinstance(answer.get("adaptive_behavior_shadow"), dict) else {}
    for key in ("mutates_answer", "mutates_selector_policy", "mutates_memory", "mutates_config"):
        if shadow.get(key) is not False:
            mutation_flags.append(key)
    for decision in shadow.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        advisory_counts[str(decision.get("advisory") or "unknown")] += 1
        family_counts[str(decision.get("behavior_family") or "unknown")] += 1
    return advisory_counts, family_counts, mutation_flags


def run_cycle(api: MemoryApi, query_case: dict[str, str]) -> dict[str, Any]:
    answer = api.ask(
        {
            "query": query_case["query"],
            "top_k": 8,
            "namespace": NAMESPACE,
            "include_global": True,
            "agent_id": AGENT_ID,
            "include_selector_snapshot": True,
            "include_resolver_shadow": True,
            "include_adaptive_behavior_shadow": True,
            "log_adaptive_behavior_shadow": True,
        }
    )
    op_id = str(answer.get("operation_id") or "")
    ids = evidence_ids(answer)
    answer_feedback = api.feedback(
        {
            "operation_id": op_id,
            "feedback_scope": "answer",
            "label": query_case["feedback"],
            "selected_memory_ids": ids,
            "query": query_case["query"],
            "notes": f"Local rerun scenario family: {query_case['family']}",
        }
    )
    memory_feedback_count = 0
    memory_label = "useful" if query_case["feedback"] == "answer_correct" else query_case["feedback"]
    for rank, item in enumerate(answer.get("evidence") or [], start=1):
        if not isinstance(item, dict) or not item.get("memory_id"):
            continue
        api.feedback(
            {
                "operation_id": op_id,
                "memory_id": item.get("memory_id"),
                "label": memory_label,
                "query": query_case["query"],
                "rank": rank,
                "retrieval_score": item.get("score"),
                "notes": f"Local rerun family: {query_case['family']}, rank {rank}",
            }
        )
        memory_feedback_count += 1
    advisories, families, mutations = shadow_counts(answer)
    return {
        "query": query_case["query"],
        "family": query_case["family"],
        "label": query_case["feedback"],
        "operation_id": op_id,
        "answer_feedback_operation_id": answer_feedback.get("operation_id"),
        "evidence_count": len(ids),
        "advisory_counts": dict(advisories),
        "behavior_family_counts": dict(families),
        "mutation_flags": mutations,
        "memory_feedback_count": memory_feedback_count,
    }


def write_run_report(summary: dict[str, Any]) -> None:
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Shadow Local Real-Log Rerun",
        "",
        f"Passed: **{summary['ok']}**",
        f"Ask count: `{summary['ask_count']}`",
        f"Answer feedback count: `{summary['answer_feedback_count']}`",
        f"Memory feedback count: `{summary['memory_feedback_count']}`",
        f"Outcome log: `{summary['outcome_log']}`",
        "",
        "## Advisory Counts",
        "",
        "```json",
        json.dumps(summary["advisory_counts"], indent=2),
        "```",
        "",
        "## Behavior Family Counts",
        "",
        "```json",
        json.dumps(summary["behavior_family_counts"], indent=2),
        "```",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    prepare_run_db()
    api = MemoryApi(ROOT, db_path=RUN_DB)
    configure_outcome_log(api)
    results = []
    try:
        for query_case in QUERIES:
            results.append(run_cycle(api, query_case))
    finally:
        api.close()

    advisory_counts: Counter[str] = Counter()
    behavior_counts: Counter[str] = Counter()
    mutation_flags: list[dict[str, Any]] = []
    for row in results:
        advisory_counts.update(row["advisory_counts"])
        behavior_counts.update(row["behavior_family_counts"])
        if row["mutation_flags"]:
            mutation_flags.append({"operation_id": row["operation_id"], "flags": row["mutation_flags"]})

    calibration = build_report(OUTCOME_LOG)
    write_report(calibration, CALIBRATION_JSON, CALIBRATION_MD)
    summary = {
        "schema": "adaptive_behavior_shadow_local_real_log_rerun/v1",
        "ok": bool(results) and not mutation_flags and calibration.get("ok") is True,
        "source_db": str(SOURCE_DB),
        "run_db": str(RUN_DB),
        "outcome_log": str(OUTCOME_LOG),
        "ask_count": len(results),
        "answer_feedback_count": len(results),
        "memory_feedback_count": sum(int(row["memory_feedback_count"]) for row in results),
        "advisory_counts": dict(advisory_counts.most_common()),
        "behavior_family_counts": dict(behavior_counts.most_common()),
        "mutation_flags": mutation_flags,
        "calibration": {
            "json": str(CALIBRATION_JSON),
            "markdown": str(CALIBRATION_MD),
            "improvement": calibration.get("improvement"),
            "logged_match_rate": calibration.get("logged_runtime_shadow", {}).get("overall_match_rate"),
        },
        "results": results,
    }
    write_run_report(summary)
    print(json.dumps({"ok": summary["ok"], "summary": str(OUT_JSON), "calibration": summary["calibration"]}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
