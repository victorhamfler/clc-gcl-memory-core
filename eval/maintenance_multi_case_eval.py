from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.maintenance import record_memory_improvement, weak_memories
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


CASES = [
    {
        "id": "provenance_rule",
        "query": "How should maintenance facts store provenance?",
        "weak": "Maintenance facts are temporary notes and can be stored without evidence ids or source labels.",
        "rating": -0.75,
        "note": "Current maintenance rule: maintenance facts must include source labels, evidence ids, and provenance notes.",
        "expected": ["must include", "source labels", "evidence ids"],
        "forbidden": ["without evidence ids", "without source labels", "can be stored without"],
    },
    {
        "id": "agent_style_preference",
        "query": "How should the agent answer detailed planning questions?",
        "weak": "The agent should always answer detailed planning questions with only one short sentence.",
        "rating": -0.65,
        "note": "Current response style rule: detailed planning questions should get concise structure, evidence, and next actions.",
        "expected": ["concise structure", "evidence", "next actions"],
        "forbidden": ["only one short sentence", "always answer"],
    },
    {
        "id": "github_upload_policy",
        "query": "Can the assistant upload every memory change to GitHub automatically?",
        "weak": "The assistant can upload every memory change to GitHub automatically after tests pass.",
        "rating": -0.8,
        "note": "Current GitHub policy: upload to GitHub only when the user explicitly asks for that upload.",
        "expected": ["only when", "explicitly asks"],
        "forbidden": ["automatically after tests pass", "upload every memory change"],
    },
]


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def contains_all(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return all(term.lower() in lower for term in terms)


def contains_any(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return any(term.lower() in lower for term in terms)


def rank_of(memory_id: str, rows: list[dict[str, Any]]) -> int | None:
    for index, row in enumerate(rows, start=1):
        if row.get("memory_id") == memory_id:
            return index
    return None


def run_case(pipeline: MemoryPipeline, case: dict[str, Any]) -> dict[str, Any]:
    weak = pipeline.ingest(case["weak"])
    weak_id = weak["memory_id"]
    pipeline.db.add_retrieval_feedback(
        weak_id,
        "stale",
        query=case["query"],
        rating=float(case["rating"]),
        notes=f"multi-case maintenance seed: {case['id']}",
    )
    before_answer = pipeline.ask(case["query"], top_k=4)
    before_retrieval = pipeline.retrieve(case["query"], top_k=5)
    before_weak = weak_memories(pipeline.db, limit=20)

    improved = record_memory_improvement(
        pipeline,
        weak_id,
        case["note"],
        agent_id="maintenance_multi_case_agent",
    )
    improvement_id = improved["improvement_memory"]["memory_id"]
    after_answer = pipeline.ask(case["query"], top_k=4)
    after_retrieval = pipeline.retrieve(case["query"], top_k=5)
    active_weak = weak_memories(pipeline.db, limit=20)
    resolved_weak = weak_memories(pipeline.db, limit=20, include_resolved=True)

    checks = {
        "weak_was_active_before": any(item["memory_id"] == weak_id for item in before_weak),
        "before_answer_bad": contains_any(before_answer["answer"], case["forbidden"]),
        "improvement_top_after": rank_of(improvement_id, after_retrieval) == 1,
        "old_memory_demoted_after": (rank_of(weak_id, after_retrieval) or 99) > 1,
        "answer_uses_expected_terms": contains_all(after_answer["answer"], case["expected"]),
        "answer_avoids_forbidden_terms": not contains_any(after_answer["answer"], case["forbidden"]),
        "answer_hides_internal_wrapper": "Memory improvement for" not in after_answer["answer"] and "mem_" not in after_answer["answer"],
        "old_memory_resolved": not any(item["memory_id"] == weak_id for item in active_weak)
        and any(item["memory_id"] == weak_id and item.get("resolved") for item in resolved_weak),
        "improvement_not_weak": not any(item["memory_id"] == improvement_id for item in active_weak),
    }
    return {
        "id": case["id"],
        "ok": all(checks.values()),
        "checks": checks,
        "weak_memory_id": weak_id,
        "improvement_memory_id": improvement_id,
        "before_answer": before_answer["answer"],
        "after_answer": after_answer["answer"],
        "after_evidence_ids": [item.get("memory_id") for item in after_answer.get("evidence") or []],
        "after_stale_ids": [item.get("memory_id") for item in after_answer.get("stale") or []],
    }


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "maintenance_multi_case.db")
        try:
            case_results = [run_case(pipeline, case) for case in CASES]
            active_weak = weak_memories(pipeline.db, limit=20)
            resolved_weak = weak_memories(pipeline.db, limit=20, include_resolved=True)
            relations = pipeline.db.relation_counts()
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    resolved_ids = {item["memory_id"] for item in resolved_weak if item.get("resolved")}
    improvement_ids = {case["improvement_memory_id"] for case in case_results}
    checks = {
        "all_cases_pass": all(case["ok"] for case in case_results),
        "all_targets_resolved": all(case["weak_memory_id"] in resolved_ids for case in case_results),
        "no_improvement_is_active_weak": all(
            item["memory_id"] not in improvement_ids for item in active_weak
        ),
        "updates_count_matches_cases": any(
            row["relation_type"] == "updates" and row["count"] == len(CASES) for row in relations
        ),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "cases": case_results,
        "active_weak_count": len(active_weak),
        "resolved_weak_count": len([item for item in resolved_weak if item.get("resolved")]),
        "relations": relations,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
