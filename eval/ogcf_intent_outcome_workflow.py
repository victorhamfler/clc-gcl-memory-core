from __future__ import annotations

import json
import subprocess
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


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_intent_outcome_workflow_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_intent_outcome_workflow_report.md"
LOG_COPY = REPO_ROOT / "experiments" / "ogcf_intent_outcome_workflow.jsonl"
CANDIDATE_JSON = REPO_ROOT / "experiments" / "ogcf_intent_candidates_from_memory_session.json"
CANDIDATE_MD = REPO_ROOT / "experiments" / "ogcf_intent_candidates_from_memory_session_report.md"


FIXTURES = {
    "ordinary_lookup": {
        "text": "Lunar audit meeting schedule: Victor meets Hermes on Tuesday at 10:00.",
        "source": "ogcf_workflow/lunar_audit_schedule.md",
    },
    "bridge_weather": {
        "text": "Meshlink bridge memo: radar uncertainty connects weather checks to selector refresh evidence.",
        "source": "ogcf_workflow/meshlink_weather_bridge.md",
    },
    "bridge_project": {
        "text": "Meshlink bridge memo: project risk connects deployment notes to selector refresh evidence.",
        "source": "ogcf_workflow/meshlink_project_bridge.md",
    },
    "geometry_loop": {
        "text": "Manifolddrift geometry note: embedding stress reveals bridge loop pressure across memory clusters.",
        "source": "ogcf_workflow/manifolddrift_loop_geometry.md",
    },
    "geometry_defect": {
        "text": "Manifolddrift geometry note: local vector stress reveals bridge defect pressure in memory clusters.",
        "source": "ogcf_workflow/manifolddrift_defect_geometry.md",
    },
    "maintenance_duplicate": {
        "text": "Pruneflow maintenance note: duplicate policy memories should be reviewed with canonical support.",
        "source": "ogcf_workflow/pruneflow_duplicate_maintenance.md",
    },
    "maintenance_bridge": {
        "text": "Pruneflow maintenance note: bridge-heavy duplicate memories should be reviewed before refresh.",
        "source": "ogcf_workflow/pruneflow_bridge_maintenance.md",
    },
    "false_positive_lunar": {
        "text": "Lunar bridge story note: the word bridge is only a location name in this ordinary calendar fact.",
        "source": "ogcf_workflow/lunar_bridge_false_positive.md",
    },
}


CASES = [
    {
        "id": "ordinary_lookup_suppression",
        "query": "When is the lunar audit meeting scheduled?",
        "target": "ordinary_lookup",
        "label": "ordinary_lookup",
    },
    {
        "id": "bridge_weather_positive",
        "query": "How does meshlink connect weather uncertainty to selector refresh?",
        "target": "bridge_weather",
        "label": "bridge_relevant",
    },
    {
        "id": "bridge_project_positive",
        "query": "How does meshlink connect deployment risk to selector refresh?",
        "target": "bridge_project",
        "label": "cross_domain_bridge",
    },
    {
        "id": "geometry_loop_positive",
        "query": "Does manifolddrift reveal embedding stress in bridge loops?",
        "target": "geometry_loop",
        "label": "ogcf_geometry",
    },
    {
        "id": "geometry_defect_positive",
        "query": "Does manifolddrift reveal local vector stress in bridge defects?",
        "target": "geometry_defect",
        "label": "bridge_geometry",
    },
    {
        "id": "maintenance_duplicate_positive",
        "query": "Should pruneflow review duplicate policy memories?",
        "target": "maintenance_duplicate",
        "label": "dedup",
    },
    {
        "id": "maintenance_bridge_positive",
        "query": "Should pruneflow review bridge-heavy duplicate memories before refresh?",
        "target": "maintenance_bridge",
        "label": "bridge_maintenance",
    },
    {
        "id": "false_positive_lunar_bridge",
        "query": "What does the lunar bridge story note say?",
        "target": "false_positive_lunar",
        "label": "ogcf_false_positive",
    },
]


def build_test_api(tmp: Path) -> MemoryApi:
    db_path = tmp / "ogcf_intent_outcome.db"
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
                "path": str(tmp / "ogcf_intent_outcomes.jsonl"),
                "max_text_chars": 900,
                "max_list_items": 40,
            }
        },
    )
    return api


def ref_for_source(source: str | None) -> str | None:
    for ref, fixture in FIXTURES.items():
        if source == fixture["source"]:
            return ref
    return None


def find_row(rows: list[dict[str, Any]], target_ref: str) -> tuple[int | None, dict[str, Any] | None]:
    for idx, row in enumerate(rows, start=1):
        if ref_for_source(row.get("source")) == target_ref:
            return idx, row
    return None, None


