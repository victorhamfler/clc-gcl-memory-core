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
    query = "source reliability generalizes to fresh candidate"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "reliability_ranking.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            embedding = pipeline.encoder.embed(query)
            good_domain = DomainState(id="dom_reliable", name="ReliableDomain", anchor_vector=embedding, memory_count=2)
            bad_domain = DomainState(id="dom_unreliable", name="UnreliableDomain", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(good_domain)
            pipeline.db.upsert_domain(bad_domain)

            history_embedding = pipeline.encoder.embed("archived unrelated reliability history")
            good_history = make_memory("mem_good_history", "Past reliable source answer.", history_embedding, good_domain.id)
            bad_history = make_memory("mem_bad_history", "Past unreliable source answer.", history_embedding, bad_domain.id)
            good_candidate = make_memory("mem_good_candidate", "Fresh candidate from reliable source.", embedding, good_domain.id)
            bad_candidate = make_memory("mem_bad_candidate", "Fresh candidate from unreliable source.", embedding, bad_domain.id)
            for memory in (bad_candidate, good_candidate, bad_history, good_history):
                pipeline.db.insert_memory(memory)
            pipeline.db.set_memory_source(good_history.id, "reliable_source.md", 0)
            pipeline.db.set_memory_source(good_candidate.id, "reliable_source.md", 1)
            pipeline.db.set_memory_source(bad_history.id, "unreliable_source.md", 0)
            pipeline.db.set_memory_source(bad_candidate.id, "unreliable_source.md", 1)

            before = pipeline.retrieve(query, top_k=4)
            for _ in range(3):
                pipeline.db.add_retrieval_feedback(good_history.id, "useful", query=query, rating=1.0)
                pipeline.db.add_retrieval_feedback(bad_history.id, "wrong", query=query, rating=-1.0)
            after = pipeline.retrieve(query, top_k=4)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    top_after = after[0]
    assert top_after["memory_id"] == "mem_good_candidate"
    assert top_after["feedback_count"] == 0
    assert top_after["domain_reliability"] > 0
    assert top_after["source_reliability"] > 0
    assert stats["retrieval_feedback"] == 6
    print(
        json.dumps(
            {
                "ok": True,
                "before": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "domain_reliability": item["domain_reliability"],
                        "source_reliability": item["source_reliability"],
                    }
                    for item in before
                ],
                "after": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "feedback_count": item["feedback_count"],
                        "feedback_score": item["feedback_score"],
                        "domain_reliability": item["domain_reliability"],
                        "source_reliability": item["source_reliability"],
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
