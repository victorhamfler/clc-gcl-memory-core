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
    query = "Can the assistant push documentation updates to GitHub automatically?"
    old_policy = "Old repository policy: the assistant may push documentation updates to GitHub automatically after local tests pass."
    correction = "the assistant must not push documentation updates to GitHub automatically. GitHub uploads happen only when Mira explicitly asks."

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "teach_correct_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            taught = pipeline.teach(
                old_policy,
                source="agent_training_v1/policy.md",
                agent_id="agent_teacher",
                store_session=True,
            )
            before = pipeline.ask(query, top_k=3, session_id=taught["session_id"], agent_id="agent_teacher", store_session=True)
            corrected = pipeline.correct(
                correction,
                target_memory_ids=[taught["memory"]["memory_id"]],
                target_query=query,
                top_k=3,
                source="agent_training_v2/corrections.md",
                session_id=taught["session_id"],
                agent_id="agent_teacher",
                store_session=True,
            )
            after = pipeline.ask(query, top_k=3, session_id=taught["session_id"], agent_id="agent_teacher", store_session=True)
            history = pipeline.db.session_history(taught["session_id"])
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    assert taught["memory"]["memory_id"]
    assert corrected["correction_memory"]["memory_id"]
    assert corrected["relations"]
    assert corrected["feedback"]
    assert corrected["target_memory_ids"][0] == taught["memory"]["memory_id"]
    assert after["current"][0]["memory_id"] == corrected["correction_memory"]["memory_id"]
    assert any(item["memory_id"] == taught["memory"]["memory_id"] for item in after["stale"])
    assert "must not push" in after["answer"].lower()
    assert stats["memories"] == 2
    assert stats["relations"] >= 1
    assert stats["retrieval_feedback"] >= 1
    assert stats["sessions"] == 1
    assert stats["session_turns"] >= 5

    print(
        json.dumps(
            {
                "ok": True,
                "before": {
                    "answer": before["answer"],
                    "current": before["current"],
                    "stale": before["stale"],
                },
                "corrected": corrected,
                "after": {
                    "answer": after["answer"],
                    "confidence": after["confidence"],
                    "conflict": after["conflict"],
                    "current": after["current"],
                    "stale": after["stale"],
                },
                "turn_count": len(history),
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
