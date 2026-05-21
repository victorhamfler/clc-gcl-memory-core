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
from serve import MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "memory_outcome_contract_workflow_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_outcome_contract_workflow_report.md"
LOG_COPY = REPO_ROOT / "experiments" / "memory_outcome_contract_workflow.jsonl"

TRAINING_FIELDS = (
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


FIXTURES = {
    "stale": {
        "text": "Retired truth: Hermes deployment channel is alpha.",
        "source": "workflow/deployment_retired_truth.md",
    },
    "current": {
        "text": "Verified current: Hermes deployment channel is beta.",
        "source": "workflow/deployment_verified_current.md",
    },
    "sensitive": {
        "text": "Victor private signing key is sk-test-alpha.",
        "source": "workflow/private_signing_key.md",
    },
    "scope_deflection": {
        "text": "Ops control note: calendar approvals do not authorize GitHub uploads.",
        "source": "workflow/ops_control_note.md",
    },
    "broad": {
        "text": "Universal policy note: all approvals should be documented in the audit log.",
        "source": "workflow/universal_policy_note.md",
    },
}


CASES = [
    {
        "id": "stale_evidence_feedback",
        "query": "What deployment channel should Hermes use?",
        "target": "stale",
        "label": "stale",
        "rating": -0.75,
    },
    {
        "id": "current_correction_feedback",
        "query": "What is the current Hermes deployment channel?",
        "target": "current",
        "label": "corrected_current",
        "rating": 1.0,
    },
    {
        "id": "sensitive_lookup_feedback",
        "query": "What is Victor private signing key?",
        "target": "sensitive",
        "label": "sensitive_lookup",
        "rating": -1.0,
    },
    {
        "id": "wrong_domain_feedback",
        "query": "What GitHub upload approval policy should Hermes follow?",
        "target": "scope_deflection",
        "label": "wrong_domain",
        "rating": -0.75,
    },
    {
        "id": "generic_broad_feedback",
        "query": "What calendar change policy should Hermes follow?",
        "target": "broad",
        "label": "irrelevant",
        "rating": -0.75,
    },
]


def build_test_api(tmp: Path) -> MemoryApi:
    db_path = tmp / "memory_outcome_contract.db"
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
                "max_text_chars": 900,
                "max_list_items": 30,
            }
        },
    )
    return api


def ref_for_source(source: str | None) -> str | None:
    for ref, fixture in FIXTURES.items():
        if source == fixture["source"]:
            return ref
    return None


def find_row_by_ref(rows: list[dict[str, Any]], ref: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    for idx, row in enumerate(rows, start=1):
        if ref_for_source(row.get("source")) == ref:
            return idx, row
    return None, None


def run_case(api: MemoryApi, namespace: str, case: dict[str, Any]) -> dict[str, Any]:
    asked = api.ask(
        {
            "query": case["query"],
            "namespace": namespace,
            "include_global": False,
            "agent_id": "memory-outcome-contract",
            "top_k": 12,
            "store_session": False,
        }
    )
    rows = asked.get("raw_results") or []
    rank, row = find_row_by_ref(rows, case["target"])
    if not row:
        return {
            "id": case["id"],
            "passed": False,
            "query": case["query"],
            "error": f"target ref {case['target']} was not present in ask.raw_results",
            "operation_id": asked.get("operation_id"),
            "retrieved_refs": [ref_for_source(item.get("source")) for item in rows],
        }
    feedback = api.feedback(
        {
            "memory_id": row["memory_id"],
            "label": case["label"],
            "rating": case["rating"],
            "query": case["query"],
            "operation_id": asked["operation_id"],
            "rank": rank,
            "retrieval_score": row.get("score"),
            "notes": f"memory outcome contract workflow: {case['id']}",
        }
    )
    missing_fields = [field for field in TRAINING_FIELDS if field not in row]
    return {
        "id": case["id"],
        "passed": not missing_fields and feedback.get("linked_operation_id") == asked.get("operation_id"),
        "query": case["query"],
        "target_ref": case["target"],
        "target_memory_id": row.get("memory_id"),
        "target_rank": rank,
        "label": case["label"],
        "rating": case["rating"],
        "ask_operation_id": asked.get("operation_id"),
        "feedback_operation_id": feedback.get("operation_id"),
        "linked_operation_id": feedback.get("linked_operation_id"),
        "missing_training_fields": missing_fields,
    }


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Memory Outcome Contract Workflow",
        "",
        f"Passed: **{report['ok']}**",
        f"Log copy: `{report['log_copy']}`",
        f"Ask events: `{report['ask_event_count']}`",
        f"Feedback events: `{report['feedback_event_count']}`",
        "",
        "| case | pass | label | rank | linked | missing fields |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case.get('label')}` | "
            f"{case.get('target_rank')} | `{case.get('linked_operation_id')}` | "
            f"{', '.join(case.get('missing_training_fields') or []) or 'none'} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "memory_outcome_contract_workflow"
    with tempfile.TemporaryDirectory(prefix="memory_outcome_contract_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            for ref, fixture in FIXTURES.items():
                api.teach(
                    {
                        "text": fixture["text"],
                        "source": fixture["source"],
                        "namespace": namespace,
                        "include_global": False,
                        "agent_id": "memory-outcome-contract",
                        "store_session": False,
                        "metadata": {"ref": ref},
                        "domain": "agent_memory",
                        "memory_type": "procedure",
                    }
                )
            cases = [run_case(api, namespace, case) for case in CASES]
            log_path = api.outcome_logger.path
            events = read_events(log_path)
        finally:
            api.close()

        LOG_COPY.parent.mkdir(parents=True, exist_ok=True)
        LOG_COPY.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")

    ask_events = [event for event in events if event.get("event_type") == "ask"]
    feedback_events = [event for event in events if event.get("event_type") == "feedback"]
    linked_feedback = [event for event in feedback_events if event.get("linked_operation_id")]
    report = {
        "ok": all(case["passed"] for case in cases) and len(ask_events) == len(CASES) and len(linked_feedback) == len(CASES),
        "log_copy": str(LOG_COPY),
        "ask_event_count": len(ask_events),
        "feedback_event_count": len(feedback_events),
        "linked_feedback_count": len(linked_feedback),
        "cases": cases,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD), "log": str(LOG_COPY)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
