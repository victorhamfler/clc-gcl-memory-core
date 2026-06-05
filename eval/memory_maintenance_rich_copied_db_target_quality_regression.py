from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from storage.db import MemoryDB  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
WORK_DIR = Path("E:/projcod2_artifacts_archive/current_rehearsals/rich_target_quality")
if not Path("E:/").exists():
    WORK_DIR = OUT_DIR / "memory_maintenance_rich_copied_db_target_quality"
SOURCE_DB = WORK_DIR / "rich_target_quality_source.db"
PLAN_JSON = WORK_DIR / "rich_target_quality_apply_plan.json"
REHEARSAL_JSON = WORK_DIR / "rich_target_quality_rehearsal_results.json"
OUT_JSON = OUT_DIR / "memory_maintenance_rich_copied_db_target_quality_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rich_copied_db_target_quality_regression_report.md"
SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def setup_rich_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDB(path)
    db.init_schema(SCHEMA_PATH)
    rows = [
        ("dup_keep", "Rich rehearsal duplicate fact: Victor stores alpha route in memory.", "project", "fact"),
        ("dup_extra", "Rich rehearsal duplicate fact: Victor stores alpha route in memory.", "project", "fact"),
        ("stale_keep", "Current rich rehearsal fact: Victor now uses beta route.", "profile_current", "fact"),
        ("stale_old", "Stale rich rehearsal fact: Victor used alpha route before the update.", "profile_stale", "stale_fact"),
        ("bridge_note", "Bridge rehearsal note connects routing and calendar memories.", "bridge_cluster", "bridge_note"),
        ("semantic_note", "Semantic rehearsal paraphrase is related but not exact duplicate text.", "project", "semantic_duplicate"),
    ]
    for memory_id, text, domain_id, memory_type in rows:
        db.conn.execute(
            """
            INSERT INTO memories (
                id, text, domain_id, memory_type, namespace, importance, stability, confidence,
                csd_score, surprise, recall_score, curiosity, focus, clc_state,
                created_at, updated_at, deprecated
            )
            VALUES (?, ?, ?, ?, 'global', 0.5, 0.0, 0.8,
                0.0, 0.0, 0.0, 0.0, 0.0, 'stored',
                '2026-06-04T00:00:00Z', '2026-06-04T00:00:00Z', 0)
            """,
            (memory_id, text, domain_id, memory_type),
        )
    db.conn.commit()
    db.close()


