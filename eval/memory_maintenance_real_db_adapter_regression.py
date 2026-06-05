from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_apply_backend import MemoryDBMaintenanceApplyStore, apply_memory_maintenance_plan  # noqa: E402
from core.maintenance_candidate_contract import build_manual_apply_decisions, build_manual_apply_plan  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)
from storage.db import MemoryDB  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
DB_PATH = OUT_DIR / "memory_maintenance_real_db_adapter_fixture.db"
OUT_JSON = OUT_DIR / "memory_maintenance_real_db_adapter_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_real_db_adapter_regression_report.md"
SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def setup_memory_db(path: Path) -> MemoryDB:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDB(path)
    db.init_schema(SCHEMA_PATH)
    rows = [
        ("dup_alpha_r1", "Alpha duplicate maintenance fixture should keep this canonical row."),
        ("dup_alpha_r2", "Alpha duplicate maintenance fixture should deprecate this duplicate row."),
        ("stale_beta_r1", "Beta stale fixture row one should not be touched by duplicate backend."),
        ("stale_beta_r2", "Beta stale fixture row two should not be touched by duplicate backend."),
    ]
    for memory_id, text in rows:
        db.conn.execute(
            """
            INSERT INTO memories (
                id, text, domain_id, memory_type, namespace, importance, stability, confidence,
                csd_score, surprise, recall_score, curiosity, focus, clc_state,
                created_at, updated_at, deprecated
            )
            VALUES (?, ?, 'maintenance_fixture', 'fact', 'global', 0.5, 0.0, 0.8,
                0.0, 0.0, 0.0, 0.0, 0.0, 'stored',
                '2026-06-04T00:00:00Z', '2026-06-04T00:00:00Z', 0)
            """,
            (memory_id, text),
        )
    db.conn.commit()
    return db


def deprecated_map(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    try:
        return {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT id, deprecated FROM memories ORDER BY id").fetchall()
        }
    finally:
        conn.close()


def audit_count(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_maintenance_apply_audit'"
        ).fetchone()
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM memory_maintenance_apply_audit").fetchone()[0])
    finally:
        conn.close()


def build_fixture_plan() -> dict:
    build_outcome_fixture()
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_JSON.read_text(encoding="utf-8"))
    decisions = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    return build_manual_apply_plan(decisions, dry_run=True, operator_id="real_db_adapter_regression")


def main() -> int:
    apply_plan = build_fixture_plan()

    db = setup_memory_db(DB_PATH)
    before_disabled = deprecated_map(DB_PATH)
    adapter = MemoryDBMaintenanceApplyStore(db, close_wrapped_db=True)
    disabled_result = apply_memory_maintenance_plan(
        adapter,
        apply_plan,
        operator_id="real_db_adapter_regression",
        operator_confirmed=True,
        mutation_enabled=False,
        dry_run=False,
        write_audit=True,
    )
    adapter.close()
    after_disabled = deprecated_map(DB_PATH)
    disabled_audit_count = audit_count(DB_PATH)

    db = setup_memory_db(DB_PATH)
    adapter = MemoryDBMaintenanceApplyStore(db, close_wrapped_db=True)
    enabled_result = apply_memory_maintenance_plan(
        adapter,
        apply_plan,
        operator_id="real_db_adapter_regression",
        operator_confirmed=True,
        mutation_enabled=True,
        dry_run=False,
        write_audit=True,
    )
    adapter.close()
    after_enabled = deprecated_map(DB_PATH)
    enabled_audit_count = audit_count(DB_PATH)
    enabled_event = ((enabled_result.get("results") or [{}])[0] or {}).get("audit_event") or {}

    checks = {
        "plan_has_duplicate_operation": apply_plan.get("duplicate_deprecation_operation_count") == 1,
        "real_db_disabled_preserves_rows": disabled_result.get("applied_count") == 0
        and before_disabled == after_disabled
        and disabled_audit_count == 1,
        "real_db_enabled_mutates_only_duplicate_fixture": enabled_result.get("applied_count") == 1
        and after_enabled.get("dup_alpha_r1") == 0
        and after_enabled.get("dup_alpha_r2") == 1
        and after_enabled.get("stale_beta_r1") == 0
        and after_enabled.get("stale_beta_r2") == 0
        and enabled_audit_count == 1,
        "real_db_enabled_audit_has_before_after": bool(enabled_event.get("before_memory_rows"))
        and bool(enabled_event.get("after_memory_rows")),
        "real_db_enabled_audit_has_rollback": bool((enabled_event.get("rollback") or {}).get("required")),
    }
    result = {
        "schema": "memory_maintenance_real_db_adapter_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "disabled_result": disabled_result,
        "enabled_result": enabled_result,
        "final_deprecated_map": after_enabled,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Real DB Adapter Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Final Deprecated Map", "", "```json", json.dumps(after_enabled, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
