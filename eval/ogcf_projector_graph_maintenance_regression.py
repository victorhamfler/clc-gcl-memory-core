from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_candidates import build_report  # noqa: E402


DB_PATH = REPO_ROOT / "experiments" / "ogcf_projector_graph_maintenance_fixture.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_projector_graph_maintenance_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_projector_graph_maintenance_regression_report.md"


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
        ("dup_a", "Cedar Map uses selector outcome logs for routing.", "project", [3.0, 0.0, 0.0, 0.2, 0.0, 0.0]),
        ("dup_b", "Cedar Map uses selector outcome logs for routing.", "project", [2.95, 0.05, 0.0, 0.2, 0.0, 0.0]),
        ("sem_a", "Victor prefers sparkling water in the morning.", "profile", [0.0, 3.0, 0.0, 0.0, 0.2, 0.0]),
        ("sem_b", "Victor prefers morning sparkling water.", "profile", [0.0, 2.94, 0.04, 0.0, 0.2, 0.0]),
        ("old_pref", "Old memory: Victor used to prefer espresso in the morning.", "profile", [0.0, 2.4, 0.45, 0.0, 0.25, 0.0]),
        ("new_pref", "Victor currently prefers sparkling water in the morning.", "profile", [0.0, 2.8, 0.2, 0.0, 0.22, 0.0]),
        ("bridge_a", "Bridge memory connects CSD contradiction and G-CL domain curvature.", "bridge", [1.5, 1.5, 0.2, 0.4, 0.4, 0.0]),
        ("bridge_b", "Bridge memory connects selector policy and ERG projector graph review.", "bridge", [1.45, 1.45, 0.25, 0.45, 0.35, 0.0]),
        ("robot_a", "Robotics controller uses a torque safety limit.", "robotics", [0.0, 0.0, 3.0, 0.0, 0.0, 0.3]),
        ("robot_b", "Robotics controller checks actuator current.", "robotics", [0.0, 0.0, 2.9, 0.0, 0.0, 0.35]),
        ("style_a", "Assistant style should be concise and evidence-backed.", "style", [0.0, 0.0, 0.0, 3.0, 0.0, 0.2]),
        ("tool_a", "Tool results should be timestamped before memory write.", "tools", [0.0, 0.0, 0.0, 0.0, 3.0, 0.2]),
    ]
    for index, (memory_id, text, domain, embedding) in enumerate(rows):
        created = f"2026-06-04T12:{index:02d}:00"
        conn.execute(
            """
            INSERT INTO memories (id, text, domain_id, namespace, importance, confidence, created_at, updated_at, deprecated)
            VALUES (?, ?, ?, 'global', 0.7, 0.8, ?, ?, 0)
            """,
            (memory_id, text, domain, created, created),
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
    report = build_report(
        DB_PATH,
        n_clusters=4,
        rank_k=2,
        neighbors=4,
        random_baselines=2,
        semantic_threshold=0.90,
        jaccard_min=0.30,
        stale_jaccard_min=0.35,
        skip_geometry=False,
    )
    after = sqlite3.connect(str(DB_PATH)).execute("SELECT COUNT(*) FROM memories WHERE deprecated=1").fetchone()[0]
    candidates = report.get("candidates") or []
    annotated = [candidate for candidate in candidates if (candidate.get("projector_graph") or {}).get("cluster_ids")]
    prioritized = [candidate for candidate in annotated if (candidate.get("maintenance_priority") or {}).get("priority_score")]
    duplicate_or_stale = [
        candidate
        for candidate in annotated
        if candidate.get("action") in {"exact_duplicate_group", "semantic_duplicate_group", "stale_version_candidate"}
    ]
    bridge = [candidate for candidate in annotated if candidate.get("action") == "bridge_cluster_review"]
    graph_summary = (report.get("geometry_summary") or {}).get("projector_distance_summary") or {}
    priority_summary = report.get("maintenance_priority_summary") or {}
    checks = {
        "schema_ok": report.get("schema") == "ogcf_maintenance_candidates/v1",
        "dry_run_only": report.get("mutates_db") is False and before == 0 and after == 0,
        "geometry_ran": not bool((report.get("geometry_summary") or {}).get("skipped")),
        "projector_graph_summary_present": float(graph_summary.get("edge_count") or 0.0) > 0.0
        and float(graph_summary.get("mean_distance") or 0.0) > 0.0,
        "projector_graph_edges_present": bool((report.get("geometry_summary") or {}).get("projector_graph_edges")),
        "maintenance_candidates_annotated": len(annotated) >= 3,
        "maintenance_candidates_prioritized": len(prioritized) >= 3,
        "duplicate_or_stale_candidates_annotated": bool(duplicate_or_stale),
        "priority_is_report_only": all(
            (candidate.get("maintenance_priority") or {}).get("report_only") is True
            and (candidate.get("maintenance_priority") or {}).get("mutates_db") is False
            for candidate in prioritized
        ),
        "priority_uses_projector_graph_boost": any(
            float((candidate.get("maintenance_priority") or {}).get("projector_graph_boost") or 0.0) > 0.0
            for candidate in prioritized
        ),
        "priority_summary_present": priority_summary.get("schema") == "ogcf_maintenance_priority_summary/v1"
        and priority_summary.get("prioritized_candidate_count") == len(prioritized)
        and priority_summary.get("max_priority_score", 0.0) > 0.0,
        "priority_summary_has_next_action": priority_summary.get("readiness")
        in {"diagnostic_only", "ready_for_outcome_collection", "ready_for_review"}
        and bool(priority_summary.get("next_action")),
        "priority_summary_top_candidates": bool(priority_summary.get("top_candidate_ids")),
        "candidate_annotations_have_edges_or_anomaly": all(
            (candidate["projector_graph"].get("incident_edge_count", 0) > 0)
            or (candidate["projector_graph"].get("projector_graph_anomaly", 0.0) > 0.0)
            for candidate in duplicate_or_stale
        ),
        "bridge_candidates_remain_optional": True if not bridge else bridge[0]["projector_graph"].get("report_only") is True,
    }
    result = {
        "schema": "ogcf_projector_graph_maintenance_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "candidate_counts": report.get("candidate_counts"),
        "annotated_candidate_count": len(annotated),
        "prioritized_candidate_count": len(prioritized),
        "graph_summary": graph_summary,
        "priority_summary": priority_summary,
        "annotated_samples": annotated[:5],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "mutates_db": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Projector Graph Maintenance Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Graph Summary", "", "```json", json.dumps(graph_summary, indent=2), "```"])
    lines.extend(["", "## Priority Summary", "", "```json", json.dumps(priority_summary, indent=2), "```"])
    lines.extend(["", "## Annotated Samples", "", "```json", json.dumps(annotated[:5], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
