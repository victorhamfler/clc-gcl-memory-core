from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import load_config, resolve_project_path
from core.pipeline import MemoryPipeline


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve memories from the CLC-CSD-GCL memory core")
    parser.add_argument("query", nargs="+", help="Query text")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()
    config = load_config(ROOT)
    db_path = resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else resolve_project_path(ROOT, config.get("database_path"), "memory.db")
    pipeline = MemoryPipeline(
        ROOT,
        db_path,
        embedding_dim=int(config.get("embedding_dim") or 128),
        top_k=max(1, args.top_k),
        embedding_config=config.get("embedding"),
    )
    pipeline.db.init_schema(ROOT / "storage" / "schema.sql")
    try:
        result = pipeline.retrieve(" ".join(args.query), top_k=args.top_k)
        print(json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
