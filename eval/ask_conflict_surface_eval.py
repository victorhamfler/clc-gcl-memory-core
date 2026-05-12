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
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "ask_conflict_surface.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            old = pipeline.ingest(
                "Agent name is NovaDesk.",
                source="ask_conflict/old_name.md",
                namespace="agent:conflict",
            )
            new = pipeline.ingest(
                "Correction: the current agent name is LoomGuide, not NovaDesk.",
                source="ask_conflict/new_name.md",
                namespace="agent:conflict",
            )
            answer = pipeline.ask(
                "What is the current agent name?",
                namespace="agent:conflict",
                agent_id="conflict_agent",
                store_session=False,
                top_k=2,
            )
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    evidence_scores = [float(item.get("stored_contradiction_score") or 0.0) for item in answer["evidence"]]
    checks = {
        "ingest_stored_contradiction": new["contradiction"] >= 0.75 and stats["contradictions"] >= 1,
        "ask_surfaces_conflict": answer["conflict"] is True,
        "evidence_carries_stored_contradiction": max(evidence_scores or [0.0]) >= 0.75,
        "answer_prefers_current_name": "loomguide" in answer["answer"].lower(),
    }
    assert all(checks.values()), checks
    print(
        json.dumps(
            {
                "ok": True,
                "checks": checks,
                "old": old,
                "new": new,
                "answer": answer["answer"],
                "evidence": answer["evidence"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
