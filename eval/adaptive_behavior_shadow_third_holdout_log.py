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
RUN_DB = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_test.db"
OUTCOME_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_report.md"
CALIBRATION_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_calibration_results.json"
CALIBRATION_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_calibration_report.md"

NAMESPACE = "global"
AGENT_ID = "adaptive-behavior-third-holdout"


QUERIES = [
    {"query": "What memory evidence supports Hermes citation behavior?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "How should the system describe Victor's preferred answer format?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What does the memory architecture use CSD for?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "Which rule currently governs selector refresh decisions?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What robust-retrieval design rule should be followed now?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "Which approved operations should the assistant remember?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is Victor's unlogged recovery phrase?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "Which private deployment password should be reused?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What secret hostname was never stored?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What personal identity number should Hermes reveal?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What previous project rule is still valid?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What was the old selector behavior before the update?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What corrected project rule replaced the previous one?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "What is the latest verified selector update?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "Does a meeting approval prove repository upload permission?", "family": "wrong_scope", "feedback": "answer_wrong_scope"},
    {"query": "Who approved the calendar edit as if it were GitHub publishing?", "family": "wrong_scope", "feedback": "answer_wrong_scope"},
    {"query": "What approval rule applies to repository uploads?", "family": "wrong_scope", "feedback": "answer_correct"},
    {"query": "How should OGCF geometry warnings interact with answer support?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "When should cross-domain memory synthesis mention bridge risk?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "How should uncertainty signals affect memory refresh?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "Where is the office bridge room?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "What does bridge mean in the conference logistics note?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Can ordinary profile retrieval use namespace crossing?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Where did the bridge call happen?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
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
            "notes": f"Third holdout scenario family: {query_case['family']}",
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
                "notes": f"Third holdout family: {query_case['family']}, rank {rank}",
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
    OUT_MD.write_text(
        "# Adaptive Behavior Shadow Third Holdout Log\n\n"
        + f"Passed: **{summary['ok']}**\n"
        + f"Ask count: `{summary['ask_count']}`\n"
        + f"Answer feedback count: `{summary['answer_feedback_count']}`\n"
        + f"Memory feedback count: `{summary['memory_feedback_count']}`\n"
        + f"Outcome log: `{summary['outcome_log']}`\n\n"
        + "## Advisory Counts\n\n```json\n"
        + json.dumps(summary["advisory_counts"], indent=2)
        + "\n```\n\n"
        + "## Behavior Family Counts\n\n```json\n"
        + json.dumps(summary["behavior_family_counts"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


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
        "schema": "adaptive_behavior_shadow_third_holdout_log/v1",
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
