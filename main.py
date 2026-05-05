from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.config import load_config, resolve_project_path
from storage.db import MemoryDB


ROOT = Path(__file__).resolve().parent
CONFIG = load_config(ROOT)
DB_PATH = resolve_project_path(ROOT, CONFIG.get("database_path"), "memory.db")
SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_db() -> dict:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDB(DB_PATH)
    db.init_schema(SCHEMA_PATH)
    stats = db.stats()
    db.close()
    return {"database": str(DB_PATH), **stats}


def show_stats() -> dict:
    db = MemoryDB(DB_PATH)
    db.init_schema(SCHEMA_PATH)
    stats = db.stats()
    domains = [
        {
            "id": d.id,
            "name": d.name,
            "memory_count": d.memory_count,
            "effective_dimension": round(d.effective_dimension, 4),
            "drift_ema": round(d.drift_ema, 6),
            "curvature_ema": round(d.curvature_ema, 6),
            "stability": round(d.stability, 4),
        }
        for d in db.list_domains()
    ]
    sources = db.source_counts()
    feedback = db.feedback_counts()
    db.close()
    return {
        "database": str(DB_PATH),
        **stats,
        "domains_detail": domains,
        "sources_detail": sources,
        "feedback_detail": feedback,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CLC-CSD-GCL memory core")
    parser.add_argument("command", choices=["init", "stats"])
    args = parser.parse_args()
    payload = init_db() if args.command == "init" else show_stats()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
