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
    original = "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment."
    first_query = "What is Cerulean Keystone?"
    followup = "What should I remember about that label?"
    correction = "Cerulean Keystone was renamed Amber Compass for the adaptive memory brain experiment."

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_context_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            taught = pipeline.teach(
                original,
                source="agent_training_v1/project_label.md",
                agent_id="agent_context",
                store_session=True,
            )
            first = pipeline.ask(first_query, top_k=1, session_id=taught["session_id"], agent_id="agent_context", store_session=True)
            second = pipeline.ask(followup, top_k=1, session_id=taught["session_id"], agent_id="agent_context", store_session=True)
            corrected = pipeline.correct(
                correction,
                source="agent_training_v2/project_label.md",
                session_id=taught["session_id"],
                agent_id="agent_context",
                store_session=True,
            )
            after = pipeline.ask(followup, top_k=2, session_id=taught["session_id"], agent_id="agent_context", store_session=True)
            history = pipeline.db.session_history(taught["session_id"])
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    assert first["evidence"][0]["memory_id"] == taught["memory"]["memory_id"]
    assert second["session_context_used"] is True
    assert "Cerulean Keystone" in second["retrieval_query"]
    assert second["evidence"][0]["memory_id"] == taught["memory"]["memory_id"]
    assert corrected["target_memory_ids"] == [taught["memory"]["memory_id"]]
    assert corrected["relations"]
    assert any(item["memory_id"] == corrected["correction_memory"]["memory_id"] for item in after["current"])
    assert any(item["memory_id"] == taught["memory"]["memory_id"] for item in after["stale"])
    assert "Amber Compass" in after["answer"]
    assert stats["sessions"] == 1
    assert stats["session_turns"] >= 8

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": taught["session_id"],
                "second": {
                    "answer": second["answer"],
                    "session_context_used": second["session_context_used"],
                    "retrieval_query": second["retrieval_query"],
                    "evidence": second["evidence"],
                },
                "corrected": corrected,
                "after": {
                    "answer": after["answer"],
                    "current": after["current"],
                    "stale": after["stale"],
                    "retrieval_query": after["retrieval_query"],
                },
                "turn_count": len(history),
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
