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
        db_path = root / "correction_target_validation.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            alpha = pipeline.teach(
                "Alpha correction target memory: deployment approval requires Victor.",
                namespace="agent:alpha",
                agent_id="alpha",
                store_session=False,
            )
            beta = pipeline.teach(
                "Beta correction target memory: deployment approval requires Mira.",
                namespace="agent:beta",
                agent_id="beta",
                store_session=False,
            )
            valid = pipeline.correct(
                "Deployment approval requires Victor and a passing smoke test.",
                target_memory_ids=[alpha["memory"]["memory_id"]],
                namespace="agent:alpha",
                agent_id="alpha",
                store_session=False,
            )
            missing_error = None
            wrong_namespace_error = None
            try:
                pipeline.correct(
                    "This should not create an orphan relation.",
                    target_memory_ids=["mem_does_not_exist"],
                    namespace="agent:alpha",
                    agent_id="alpha",
                    store_session=False,
                )
            except ValueError as exc:
                missing_error = str(exc)
            try:
                pipeline.correct(
                    "This should not correct another agent's private memory.",
                    target_memory_ids=[beta["memory"]["memory_id"]],
                    namespace="agent:alpha",
                    agent_id="alpha",
                    store_session=False,
                )
            except ValueError as exc:
                wrong_namespace_error = str(exc)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    checks = {
        "valid_target_links": valid["linked"] is True and valid["target_memory_ids"] == [alpha["memory"]["memory_id"]],
        "missing_id_rejected": missing_error is not None and "Unknown or out-of-scope" in missing_error,
        "wrong_namespace_rejected": wrong_namespace_error is not None and "Unknown or out-of-scope" in wrong_namespace_error,
        "invalid_corrections_not_stored": stats["memories"] == 3,
    }
    assert all(checks.values()), checks
    print(
        json.dumps(
            {
                "ok": True,
                "checks": checks,
                "missing_error": missing_error,
                "wrong_namespace_error": wrong_namespace_error,
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
