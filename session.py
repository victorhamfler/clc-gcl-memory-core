from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.chunking import load_texts_from_file
from core.config import resolve_project_path
from core.runtime import create_pipeline, pipeline_stats


ROOT = Path(__file__).resolve().parent


HELP = """Commands:
  ingest <text>
  import <path>
  retrieve <query>
  stats
  help
  exit
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive long-running CLC-CSD-GCL memory session")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()

    pipeline = create_pipeline(ROOT, db_path=resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else None)
    print("CLC-CSD-GCL memory session ready. Type help for commands.")
    try:
        while True:
            try:
                line = input("memory> ").strip()
            except EOFError:
                break
            if not line:
                continue
            command, _, rest = line.partition(" ")
            command = command.lower()
            try:
                if command in ("exit", "quit"):
                    break
                if command == "help":
                    print(HELP)
                elif command == "stats":
                    print(json.dumps(pipeline_stats(pipeline), indent=2))
                elif command == "ingest":
                    if not rest.strip():
                        print(json.dumps({"error": "ingest requires text"}, indent=2))
                        continue
                    print(json.dumps(pipeline.ingest(rest.strip()), indent=2))
                elif command == "import":
                    if not rest.strip():
                        print(json.dumps({"error": "import requires a file path"}, indent=2))
                        continue
                    path = Path(rest.strip().strip('"'))
                    texts = load_texts_from_file(path)
                    print(json.dumps(pipeline.ingest_batch(texts, source=str(path)), indent=2))
                elif command in ("retrieve", "search"):
                    if not rest.strip():
                        print(json.dumps({"error": "retrieve requires a query"}, indent=2))
                        continue
                    print(json.dumps({"results": pipeline.retrieve(rest.strip(), top_k=args.top_k)}, indent=2))
                else:
                    print(json.dumps({"error": f"unknown command: {command}"}, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
