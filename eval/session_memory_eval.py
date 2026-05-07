from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def main() -> None:
    label_memory = "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment."
    policy_memory = "GitHub policy memory: the assistant must not push to GitHub automatically unless Mira explicitly asks."

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_memory_eval.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            label = pipeline.teach(
                label_memory,
                source="agent_training/project_label.md",
                agent_id="agent_context",
                store_session=True,
            )
            session_id = label["session_id"]
            policy = pipeline.teach(
                policy_memory,
                source="agent_training/github_policy.md",
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            policy_answer = pipeline.ask(
                "Can the assistant push to GitHub automatically?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            vague_policy = pipeline.ask(
                "What about that?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            label_answer = pipeline.ask(
                "What is Cerulean Keystone?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            vague_label = pipeline.ask(
                "What about that?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            session_memory = pipeline.db.list_session_memory(session_id)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    policy_ids = [item["memory_id"] for item in vague_policy["evidence"]]
    label_ids = [item["memory_id"] for item in vague_label["evidence"]]
    active = next(item for item in session_memory if item["key"] == "active_topic")

    assert policy_answer["evidence"][0]["memory_id"] == policy["memory"]["memory_id"]
    assert policy["memory"]["memory_id"] in policy_ids
    assert "GitHub policy memory" in vague_policy["retrieval_query"]
    assert label_answer["evidence"][0]["memory_id"] == label["memory"]["memory_id"]
    assert label["memory"]["memory_id"] in label_ids
    assert "Cerulean Keystone" in vague_label["retrieval_query"]
    assert active["metadata"]["evidence_memory_ids"]
    assert stats["session_memory"] == 1

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": session_id,
                "vague_policy": {
                    "answer": vague_policy["answer"],
                    "session_context": vague_policy["session_context"],
                    "evidence": vague_policy["evidence"],
                    "retrieval_query": vague_policy["retrieval_query"],
                },
                "vague_label": {
                    "answer": vague_label["answer"],
                    "session_context": vague_label["session_context"],
                    "evidence": vague_label["evidence"],
                    "retrieval_query": vague_label["retrieval_query"],
                },
                "session_memory": session_memory,
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
