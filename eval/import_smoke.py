from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chunking import load_texts_from_file
from core.config import load_config
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def main() -> None:
    sample = """# Memory Program Notes

The memory program should keep EmbeddingGemma loaded while ingesting many design notes.

CSD novelty scores should help decide whether a memory updates an existing domain or creates a new domain.

Retrieval should surface the notes that best match a user query, with error memories receiving a small boost.
"""
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "sample_notes.md"
        source.write_text(sample, encoding="utf-8")
        texts = load_texts_from_file(source, max_words=24, overlap_words=4)

        db_path = tmp_path / "import_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        config = load_config(ROOT)
        pipeline = MemoryPipeline(
            root=tmp_path,
            db_path=db_path,
            embedding_dim=int(config.get("embedding_dim") or 768),
            top_k=int(config.get("top_k") or 8),
            embedding_config=config.get("embedding"),
        )
        try:
            batch = pipeline.ingest_batch(texts, source=str(source))
            retrieved = pipeline.retrieve("novelty domain memory retrieval", top_k=3)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

        assert len(texts) >= 2
        assert batch["stored"] == len(texts)
        assert retrieved
        assert stats["vector_dimensions"] == [768]
        print(
            json.dumps(
                {
                    "ok": True,
                    "chunks": len(texts),
                    "stored": batch["stored"],
                    "stats": stats,
                    "top_result": retrieved[0]["memory_type"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
