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
    first_query = "What is the agent name?"
    second_query = "Can the assistant push documentation updates automatically?"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            embedding = pipeline.encoder.embed(first_query)
            domain = DomainState(id="dom_session", name="agent_memory", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(domain)
            name_memory = make_memory(
                "mem_agent_name",
                "Current identity: the agent name is LoomGuide.",
                embedding,
                domain.id,
            )
            policy_memory = make_memory(
                "mem_github_policy",
                "Correction: the assistant must not push to GitHub automatically. GitHub uploads happen only when Mira explicitly asks.",
                pipeline.encoder.embed(second_query),
                domain.id,
            )
            pipeline.db.insert_memory(name_memory)
            pipeline.db.insert_memory(policy_memory)
            pipeline.db.set_memory_source(name_memory.id, "agent_memory_v2/updates_v2.md", 0)
            pipeline.db.set_memory_source(policy_memory.id, "agent_memory_v2/corrections_v2.md", 0)

            first = pipeline.ask(first_query, top_k=2, agent_id="agent_alpha", store_session=True)
            second = pipeline.ask(second_query, top_k=2, session_id=first["session_id"], agent_id="agent_alpha", store_session=True)
            history = pipeline.db.session_history(first["session_id"])
            sessions = pipeline.db.list_sessions(agent_id="agent_alpha")
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    assert first["session_id"]
    assert second["session_id"] == first["session_id"]
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["evidence_memory_ids"]
    assert sessions[0]["turn_count"] == 4
    assert stats["sessions"] == 1
    assert stats["session_turns"] == 4
    print(
        json.dumps(
            {
                "ok": True,
                "session_id": first["session_id"],
                "turn_count": len(history),
                "sessions": sessions,
                "history": history,
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
