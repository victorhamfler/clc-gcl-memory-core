from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB, encode_vector


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


OLD_SCHEMA = """
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    summary TEXT,
    domain_id TEXT,
    memory_type TEXT,
    importance REAL DEFAULT 0.5,
    stability REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.5,
    csd_score REAL DEFAULT 0.0,
    surprise REAL DEFAULT 0.0,
    recall_score REAL DEFAULT 0.0,
    curiosity REAL DEFAULT 0.0,
    focus REAL DEFAULT 0.0,
    clc_state TEXT,
    created_at TEXT,
    updated_at TEXT,
    last_recalled TEXT,
    deprecated INTEGER DEFAULT 0
);

CREATE TABLE vectors (
    memory_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    dim INTEGER NOT NULL
);

CREATE TABLE domains (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    anchor_vector BLOB,
    effective_dimension REAL DEFAULT 1.0,
    drift_ema REAL DEFAULT 0.0,
    drift_var REAL DEFAULT 0.0,
    curvature_ema REAL DEFAULT 0.0,
    stability REAL DEFAULT 0.0,
    memory_count INTEGER DEFAULT 0,
    previous_update_direction BLOB,
    created_at TEXT,
    updated_at TEXT
);
"""


def create_old_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(OLD_SCHEMA)
        embedding = [1.0] + [0.0] * 127
        conn.execute(
            """
            INSERT INTO domains (
                id, name, anchor_vector, effective_dimension, drift_ema,
                drift_var, curvature_ema, stability, memory_count,
                previous_update_direction, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("dom_legacy_gcl", "G-CL", encode_vector(embedding), 1.0, 0.0, 0.0, 0.0, 0.0, 1, None, "old", "old"),
        )
        conn.execute(
            """
            INSERT INTO memories (
                id, text, domain_id, memory_type, importance, stability, confidence,
                csd_score, surprise, recall_score, curiosity, focus, clc_state,
                created_at, updated_at, deprecated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem_legacy_gcl",
                "G-CL legacy memory: global anchors existed before namespace migration.",
                "dom_legacy_gcl",
                "semantic_note",
                0.5,
                0.0,
                0.55,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                "SPLIT_DOMAIN",
                "old",
                "old",
                0,
            ),
        )
        conn.execute("INSERT INTO vectors (memory_id, embedding, dim) VALUES (?, ?, ?)", ("mem_legacy_gcl", encode_vector(embedding), 128))
        conn.commit()
    finally:
        conn.close()


def columns(db: MemoryDB, table: str) -> set[str]:
    return {row["name"] for row in db.conn.execute(f"PRAGMA table_info({table})").fetchall()}


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "legacy_namespace_migration.db"
        create_old_db(db_path)

        db = MemoryDB(db_path)
        try:
            db.init_schema(SCHEMA_PATH)
            memory_columns = columns(db, "memories")
            domain_columns = columns(db, "domains")
            legacy_domain = db.get_domain("dom_legacy_gcl")
            legacy_memory = db.conn.execute("SELECT namespace FROM memories WHERE id='mem_legacy_gcl'").fetchone()
        finally:
            db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            alpha = pipeline.ingest(
                "G-CL migration eval: alpha namespace should create its own post-migration anchor.",
                source="G-CL_SKILL.md",
                namespace="agent:alpha",
            )
            global_lookup = pipeline.db.get_domain_by_name("G-CL", namespace="global")
            alpha_lookup = pipeline.db.get_domain_by_name("G-CL", namespace="agent:alpha")
            domains = pipeline.db.list_domains()
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    checks = {
        "memory_namespace_column_added": "namespace" in memory_columns,
        "domain_namespace_column_added": "namespace" in domain_columns,
        "legacy_memory_defaults_global": legacy_memory is not None and legacy_memory["namespace"] == "global",
        "legacy_domain_defaults_global": legacy_domain is not None and legacy_domain.namespace == "global",
        "new_agent_domain_created": alpha_lookup is not None and alpha_lookup.namespace == "agent:alpha",
        "global_domain_still_available": global_lookup is not None and global_lookup.id == "dom_legacy_gcl",
        "agent_domain_does_not_reuse_legacy_global": alpha["domain_id"] != "dom_legacy_gcl",
        "domain_namespace_filtering_works": {"global", "agent:alpha"} <= {domain.namespace for domain in domains if domain.name == "G-CL"},
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "alpha_ingest": alpha,
        "domains": [
            {
                "id": domain.id,
                "name": domain.name,
                "namespace": domain.namespace,
                "memory_count": domain.memory_count,
            }
            for domain in domains
        ],
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
