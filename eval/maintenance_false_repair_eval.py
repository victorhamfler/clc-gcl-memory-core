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
NAMESPACE = "agent:false_repair_eval"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def relation_count(rows: list[dict[str, Any]], relation_type: str) -> int:
    return sum(int(row["count"]) for row in rows if row["relation_type"] == relation_type)


def ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("memory_id")) for row in rows if row.get("memory_id")}


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "maintenance_false_repair_eval.db")
        try:
            old = pipeline.teach(
                "GitHub upload policy: the assistant may upload repository changes automatically after tests pass.",
                source="agent_policy/old_github_upload.md",
                store_session=False,
                namespace=NAMESPACE,
            )
            wrong_repair = record_memory_improvement(
                pipeline,
                old["memory"]["memory_id"],
                "GitHub upload policy: the assistant may upload repository changes automatically after local tests pass when memory maintenance succeeds.",
                agent_id="false_repair_eval",
                namespace=NAMESPACE,
            )
            correction = pipeline.correct(
                "GitHub upload policy: the assistant must not upload to GitHub unless the user explicitly asks for that upload.",
                target_memory_ids=[
                    old["memory"]["memory_id"],
                    wrong_repair["improvement_memory"]["memory_id"],
                ],
                target_query="What is the GitHub upload policy?",
                source="agent_policy/corrected_github_upload.md",
                store_session=False,
                namespace=NAMESPACE,
            )
            answer = pipeline.ask(
                "What is the GitHub upload policy?",
                top_k=8,
                namespace=NAMESPACE,
                include_global=False,
            )
            active_weak = weak_memories(pipeline.db, limit=10)
            resolved_weak = weak_memories(pipeline.db, limit=10, include_resolved=True)
            relations = pipeline.db.relation_counts()
            health_stats = pipeline.db.stats()
        finally:
            pipeline.close()

    answer_text = str(answer["answer"] or "").lower()
    stale_ids = ids(answer.get("stale", []))
    evidence_ids = ids(answer.get("evidence", []))
    active_weak_ids = ids(active_weak)
    resolved_weak_ids = ids(resolved_weak)
    old_id = old["memory"]["memory_id"]
    wrong_id = wrong_repair["improvement_memory"]["memory_id"]
    correction_id = correction["correction_memory"]["memory_id"]
    checks = {
        "wrong_repair_created_update_relation": relation_count(relations, "updates") >= 1,
        "correction_created_correct_relations": relation_count(relations, "corrects") >= 2,
        "correction_feedback_marked_targets_stale": len(correction["feedback"]) == 2,
        "answer_uses_correct_policy": "must not upload" in answer_text and "explicitly asks" in answer_text,
        "answer_does_not_use_false_repair": "automatically after local tests" not in answer_text,
        "correction_is_preferred_evidence": correction_id in evidence_ids,
        "old_or_wrong_memory_marked_stale": bool({old_id, wrong_id} & stale_ids),
        "resolved_targets_not_active_weak": old_id not in active_weak_ids and wrong_id not in active_weak_ids,
        "resolved_targets_visible_when_requested": old_id in resolved_weak_ids or wrong_id in resolved_weak_ids,
        "namespace_preserved": answer.get("namespace") == NAMESPACE,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "memory_ids": {
            "old": old_id,
            "wrong_repair": wrong_id,
            "correction": correction_id,
        },
        "answer": {
            "text": answer["answer"],
            "confidence": answer["confidence"],
            "conflict": answer["conflict"],
            "evidence": answer["evidence"],
            "stale": answer["stale"],
        },
        "relations": relations,
        "active_weak": active_weak,
        "resolved_weak": resolved_weak,
        "stats": health_stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
