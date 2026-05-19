from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serve  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def create_hash_pipeline(root: Path, db_path: Path | None = None) -> MemoryPipeline:
    if db_path is None:
        db_path = root / "correct_metadata_passthrough.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def main() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "correct_metadata_passthrough.db"
        original_create_pipeline = serve.create_pipeline
        serve.create_pipeline = create_hash_pipeline
        api = serve.MemoryApi(ROOT, db_path=db_path)
        try:
            taught = api.teach(
                {
                    "text": "Hermes correction metadata regression target: Cedar Map is disabled.",
                    "agent_id": "hermes",
                    "namespace": "agent:hermes",
                    "domain": "agent_memory",
                    "memory_type": "semantic_note",
                    "store_session": False,
                },
            )
            corrected = api.correct(
                {
                    "correction": "Hermes correction metadata regression target: Cedar Map is enabled.",
                    "target_memory_id": taught["memory"]["memory_id"],
                    "target_query": "Cedar Map enabled",
                    "agent_id": "hermes",
                    "namespace": "agent:hermes",
                    "domain": "agent_memory",
                    "memory_type": "semantic_note",
                    "store_session": False,
                },
            )
        finally:
            api.close()
            serve.create_pipeline = original_create_pipeline

    correction_memory = corrected["correction_memory"]
    checks = {
        "teach_ok": taught["ok"] is True,
        "correct_ok": corrected["ok"] is True,
        "correction_linked": corrected["linked"] is True,
        "domain_preserved": correction_memory["domain_name"] == "agent_memory",
        "memory_type_preserved": correction_memory["memory_type"] == "semantic_note",
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "target_memory": taught["memory"],
        "correction_memory": correction_memory,
        "relations": corrected["relations"],
    }
    print(json.dumps(payload, indent=2), flush=True)
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
