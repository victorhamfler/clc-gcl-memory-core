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
from serve import MemoryApi  # noqa: E402


SOURCE_DB = ROOT / "memory_experiment_180_best.db"
RUN_DB = REPO_ROOT / "experiments" / "adaptive_residual_shadow_fourth_holdout_test.db"
OUTCOME_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_fourth_holdout_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_fourth_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_fourth_holdout_report.md"

NAMESPACE = "global"
AGENT_ID = "adaptive-residual-fourth-holdout"


QUERIES = [
    {"query": "Which selected evidence should be cited for Hermes answer policy?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What current evidence explains the selector memory policy?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "How should CSD evidence be used in the architecture?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What current robust retrieval rule should the system follow?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "Which current approved operations should be remembered?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "How should canonical memory affect supported answers?", "family": "supported_evidence", "feedback": "answer_correct"},
    {"query": "What is Victor's private recovery phrase?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "Which unrecorded token authorizes deployment?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What secret password should be reused?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What hidden server hostname should be cited?", "family": "missing_support", "feedback": "answer_missing_support"},
    {"query": "What old project rule should still be followed?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What previous backend policy remains active?", "family": "stale_conflict", "feedback": "answer_stale"},
    {"query": "What corrected policy replaced the old backend rule?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "What is the latest current selector correction?", "family": "stale_current", "feedback": "answer_correct"},
    {"query": "Does meeting permission imply GitHub publishing approval?", "family": "wrong_scope", "feedback": "answer_wrong_scope"},
    {"query": "Who approved calendar changes as repository uploads?", "family": "wrong_scope", "feedback": "answer_wrong_scope"},
    {"query": "What approval is needed for GitHub upload?", "family": "wrong_scope", "feedback": "answer_correct"},
    {"query": "When should OGCF bridge geometry warn during synthesis?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "How should cross-domain memory synthesis handle bridge risk?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "How should uncertainty affect verified memory refresh?", "family": "bridge_useful", "feedback": "answer_bridge_warning_useful"},
    {"query": "Where is the bridge room in the calendar?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "What does bridge mean in ordinary meeting logistics?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Can ordinary profile lookup cross namespaces?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
    {"query": "Where is the conference bridge scheduled?", "family": "bridge_noise", "feedback": "answer_bridge_warning_noise"},
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


def residual_counts(answer: dict[str, Any]) -> tuple[Counter[str], list[str]]:
    counts: Counter[str] = Counter()
    mutation_flags = []
    shadow = answer.get("adaptive_residual_shadow") if isinstance(answer.get("adaptive_residual_shadow"), dict) else {}
    for key in ("mutates_answer", "mutates_selector_policy", "mutates_memory", "mutates_config"):
        if shadow.get(key) is not False:
            mutation_flags.append(key)
    for decision in shadow.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        counts["would_override" if decision.get("would_override") else "symbolic_or_suppressed"] += 1
        if decision.get("suppression_reasons"):
            counts["suppressed_reasons"] += 1
    return counts, mutation_flags


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
            "include_adaptive_residual_shadow": True,
            "log_adaptive_residual_shadow": True,
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
            "notes": f"Fourth residual holdout scenario family: {query_case['family']}",
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
                "notes": f"Fourth residual holdout family: {query_case['family']}, rank {rank}",
            }
        )
        memory_feedback_count += 1
    counts, mutations = residual_counts(answer)
    return {
        "query": query_case["query"],
        "family": query_case["family"],
        "label": query_case["feedback"],
        "operation_id": op_id,
        "answer_feedback_operation_id": answer_feedback.get("operation_id"),
        "evidence_count": len(ids),
        "residual_counts": dict(counts),
        "mutation_flags": mutations,
        "memory_feedback_count": memory_feedback_count,
    }


def write_run_report(summary: dict[str, Any]) -> None:
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Fourth Holdout Log\n\n"
        + f"Passed: **{summary['ok']}**\n"
        + f"Ask count: `{summary['ask_count']}`\n"
        + f"Answer feedback count: `{summary['answer_feedback_count']}`\n"
        + f"Memory feedback count: `{summary['memory_feedback_count']}`\n"
        + f"Outcome log: `{summary['outcome_log']}`\n\n"
        + "## Residual Counts\n\n```json\n"
        + json.dumps(summary["residual_counts"], indent=2)
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

    residual_counter: Counter[str] = Counter()
    mutation_flags = []
    for row in results:
        residual_counter.update(row["residual_counts"])
        if row["mutation_flags"]:
            mutation_flags.append({"operation_id": row["operation_id"], "flags": row["mutation_flags"]})
    summary = {
        "schema": "adaptive_residual_shadow_fourth_holdout_log/v1",
        "ok": bool(results) and not mutation_flags,
        "source_db": str(SOURCE_DB),
        "run_db": str(RUN_DB),
        "outcome_log": str(OUTCOME_LOG),
        "ask_count": len(results),
        "answer_feedback_count": len(results),
        "memory_feedback_count": sum(int(row["memory_feedback_count"]) for row in results),
        "residual_counts": dict(residual_counter.most_common()),
        "mutation_flags": mutation_flags,
        "results": results,
    }
    write_run_report(summary)
    print(json.dumps({"ok": summary["ok"], "summary": str(OUT_JSON), "outcome_log": str(OUTCOME_LOG)}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
