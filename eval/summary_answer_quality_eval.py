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
        pipeline = init_pipeline(root, root / "summary_answer_quality.db")
        try:
            source_ids = []
            for idx, text in enumerate(
                [
                    "Agent memory summary skill: store durable user profile facts with evidence ids.",
                    "Agent memory summary skill: answer questions with confidence and citations.",
                    "Agent memory summary skill: keep stale context separate from current evidence.",
                    "Agent memory summary skill: preserve original memories behind consolidation summaries.",
                ]
            ):
                taught = pipeline.teach(
                    text,
                    source=f"summary_answer/source_{idx}.md",
                    agent_id="summary_quality_agent",
                    store_session=False,
                )
                source_ids.append(taught["memory"]["memory_id"])
            created = create_consolidation_summaries(pipeline, min_domain_memories=3, max_groups=1)
            summary_id = created["created_summaries"][0]["summary_memory_id"]
            broad = pipeline.ask("Summarize the agent memory summary skill.", top_k=4)
            specific = pipeline.ask("How should consolidation preserve original memories?", top_k=4)
        finally:
            pipeline.close()

    broad_answer = broad["answer"]
    specific_answer = specific["answer"]
    broad_evidence_ids = [item["memory_id"] for item in broad["evidence"]]
    specific_evidence_ids = [item["memory_id"] for item in specific["evidence"]]
    broad_source_context_ids = [item["memory_id"] for item in broad.get("source_context", [])]
    checks = {
        "broad_uses_summary_evidence": summary_id in broad_evidence_ids,
        "broad_has_summary_prefix": broad_answer.startswith("Consolidated memory summary indicates:"),
        "broad_avoids_stale_warning": "Older or stale memories" not in broad_answer,
        "broad_hides_source_ids": "Source memory ids:" not in broad_answer,
        "broad_exposes_originals_as_context": any(memory_id in source_ids for memory_id in broad_source_context_ids),
        "specific_prefers_original_evidence": specific_evidence_ids and specific_evidence_ids[0] in source_ids,
        "specific_avoids_summary_prefix": not specific_answer.startswith("Consolidated memory summary indicates:"),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "summary_id": summary_id,
        "source_ids": source_ids,
        "broad": {
            "answer": broad_answer,
            "confidence": broad["confidence"],
            "conflict": broad["conflict"],
            "evidence_ids": broad_evidence_ids,
            "source_context_ids": broad_source_context_ids,
        },
        "specific": {
            "answer": specific_answer,
            "confidence": specific["confidence"],
            "conflict": specific["conflict"],
            "evidence_ids": specific_evidence_ids,
        },
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
