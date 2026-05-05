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
        db_path = root / "memory.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(
            root=root,
            db_path=db_path,
            embedding_config={"backend": "hash", "dim": 128},
        )
        first = pipeline.ingest(
            "The CLC kernel should control novelty while G-CL updates memory geometry anchors."
        )
        second = pipeline.ingest(
            "ctypes OverflowError int too long to convert means the callback pointer signature should be checked."
        )
        results = pipeline.retrieve("memory geometry controller", top_k=2)
        stats = pipeline.db.stats()
        pipeline.close()

        assert first["memory_id"].startswith("mem_")
        assert second["memory_id"].startswith("mem_")
        assert stats["memories"] == 2
        assert stats["domains"] >= 1
        assert results

        print(
            json.dumps(
                {
                    "ok": True,
                    "stats": stats,
                    "first_state": first["clc_state"],
                    "second_state": second["clc_state"],
                    "top_result": results[0]["memory_type"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
