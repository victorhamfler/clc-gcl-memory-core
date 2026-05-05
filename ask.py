from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import load_config, resolve_project_path
from core.runtime import create_pipeline


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the memory core for an extractive answer with cited memories")
    parser.add_argument("query", nargs="+", help="Question text")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    parser.add_argument("--session-id", default=None, help="Continue an existing memory session")
    parser.add_argument("--agent-id", default="default", help="Agent id for stored session turns")
    parser.add_argument("--no-store-session", action="store_true", help="Do not store this ask/answer as a session turn")
    parser.add_argument("--remember", action="store_true", help="Also write the interaction summary as durable memory")
    parser.add_argument("--memory-text", default=None, help="Custom durable memory text when --remember is used")
    args = parser.parse_args()

    config = load_config(ROOT)
    db_path = (
        resolve_project_path(ROOT, args.db_path, "memory.db")
        if args.db_path
        else resolve_project_path(ROOT, config.get("database_path"), "memory.db")
    )
    pipeline = create_pipeline(ROOT, db_path=db_path)
    try:
        result = pipeline.ask(
            " ".join(args.query),
            top_k=args.top_k,
            session_id=args.session_id,
            agent_id=args.agent_id,
            store_session=not args.no_store_session,
            remember=args.remember,
            memory_text=args.memory_text,
        )
        print(json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
