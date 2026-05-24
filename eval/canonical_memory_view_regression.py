from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.canonical_memory import build_canonical_view  # noqa: E402


DB_PATH = REPO_ROOT / "experiments" / "canonical_memory_view_fixture.db"
OUT_JSON = REPO_ROOT / "experiments" / "canonical_memory_view_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_memory_view_regression_report.md"


def setup_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            domain_id TEXT,
            namespace TEXT DEFAULT 'global',
            memory_type TEXT,
            importance REAL DEFAULT 0.5,
            confidence REAL DEFAULT 0.5,
            created_at TEXT,
            updated_at TEXT,
            deprecated INTEGER DEFAULT 0
        );
        CREATE TABLE vectors (
            memory_id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            dim INTEGER NOT NULL
        );
        CREATE TABLE memory_sources (
            memory_id TEXT PRIMARY KEY,
            source TEXT,
            chunk_index INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TEXT
        );
        """
    )
    rows = [
        ("dup_a", "Hermes uses canonical memory support counts.", "project", "run:a", 0.8, 0.9, [1.0, 0.0, 0.0, 0.0], "handover.md"),
        ("dup_b", "Hermes uses canonical memory support counts.", "project", "run:b", 0.7, 0.8, [1.0, 0.0, 0.0, 0.0], "handover.md"),
        ("para_a", "Victor prefers sparkling water in the morning.", "profile", "run:a", 0.7, 0.7, [0.0, 1.0, 0.0, 0.0], "profile.md"),
        ("para_b", "Victor prefers morning sparkling water.", "profile", "run:a", 0.6, 0.7, [0.0, 0.99, 0.01, 0.0], "profile.md"),
        ("conflict_a", "Live endpoint preserves metadata.", "system", "run:a", 0.8, 0.8, [0.0, 0.0, 1.0, 0.0], "system.md"),
        ("conflict_b", "Correction: live endpoint drops metadata.", "system", "run:a", 0.9, 0.9, [0.0, 0.0, 0.99, 0.01], "system.md"),
    ]
    for idx, (memory_id, text, domain, namespace, importance, confidence, embedding, source) in enumerate(rows):
        created = f"2026-05-24T10:{idx:02d}:00+00:00"
        conn.execute(
            """
            INSERT INTO memories (id, text, domain_id, namespace, memory_type, importance, confidence, created_at, updated_at, deprecated)
            VALUES (?, ?, ?, ?, 'fact', ?, ?, ?, ?, 0)
            """,
            (memory_id, text, domain, namespace, importance, confidence, created, created),
        )
        conn.execute(
            "INSERT INTO vectors (memory_id, embedding, dim) VALUES (?, ?, ?)",
            (memory_id, json.dumps(embedding).encode("utf-8"), len(embedding)),
        )
        conn.execute(
            "INSERT INTO memory_sources (memory_id, source, chunk_index, metadata, created_at) VALUES (?, ?, 0, '{}', ?)",
            (memory_id, source, created),
        )
    conn.commit()
    conn.close()


def main() -> int:
    setup_db(DB_PATH)
    view = build_canonical_view(DB_PATH, similarity_threshold=0.90, jaccard_min=0.30)
    top_duplicate = max(view["canonical_claims"], key=lambda claim: claim["support_count"])
    edge_counts = view["semantic_edge_counts"]
    checks = {
        "schema_ok": view["schema"] == "canonical_memory_view/v1",
        "dry_run_only": view["mutates_db"] is False,
        "duplicates_collapsed_to_support": view["row_count"] == 6
        and view["canonical_claim_count"] == 5
        and view["exact_duplicate_extra_row_count"] == 1,
        "support_metadata_preserved": top_duplicate["support_count"] == 2
        and len(top_duplicate["support_memory_ids"]) == 2
        and len(top_duplicate["namespace_counts"]) == 2
        and top_duplicate["source_counts"].get("handover.md") == 2,
        "clean_paraphrase_detected": edge_counts.get("clean_paraphrase", 0) >= 1,
        "conflict_update_detected": edge_counts.get("conflict_or_update", 0) >= 1,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "db": str(DB_PATH),
        "summary": {
            "row_count": view["row_count"],
            "canonical_claim_count": view["canonical_claim_count"],
            "exact_duplicate_extra_row_count": view["exact_duplicate_extra_row_count"],
            "semantic_edge_counts": edge_counts,
        },
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical Memory View Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