def run_case(api: MemoryApi, namespace: str, case: dict[str, str]) -> dict[str, Any]:
    asked = api.ask(
        {
            "query": case["query"],
            "namespace": namespace,
            "include_global": False,
            "agent_id": "ogcf-intent-outcome-workflow",
            "top_k": 12,
            "store_session": False,
        }
    )
    rank, row = find_row(asked.get("raw_results") or [], case["target"])
    if not row:
        return {
            "id": case["id"],
            "passed": False,
            "error": f"target {case['target']} was not retrieved",
            "retrieved_refs": [ref_for_source(item.get("source")) for item in asked.get("raw_results") or []],
            "ask_operation_id": asked.get("operation_id"),
        }
    feedback = api.feedback(
        {
            "memory_id": row["memory_id"],
            "label": case["label"],
            "query": case["query"],
            "operation_id": asked["operation_id"],
            "rank": rank,
            "retrieval_score": row.get("score"),
            "notes": f"ogcf intent outcome workflow: {case['id']}",
        }
    )
    expected_rating = FEEDBACK_RATINGS[case["label"]]
    return {
        "id": case["id"],
        "passed": (
            feedback.get("linked_operation_id") == asked.get("operation_id")
            and float(feedback["feedback"]["rating"]) == float(expected_rating)
        ),
        "query": case["query"],
        "target_ref": case["target"],
        "target_rank": rank,
        "target_memory_id": row["memory_id"],
        "label": case["label"],
        "expected_rating": expected_rating,
        "actual_rating": feedback["feedback"]["rating"],
        "ask_operation_id": asked.get("operation_id"),
        "feedback_operation_id": feedback.get("operation_id"),
        "linked_operation_id": feedback.get("linked_operation_id"),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_miner(log_path: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "eval" / "mine_ogcf_intent_candidates.py"),
        "--log",
        str(log_path),
        "--min-support",
        "2",
        "--out-json",
        str(CANDIDATE_JSON),
        "--out-md",
        str(CANDIDATE_MD),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = None
    return {
        "ok": proc.returncode == 0,
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "parsed_stdout": parsed,
    }


def support_has(candidate_report: dict[str, Any], family: str, term: str) -> bool:
    support = candidate_report.get("support") if isinstance(candidate_report.get("support"), dict) else {}
    values = support.get(family) if isinstance(support.get(family), dict) else {}
    return term in values and int(values.get(term) or 0) >= 2


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# OGCF Intent Outcome Workflow",
        "",
        f"Passed: **{report['ok']}**",
        f"Log copy: `{report['log_copy']}`",
        f"Candidate JSON: `{report['candidate_json']}`",
        f"Candidate Markdown: `{report['candidate_markdown']}`",
        "",
        "| case | pass | label | rating | rank | linked |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case.get('label')}` | "
            f"{case.get('actual_rating')} | {case.get('target_rank')} | `{case.get('linked_operation_id')}` |"
        )
    lines.extend(
        [
            "",
            "## Candidate Checks",
            "",
            "```json",
            json.dumps(report["candidate_checks"], indent=2),
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    namespace = "ogcf_intent_outcome_workflow"
    with tempfile.TemporaryDirectory(prefix="ogcf_intent_outcome_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            for ref, fixture in FIXTURES.items():
                api.teach(
                    {
                        "text": fixture["text"],
                        "source": fixture["source"],
                        "namespace": namespace,
                        "agent_id": "ogcf-intent-outcome-workflow",
                        "store_session": False,
                        "metadata": {"ref": ref},
                        "domain": "agent_memory",
                        "memory_type": "procedure",
                    }
                )
            cases = [run_case(api, namespace, case) for case in CASES]
            log_path = api.outcome_logger.path
            log_text = log_path.read_text(encoding="utf-8")
        finally:
            api.close()

    LOG_COPY.parent.mkdir(parents=True, exist_ok=True)
    LOG_COPY.write_text(log_text, encoding="utf-8")
    miner = run_miner(LOG_COPY)
    candidate_report = json.loads(CANDIDATE_JSON.read_text(encoding="utf-8")) if CANDIDATE_JSON.exists() else {}
    events = read_jsonl(LOG_COPY)
    ask_count = sum(1 for event in events if event.get("event_type") == "ask")
    feedback_count = sum(1 for event in events if event.get("event_type") == "feedback")
    linked_feedback_count = sum(
        1 for event in events if event.get("event_type") == "feedback" and event.get("linked_operation_id")
    )
    candidate_checks = {
        "bridge_meshlink_support": support_has(candidate_report, "bridge_terms", "meshlink"),
        "geometry_manifolddrift_support": support_has(candidate_report, "geometry_terms", "manifolddrift"),
        "maintenance_pruneflow_support": support_has(candidate_report, "maintenance_terms", "pruneflow"),
        "ordinary_lunar_support": support_has(candidate_report, "ordinary_fact_terms", "lunar"),
    }
    report = {
        "ok": (
            all(case["passed"] for case in cases)
            and miner["ok"]
            and ask_count == len(CASES)
            and feedback_count == len(CASES)
            and linked_feedback_count == len(CASES)
            and all(candidate_checks.values())
        ),
        "log_copy": str(LOG_COPY),
        "candidate_json": str(CANDIDATE_JSON),
        "candidate_markdown": str(CANDIDATE_MD),
        "ask_event_count": ask_count,
        "feedback_event_count": feedback_count,
        "linked_feedback_count": linked_feedback_count,
        "cases": cases,
        "miner": miner,
        "candidate_checks": candidate_checks,
        "candidate_count": candidate_report.get("candidate_count"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "log": str(LOG_COPY),
                "candidate_json": str(CANDIDATE_JSON),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