def write_apply_plan(path: Path) -> dict:
    plan = {
        "schema": "memory_maintenance_apply_plan/v1",
        "source_apply_decision_schema": "synthetic_rich_target_quality/v1",
        "source_apply_decision_ok": True,
        "operation_count": 2,
        "planned_operation_count": 2,
        "duplicate_deprecation_operation_count": 2,
        "blocked_operation_count": 0,
        "ready_to_execute_count": 0,
        "applied_count": 0,
        "planned_operations": [
            {
                "schema": "memory_maintenance_apply_operation/v1",
                "candidate_id": "rich:exact_duplicate:alpha_route",
                "operation_kind": "duplicate_deprecation",
                "memory_review_kind": "duplicate_deprecation_review",
                "keeper_memory_id": "dup_keep",
                "deprecate_memory_ids": ["dup_extra"],
                "operator_confirmation_required": True,
                "operator_confirmed": False,
                "dry_run": True,
                "ready_to_execute": False,
                "applied": False,
                "mutates_db": False,
            },
            {
                "schema": "memory_maintenance_apply_operation/v1",
                "candidate_id": "rich:unsafe_stale_as_duplicate",
                "operation_kind": "duplicate_deprecation",
                "memory_review_kind": "duplicate_deprecation_review",
                "keeper_memory_id": "stale_keep",
                "deprecate_memory_ids": ["stale_old"],
                "operator_confirmation_required": True,
                "operator_confirmed": False,
                "dry_run": True,
                "ready_to_execute": False,
                "applied": False,
                "mutates_db": False,
            },
        ],
        "blocked_operations": [],
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def deprecated_map(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    try:
        return {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT id, deprecated FROM memories ORDER BY id").fetchall()
        }
    finally:
        conn.close()


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    setup_rich_db(SOURCE_DB)
    before = deprecated_map(SOURCE_DB)
    write_apply_plan(PLAN_JSON)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "eval" / "memory_maintenance_copied_db_rehearsal.py"),
            "--source-db",
            str(SOURCE_DB),
            "--apply-plan",
            str(PLAN_JSON),
            "--work-dir",
            str(WORK_DIR),
            "--operator-id",
            "rich_target_quality_regression",
            "--out-json",
            str(REHEARSAL_JSON),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    after = deprecated_map(SOURCE_DB)
    report = json.loads(REHEARSAL_JSON.read_text(encoding="utf-8"))
    quality = report.get("target_quality") or {}
    review_summary = report.get("review_summary") or {}
    rpg_annotations = report.get("rpg_rehearsal_annotations") or {}
    operations = {item.get("candidate_id"): item for item in quality.get("operations") or []}
    reviews = {item.get("candidate_id"): item for item in review_summary.get("reviews") or []}
    rpg_ops = {item.get("candidate_id"): item for item in rpg_annotations.get("operation_annotations") or []}
    unsafe = operations.get("rich:unsafe_stale_as_duplicate") or {}
    safe = operations.get("rich:exact_duplicate:alpha_route") or {}
    safe_rpg = rpg_ops.get("rich:exact_duplicate:alpha_route") or {}
    unsafe_rpg = rpg_ops.get("rich:unsafe_stale_as_duplicate") or {}
    checks = {
        "command_reports_quality_failure": proc.returncode == 1 and report.get("ok") is False,
        "source_db_unchanged": before == after,
        "safe_duplicate_passes_exact_quality": safe.get("exact_duplicate_target") is True and not safe.get("risk_flags"),
        "unsafe_stale_candidate_flagged": unsafe.get("exact_duplicate_target") is False
        and "stale_marker" in (unsafe.get("risk_flags") or [])
        and "duplicate_text_mismatch" in (unsafe.get("risk_flags") or []),
        "target_ids_all_exist": quality.get("all_targets_present") is True,
        "candidate_target_quality_blocks_plan": quality.get("candidate_target_quality_ok") is False,
        "review_summary_blocks_plan": review_summary.get("overall_decision") == "blocked_or_needs_review",
        "rpg_annotations_available": rpg_annotations.get("schema") == "memory_maintenance_rpg_rehearsal_annotations/v1"
        and rpg_annotations.get("available") is True
        and rpg_annotations.get("report_only") is True
        and rpg_annotations.get("mutates_db") is False,
        "rpg_operation_annotations_present": set(rpg_ops) == {
            "rich:exact_duplicate:alpha_route",
            "rich:unsafe_stale_as_duplicate",
        },
        "rpg_safe_duplicate_has_stronger_target_relation": float(safe_rpg.get("target_mean_relation") or 0.0)
        > float(unsafe_rpg.get("target_mean_relation") or 0.0),
        "rpg_unsafe_stale_carries_risk_flags": "stale_marker" in (unsafe_rpg.get("risk_flags") or [])
        and "duplicate_text_mismatch" in (unsafe_rpg.get("risk_flags") or []),
        "safe_review_label": (reviews.get("rich:exact_duplicate:alpha_route") or {}).get("decision") == "safe_to_review",
        "unsafe_review_label": (reviews.get("rich:unsafe_stale_as_duplicate") or {}).get("decision")
        == "blocked_stale_risk",
        "rehearsal_rows_unchanged": bool((report.get("checks") or {}).get("rows_unchanged")),
        "work_dir_preferably_off_c": str(WORK_DIR).lower().startswith("e:") if Path("E:/").exists() else True,
    }
    result = {
        "schema": "memory_maintenance_rich_copied_db_target_quality_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "rehearsal_report": report,
        "source_deprecated_before": before,
        "source_deprecated_after": after,
        "report_only": True,
        "mutates_source_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rich Copied DB Target Quality Regression",
        "",
        f"Passed: **{result['ok']}**",
        f"Work dir: `{WORK_DIR}`",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD), "work_dir": str(WORK_DIR)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
