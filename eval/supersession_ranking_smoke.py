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
    query = "What is the current GitHub policy?"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "supersession_ranking.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            embedding = pipeline.encoder.embed(query)
            domain = DomainState(id="dom_supersession", name="agent_memory", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(domain)

            stale = make_memory(
                "mem_old_policy",
                "Old repository policy: the assistant may push small documentation updates automatically after tests pass. These conflict seeds are not final truth.",
                embedding,
                domain.id,
            )
            current = make_memory(
                "mem_current_policy",
                "Correction: the assistant must not push to GitHub automatically. GitHub uploads happen only when Mira explicitly asks.",
                embedding,
                domain.id,
            )
            pipeline.db.insert_memory(stale)
            pipeline.db.insert_memory(current)
            pipeline.db.set_memory_source(stale.id, str(root / "agent_memory_v1" / "conflicts_v1.md"), 0)
            pipeline.db.set_memory_source(current.id, str(root / "agent_memory_v2" / "corrections_v2.md"), 0)
            pipeline.db.add_relation(current.id, stale.id, "supersedes", 1.0)

            results = pipeline.retrieve(query, top_k=2)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    assert results[0]["memory_id"] == "mem_current_policy"
    assert results[0]["supersession_score"] > 0
    assert results[0]["relation_supersession_score"] > 0
    assert results[1]["supersession_score"] < 0
    assert results[1]["relation_supersession_score"] < 0
    assert stats["relations"] == 1
    print(
        json.dumps(
            {
                "ok": True,
                "results": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "cosine": item["cosine"],
                        "supersession_score": item["supersession_score"],
                        "relation_supersession_score": item["relation_supersession_score"],
                        "source": item["source"],
                    }
                    for item in results
                ],
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
