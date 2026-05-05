from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def timed(label: str, fn):
    start = time.perf_counter()
    result = fn()
    return label, result, time.perf_counter() - start


def main() -> None:
    config = load_config(ROOT)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "memory_gemma_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(
            root=root,
            db_path=db_path,
            embedding_dim=int(config.get("embedding_dim") or 768),
            top_k=int(config.get("top_k") or 8),
            embedding_config=config.get("embedding"),
        )
        try:
            steps = [
                timed(
                    "ingest_1",
                    lambda: pipeline.ingest(
                        "The memory program uses EmbeddingGemma vectors for semantic retrieval."
                    ),
                ),
                timed(
                    "ingest_2",
                    lambda: pipeline.ingest(
                        "G-CL anchor drift should update domain geometry after high-novelty memories."
                    ),
                ),
                timed(
                    "retrieve",
                    lambda: pipeline.retrieve("semantic retrieval memory geometry", top_k=2),
                ),
            ]
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

        assert stats["memories"] == 2
        assert stats["vector_dimensions"] == [768]
        assert stats["embedding_signature"]["backend"] == "wsl_llama_cpp"
        assert steps[-1][1]
        print(
            json.dumps(
                {
                    "ok": True,
                    "stats": stats,
                    "timings_sec": {label: round(elapsed, 6) for label, _, elapsed in steps},
                    "top_result": steps[-1][1][0]["memory_type"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
