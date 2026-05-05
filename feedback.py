from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import load_config, resolve_project_path
from core.runtime import init_db
from storage.db import MemoryDB


ROOT = Path(__file__).resolve().parent
DEFAULT_RATINGS = {
    "excellent": 2.0,
    "useful": 1.0,
    "good": 1.0,
    "ok": 0.25,
    "neutral": 0.0,
    "missing_source": -0.5,
    "wrong_domain": -0.75,
    "stale": -0.75,
    "wrong": -1.0,
    "bad": -1.0,
}


def configured_db_path(db_path: str | None) -> Path:
    config = load_config(ROOT)
    if db_path:
        return resolve_project_path(ROOT, db_path, "memory.db")
    return resolve_project_path(ROOT, config.get("database_path"), "memory.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record retrieval feedback for one memory result")
    parser.add_argument("memory_id", help="Memory id returned by retrieve.py or POST /retrieve")
    parser.add_argument("label", help="Feedback label, such as useful, wrong, wrong_domain, stale, or excellent")
    parser.add_argument("--query", default=None)
    parser.add_argument("--rating", type=float, default=None)
    parser.add_argument("--rank", type=int, default=None)
    parser.add_argument("--retrieval-score", type=float, default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()

    db_path = configured_db_path(args.db_path)
    init_db(ROOT, db_path)
    db = MemoryDB(db_path)
    try:
        label = args.label.strip().lower()
        rating = args.rating if args.rating is not None else DEFAULT_RATINGS.get(label, 0.0)
        result = db.add_retrieval_feedback(
            memory_id=args.memory_id,
            label=label,
            query=args.query,
            rating=rating,
            rank=args.rank,
            retrieval_score=args.retrieval_score,
            notes=args.notes,
        )
        print(json.dumps({"ok": True, "feedback": result, "database": str(db_path)}, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
