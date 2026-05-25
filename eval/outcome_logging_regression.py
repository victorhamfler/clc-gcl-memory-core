from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.outcome_log import OutcomeLogger  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.runtime import init_db  # noqa: E402
from serve import MemoryApi  # noqa: E402


def build_test_api(tmp: Path) -> MemoryApi:
    db_path = tmp / "outcome_logging.db"
    init_db(ROOT, db_path)
    api = object.__new__(MemoryApi)
    api.root = ROOT
    api.root_config = load_config(ROOT)
    api.pipeline = MemoryPipeline(
        ROOT,
        db_path,
        embedding_dim=128,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=api.root_config.get("retrieval_weights"),
        symbolic_config=api.root_config.get("symbolic"),
        claim_scope_config=api.root_config.get("claim_scope"),
        answer_type_config=api.root_config.get("answer_type"),
        retrieval_signal_config=api.root_config.get("retrieval_signals"),
        evidence_state_config=api.root_config.get("evidence_states"),
        llm_config=api.root_config.get("llm"),
        clc_thresholds=api.root_config.get("thresholds"),
    )
    api.outcome_logger = OutcomeLogger(
        ROOT,
        {
            "outcome_log": {
                "enabled": True,
                "path": str(tmp / "memory_outcomes.jsonl"),
                "max_text_chars": 400,
                "max_list_items": 12,
            }
        },
    )
    return api


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="outcome_logging_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught = api.teach(
                {
                    "text": "Outcome logging regression: Victor prefers memory answers with evidence ids.",
                    "namespace": "agent:outcome-logging",
                    "agent_id": "outcome-log-agent",
                    "source": "eval/outcome_logging.md",
                    "memory_type": "preference",
                }
            )
            asked = api.ask(
                {
                    "query": "What does Victor prefer for memory answers?",
                    "namespace": "agent:outcome-logging",
                    "include_global": False,
                    "agent_id": "outcome-log-agent",
                    "top_k": 3,
                }
            )
            explained = api.selector_explain(
                {
                    "query": "What does Victor prefer for memory answers?",
                    "namespace": "agent:outcome-logging",
                    "include_global": False,
                    "condition_name": "standard_budget144",
                    "top_k": 3,
                }
            )
            feedback = api.feedback(
                {
                    "memory_id": taught["memory"]["memory_id"],
                    "label": "useful",
                    "query": "What does Victor prefer for memory answers?",
                    "operation_id": asked["operation_id"],
                    "rank": 1,
                    "retrieval_score": asked["evidence"][0]["score"] if asked["evidence"] else None,
                    "notes": "linked feedback regression",
                }
            )
            log_path = api.outcome_logger.path
        finally:
            api.close()

        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_type = {row["event_type"]: row for row in rows}
        checks = {
            "ask_has_operation_id": bool(asked.get("operation_id")),
            "ask_logged": asked.get("outcome_log_logged") is True,
            "selector_has_operation_id": bool(explained.get("operation_id")),
            "selector_logged": explained.get("outcome_log_logged") is True,
            "feedback_has_operation_id": bool(feedback.get("operation_id")),
            "feedback_logged": feedback.get("outcome_log_logged") is True,
            "three_events_written": [row["event_type"] for row in rows] == ["ask", "selector_explain", "feedback"],
            "ask_selector_snapshot": by_type["ask"]["payload"]["selector_snapshot"]["ok"] is True,
            "ask_adaptive_context_schema": by_type["ask"]["payload"]["adaptive_memory_context"]["schema"] == "adaptive_memory_context/v1",
            "ask_adaptive_context_snapshot_matches": (
                by_type["ask"]["payload"]["adaptive_memory_context"]["selector_snapshot"]["decision"]
                == by_type["ask"]["payload"]["selector_snapshot"]["decision"]
            ),
            "ask_adaptive_context_has_features": bool(by_type["ask"]["payload"]["adaptive_memory_context"]["features"]),
            "ask_adaptive_context_has_retrieval": bool(by_type["ask"]["payload"]["adaptive_memory_context"]["retrieval_context"]),
            "feedback_linked_to_ask": by_type["feedback"]["linked_operation_id"] == asked["operation_id"],
            "feedback_metadata_linked": feedback["feedback"]["metadata"]["linked_operation_id"] == asked["operation_id"],
            "selector_context_schema": by_type["selector_explain"]["payload"]["selector_context"]["schema"] == "adaptive_memory_context/v1",
            "selector_context_logged": bool(by_type["selector_explain"]["payload"]["selector_context"]["retrieval_context"]),
            "selector_context_has_features": bool(by_type["selector_explain"]["payload"]["selector_context"]["features"]),
            "ask_raw_results_have_training_fields": all(
                field in by_type["ask"]["payload"]["response"]["raw_results"][0]
                for field in (
                    "memory_id",
                    "score",
                    "text_match_score",
                    "intent_match_score",
                    "supersession_score",
                    "relation_supersession_score",
                    "summary_relation_score",
                    "feedback_score",
                    "authority_state",
                    "source",
                    "text",
                )
            ),
        }
        report = {
            "ok": all(checks.values()),
            "checks": checks,
            "operation_ids": {
                "ask": asked.get("operation_id"),
                "selector_explain": explained.get("operation_id"),
                "feedback": feedback.get("operation_id"),
            },
            "log_path": str(log_path),
            "event_count": len(rows),
        }
        print(json.dumps(report, indent=2), flush=True)
        return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
