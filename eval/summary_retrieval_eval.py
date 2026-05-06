from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.consolidation import create_consolidation_summaries
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
        pipeline = init_pipeline(root, root / "summary_retrieval.db")
        try:
            source_texts = [
                "Agent memory broad skill: store durable user profile facts with evidence ids and source labels.",
                "Agent memory broad skill: retrieve answers with citations, confidence, and stale context separation.",
                "Agent memory broad skill: accept feedback labels to improve future retrieval ranking.",
                "Agent memory broad skill: create safe summaries without deleting original memory evidence.",
            ]
            source_ids = []
            for idx, text in enumerate(source_texts):
                item = pipeline.teach(
                    text,
                    source=f"summary_eval/source_{idx}.md",
                    agent_id="summary_eval_agent",
                    store_session=False,
                )
                source_ids.append(item["memory"]["memory_id"])

            created = create_consolidation_summaries(
                pipeline,
                min_domain_memories=3,
                max_candidates_per_domain=8,
                max_groups=1,
            )
            summary_id = created["created_summaries"][0]["summary_memory_id"] if created["created_summaries"] else None
            broad = pipeline.ask("Give an overview summary of the agent memory broad skill.", top_k=4)
            specific = pipeline.ask("How should the program keep original memory evidence?", top_k=4)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    broad_ids = [item["memory_id"] for item in broad["evidence"]]
    specific_ids = [item["memory_id"] for item in specific["evidence"]]
    source_context_ids = [item["memory_id"] for item in broad.get("source_context", [])]
    result = {
        "ok": (
            created["created"] == 1
            and summary_id in broad_ids
            and any(memory_id in source_ids for memory_id in specific_ids)
            and any(memory_id in source_ids for memory_id in source_context_ids)
            and broad["answer"].startswith("Consolidated memory summary indicates:")
            and "Older or stale memories" not in broad["answer"]
            and "Source memory ids:" not in broad["answer"]
        ),
        "summary_id": summary_id,
        "source_ids": source_ids,
        "broad_evidence_ids": broad_ids,
        "broad_source_context_ids": source_context_ids,
        "specific_evidence_ids": specific_ids,
        "broad_answer": broad["answer"],
        "specific_answer": specific["answer"],
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
