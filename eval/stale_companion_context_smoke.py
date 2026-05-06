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


def make_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def run() -> dict:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = make_pipeline(root, root / "stale_companion_context.db")
        try:
            old = pipeline.teach(
                "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment.",
                source="smoke/project_label_v1.md",
                agent_id="stale_context_smoke",
                store_session=False,
            )
            old_id = old["memory"]["memory_id"]
            correction = pipeline.correct(
                "Cerulean Keystone was renamed Amber Compass for the adaptive memory brain experiment.",
                target_memory_ids=[old_id],
                target_query="What should I remember about Cerulean Keystone?",
                source="smoke/project_label_v2.md",
                agent_id="stale_context_smoke",
                store_session=False,
            )
            current_id = correction["correction_memory"]["memory_id"]
            answer = pipeline.ask(
                "What should I remember about Cerulean Keystone now?",
                top_k=1,
                agent_id="stale_context_smoke",
                store_session=False,
            )
            stale_context = answer.get("stale_context") or []
            ok = (
                answer["conflict"] is True
                and any(item.get("memory_id") == old_id for item in stale_context)
                and any(item.get("memory_id") == current_id for item in answer.get("evidence", []))
                and "superseded context" in answer["answer"].lower()
            )
            return {
                "ok": ok,
                "old_memory_id": old_id,
                "current_memory_id": current_id,
                "answer": answer["answer"],
                "conflict": answer["conflict"],
                "evidence": answer.get("evidence", []),
                "stale_context": stale_context,
            }
        finally:
            pipeline.close()


def main() -> None:
    payload = run()
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
