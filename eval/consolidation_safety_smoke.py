from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.consolidation import consolidation_plan, create_consolidation_summaries, maybe_consolidate
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def run() -> dict:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "consolidation_safety.db")
        try:
            stable_ids = []
            stable_texts = [
                "Agent memory stable note: retrieval should preserve evidence ids.",
                "Agent memory stable note: retrieval should show source files.",
                "Agent memory stable note: retrieval should report confidence.",
                "Agent memory stable note: retrieval should keep session context separate.",
            ]
            for idx, text in enumerate(stable_texts):
                result = pipeline.teach(
                    text,
                    source=f"consolidation/stable_{idx}.md",
                    agent_id="consolidation_smoke",
                    store_session=False,
                )
                stable_ids.append(result["memory"]["memory_id"])

            old = pipeline.teach(
                "Old repository policy: the assistant may push documentation updates automatically.",
                source="consolidation/old_policy.md",
                agent_id="consolidation_smoke",
                store_session=False,
            )
            old_id = old["memory"]["memory_id"]
            correction = pipeline.correct(
                "the assistant must not push documentation updates automatically unless the user explicitly asks.",
                target_memory_ids=[old_id],
                target_query="Can the assistant push documentation updates automatically?",
                source="consolidation/current_policy.md",
                agent_id="consolidation_smoke",
                store_session=False,
            )
            current_id = correction["correction_memory"]["memory_id"]

            plan = consolidation_plan(pipeline.db, min_domain_memories=2)
            dry_run = maybe_consolidate(pipeline.db, dry_run=True)
            created = create_consolidation_summaries(pipeline, min_domain_memories=2, max_groups=1)
            after_create_plan = consolidation_plan(pipeline.db, min_domain_memories=2)
            protected = set(plan["protected_memory_ids"])
            candidate_ids = {
                memory_id
                for group in plan["candidate_groups"]
                for memory_id in group["memory_ids"]
            }
            after_create_protected = set(after_create_plan["protected_memory_ids"])
            summary_ids = [item["summary_memory_id"] for item in created["created_summaries"]]
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    ok = (
        old_id in protected
        and current_id in protected
        and old_id not in candidate_ids
        and current_id not in candidate_ids
        and bool(set(stable_ids) & candidate_ids)
        and dry_run["created"] == 0
        and dry_run["mode"] == "dry_run"
        and created["created"] == 1
        and bool(summary_ids)
        and all(memory_id in after_create_protected for memory_id in summary_ids)
        and all(memory_id in after_create_protected for memory_id in stable_ids)
        and stats["relations"] == 1 + len(stable_ids)
    )
    return {
        "ok": ok,
        "stable_ids": stable_ids,
        "old_memory_id": old_id,
        "current_memory_id": current_id,
        "protected_memory_ids": sorted(protected),
        "candidate_ids": sorted(candidate_ids),
        "created": created,
        "after_create_plan": after_create_plan,
        "plan": plan,
        "dry_run": dry_run,
        "stats": stats,
    }


def main() -> None:
    payload = run()
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
