from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_candidates import build_report  # noqa: E402


DB_PATH = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_fixture.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_regression_report.md"


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
        """
    )
    rows = [
        ("dup_a", "Cedar Map uses selector outcome logs for routing.", "project", 0.8, 0.9, "2026-05-01", [1.0, 0.0, 0.0, 0.0]),
        ("dup_b", "Cedar Map uses selector outcome logs for routing.", "project", 0.5, 0.7, "2026-05-02", [1.0, 0.0, 0.0, 0.0]),
        ("sem_a", "Victor prefers sparkling water in the morning.", "profile_semantic", 0.7, 0.8, "2026-05-03", [0.0, 1.0, 0.0, 0.0]),
        ("sem_b", "Victor prefers morning sparkling water.", "profile_semantic", 0.6, 0.7, "2026-05-04", [0.0, 0.98, 0.02, 0.0]),
        ("old_pref", "Old memory: Victor used to prefer espresso in the morning.", "profile_stale", 0.4, 0.6, "2026-04-01", [0.0, 0.8, 0.2, 0.0]),
        ("new_pref", "Victor currently prefers sparkling water in the morning.", "profile_stale", 0.9, 0.9, "2026-05-05", [0.0, 0.9, 0.1, 0.0]),
        ("other", "Robotics controller uses a torque safety limit.", "robotics", 0.8, 0.8, "2026-05-06", [0.0, 0.0, 1.0, 0.0]),
    ]
    for memory_id, text, domain, importance, confidence, created_at, embedding in rows:
        conn.execute(
            """
            INSERT INTO memories (id, text, domain_id, namespace, importance, confidence, created_at, updated_at, deprecated)
            VALUES (?, ?, ?, 'global', ?, ?, ?, ?, 0)
            """,
            (memory_id, text, domain, importance, confidence, created_at, created_at),
        )
        conn.execute(
            "INSERT INTO vectors (memory_id, embedding, dim) VALUES (?, ?, ?)",
            (memory_id, json.dumps(embedding).encode("utf-8"), len(embedding)),
        )
    conn.commit()
    conn.close()


def main() -> int:
    setup_db(DB_PATH)
    before = sqlite3.connect(str(DB_PATH)).execute("SELECT COUNT(*) FROM memories WHERE deprecated=1").fetchone()[0]
    report = build_report(DB_PATH, skip_geometry=True, semantic_threshold=0.90, jaccard_min=0.35)
    after = sqlite3.connect(str(DB_PATH)).execute("SELECT COUNT(*) FROM memories WHERE deprecated=1").fetchone()[0]
    actions = report.get("candidate_counts") or {}
    checks = {
        "schema_ok": report.get("schema") == "ogcf_maintenance_candidates/v1",
        "dry_run_only": report.get("mutates_db") is False and before == 0 and after == 0,
        "exact_duplicate_found": actions.get("exact_duplicate_group", 0) >= 1,
        "semantic_duplicate_found": actions.get("semantic_duplicate_group", 0) >= 1,
        "stale_candidate_found": actions.get("stale_version_candidate", 0) >= 1,
        "geometry_skipped": bool((report.get("geometry_summary") or {}).get("skipped")),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "db": str(DB_PATH),
        "candidate_counts": actions,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# OGCF Maintenance Candidate Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "\n".join(f"- {name}: `{ok}`" for name, ok in checks.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
