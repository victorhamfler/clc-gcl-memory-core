from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.models import DomainState, MemoryNode
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB, utc_now


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def make_memory(memory_id: str, text: str, embedding: list[float], domain_id: str) -> MemoryNode:
    now = utc_now()
    return MemoryNode(
        id=memory_id,
        text=text,
        embedding=embedding,
        domain_id=domain_id,
        memory_type="semantic_note",
        importance=0.5,
        stability=0.0,
        confidence=0.8,
        csd_score=0.0,
        surprise=0.0,
        recall_score=1.0,
        curiosity=0.0,
        focus=0.5,
        clc_state="RECALL",
        created_at=now,
        updated_at=now,
    )


def main() -> None:
    query = "feedback ranking target memory"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "feedback_ranking.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            embedding = pipeline.encoder.embed(query)
            domain = DomainState(id="dom_feedback", name="feedback_test", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(domain)
            weak = make_memory("mem_feedback_weak", "Weak candidate should lose after negative feedback.", embedding, domain.id)
            strong = make_memory("mem_feedback_strong", "Strong candidate should win after excellent feedback.", embedding, domain.id)
            pipeline.db.insert_memory(weak)
            pipeline.db.insert_memory(strong)

            before = pipeline.retrieve(query, top_k=2)
            pipeline.db.add_retrieval_feedback(
                memory_id=weak.id,
                label="wrong",
                query=query,
                rating=-1.0,
                rank=1,
                retrieval_score=before[0]["score"],
            )
            for _ in range(3):
                pipeline.db.add_retrieval_feedback(
                    memory_id=strong.id,
                    label="excellent",
                    query=query,
                    rating=2.0,
                    rank=2,
                    retrieval_score=before[1]["score"],
                )
            after = pipeline.retrieve(query, top_k=2)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    assert before[0]["score"] == before[1]["score"]
    assert after[0]["memory_id"] == "mem_feedback_strong"
    assert after[0]["feedback_score"] > 0
    assert after[1]["feedback_score"] < 0
    assert stats["retrieval_feedback"] == 4
    print(
        json.dumps(
            {
                "ok": True,
                "before": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "feedback_score": item["feedback_score"],
                    }
                    for item in before
                ],
                "after": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "feedback_score": item["feedback_score"],
                        "feedback_count": item["feedback_count"],
                    }
                    for item in after
                ],
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
