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
        memory_type="design_rule",
        importance=0.7,
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
    query = "Can the assistant push documentation updates to GitHub automatically?"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "ask_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            embedding = pipeline.encoder.embed(query)
            domain = DomainState(id="dom_agent_memory", name="agent_memory", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(domain)
            stale = make_memory(
                "mem_old_github_policy",
                "Old repository policy: the assistant may push small documentation updates automatically after local tests pass. These conflict seeds are not final truth.",
                embedding,
                domain.id,
            )
            current = make_memory(
                "mem_current_github_policy",
                "Correction: the assistant must not push to GitHub automatically. GitHub uploads happen only when Mira explicitly asks.",
                embedding,
                domain.id,
            )
            pipeline.db.insert_memory(stale)
            pipeline.db.insert_memory(current)
            pipeline.db.set_memory_source(stale.id, str(root / "agent_memory_v1" / "conflicts_v1.md"), 0)
            pipeline.db.set_memory_source(current.id, str(root / "agent_memory_v2" / "corrections_v2.md"), 0)
            pipeline.db.add_relation(current.id, stale.id, "corrects", 1.0)

            answer = pipeline.ask(query, top_k=2)
        finally:
            pipeline.close()

    assert answer["evidence"][0]["memory_id"] == "mem_current_github_policy"
    assert answer["current"][0]["memory_id"] == "mem_current_github_policy"
    assert answer["stale"][0]["memory_id"] == "mem_old_github_policy"
    assert answer["conflict"] is True
    assert "must not push" in answer["answer"].lower()
    print(
        json.dumps(
            {
                "ok": True,
                "answer": answer["answer"],
                "confidence": answer["confidence"],
                "conflict": answer["conflict"],
                "evidence": answer["evidence"],
                "stale": answer["stale"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
