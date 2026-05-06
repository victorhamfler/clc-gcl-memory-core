from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.maintenance import improvement_plan, memory_review, record_memory_improvement, weak_memories
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "memory_maintenance.db")
        try:
            weak_seed = pipeline.ingest(
                "Experimental orphan note: maybe the agent sometimes stores maintenance facts without a source.",
            )
            strong_seed = pipeline.teach(
                "Agent memory maintenance should preserve evidence ids and source labels.",
                source="maintenance_eval/strong.md",
                agent_id="maintenance_eval_agent",
                store_session=False,
            )
            pipeline.db.add_retrieval_feedback(
                weak_seed["memory_id"],
                "missing_source",
                query="maintenance facts",
                rating=-0.5,
                notes="seed weak memory for maintenance eval",
            )
            review_before = memory_review(pipeline.db, weak_limit=5)
            weak_before = weak_memories(pipeline.db, limit=5)
            plan = improvement_plan(pipeline.db, memory_id=weak_seed["memory_id"], limit=1)
            improved = record_memory_improvement(
                pipeline,
                weak_seed["memory_id"],
                "Retaught with provenance: maintenance facts should include source labels and evidence ids.",
                agent_id="maintenance_eval_agent",
            )
            review_after = memory_review(pipeline.db, weak_limit=5)
            weak_after = weak_memories(pipeline.db, limit=5)
            resolved_after = weak_memories(pipeline.db, limit=5, include_resolved=True)
            retrieved = pipeline.retrieve("maintenance facts source labels evidence ids", top_k=5)
            original_exists = pipeline.db.memory_exists_id(weak_seed["memory_id"])
            stats = pipeline.db.stats()
            relations = pipeline.db.relation_counts()
        finally:
            pipeline.close()

    improvement_id = improved["improvement_memory"]["memory_id"]
    retrieved_ids = [item["memory_id"] for item in retrieved]
    checks = {
        "weak_memory_detected": any(item["memory_id"] == weak_seed["memory_id"] for item in weak_before),
        "review_recommends_weak_review": "review_weak_memories" in review_before["recommendations"],
        "plan_targets_memory": plan["items"] and plan["items"][0]["memory_id"] == weak_seed["memory_id"],
        "improvement_memory_created": improvement_id != weak_seed["memory_id"],
        "updates_relation_created": any(row["relation_type"] == "updates" for row in relations),
        "original_memory_preserved": original_exists,
        "improvement_retrievable": improvement_id in retrieved_ids,
        "stats_count_increased": stats["memories"] >= 3,
        "strong_seed_preserved": strong_seed["memory"]["memory_id"] != improvement_id,
        "resolved_target_removed_from_active_weak_list": not any(
            item["memory_id"] == weak_seed["memory_id"] for item in weak_after
        ),
        "improvement_not_active_weak": not any(item["memory_id"] == improvement_id for item in weak_after),
        "resolved_target_marked_when_included": any(
            item["memory_id"] == weak_seed["memory_id"] and item["resolved"] for item in resolved_after
        ),
        "review_after_ok": review_after["ok"] is True,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "weak_memory_id": weak_seed["memory_id"],
        "strong_memory_id": strong_seed["memory"]["memory_id"],
        "improvement_memory_id": improvement_id,
        "review_before": review_before,
        "plan": plan,
        "review_after_recommendations": review_after["recommendations"],
        "weak_after": weak_after,
        "resolved_after": resolved_after,
        "retrieved_ids": retrieved_ids,
        "relations": relations,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
