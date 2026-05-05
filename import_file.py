from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.chunking import load_texts_from_file
from core.runtime import create_pipeline


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Import text, Markdown, JSON, or JSONL into the memory core")
    parser.add_argument("path", help="File to import")
    parser.add_argument("--max-words", type=int, default=120)
    parser.add_argument("--overlap-words", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.path)
    texts = load_texts_from_file(source_path, max_words=args.max_words, overlap_words=args.overlap_words)
    if args.limit is not None:
        texts = texts[: max(0, args.limit)]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "source": str(source_path),
                    "chunks": len(texts),
                    "preview": texts[:3],
                },
                indent=2,
            )
        )
        return

    pipeline = create_pipeline(ROOT, db_path=Path(args.db_path) if args.db_path else None)
    try:
        result = pipeline.ingest_batch(texts, source=str(source_path))
        print(json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
