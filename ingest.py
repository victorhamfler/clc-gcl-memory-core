from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import load_config, resolve_project_path
from core.pipeline import MemoryPipeline
from core.runtime import runtime_embedding_config


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest text into the CLC-CSD-GCL memory core")
    parser.add_argument("text", nargs="+", help="Text to ingest")
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()
    config = load_config(ROOT)
    db_path = resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else resolve_project_path(ROOT, config.get("database_path"), "memory.db")
    pipeline = MemoryPipeline(
        ROOT,
        db_path,
        embedding_dim=int(config.get("embedding_dim") or 128),
        top_k=int(config.get("top_k") or 8),
        embedding_config=runtime_embedding_config(config),
    )
    pipeline.db.init_schema(ROOT / "storage" / "schema.sql")
    try:
        result = pipeline.ingest(" ".join(args.text))
        print(json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
