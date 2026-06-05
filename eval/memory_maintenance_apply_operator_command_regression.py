from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import build_manual_apply_decisions, build_manual_apply_plan  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)
from storage.db import MemoryDB  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
DB_PATH = OUT_DIR / "memory_maintenance_apply_operator_command_fixture.db"
PLAN_JSON_OUT = OUT_DIR / "memory_maintenance_apply_operator_command_fixture_plan.json"
DEFAULT_RESULT_JSON = OUT_DIR / "memory_maintenance_apply_operator_command_default_results.json"
ENABLED_RESULT_JSON = OUT_DIR / "memory_maintenance_apply_operator_command_enabled_results.json"
OUT_JSON = OUT_DIR / "memory_maintenance_apply_operator_command_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_apply_operator_command_regression_report.md"
SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def setup_memory_db(path: Path) -> None:
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
    db.close()


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
    apply_plan = build_manual_apply_plan(decisions, dry_run=True, operator_id="operator_command_regression")
    PLAN_JSON_OUT.write_text(json.dumps(apply_plan, indent=2), encoding="utf-8")
    return apply_plan


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "eval" / "memory_maintenance_apply_operator_command.py"), *args],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )


def main() -> int:
    apply_plan = build_fixture_plan()

    setup_memory_db(DB_PATH)
    before_default = deprecated_map(DB_PATH)
    default_proc = run_command(
        "--db",
        str(DB_PATH),
        "--apply-plan",
        str(PLAN_JSON_OUT),
        "--operator-id",
        "operator_command_regression",
        "--write-audit",
        "--out-json",
        str(DEFAULT_RESULT_JSON),
    )
    after_default = deprecated_map(DB_PATH)
    default_audit_count = audit_count(DB_PATH)
    default_result = json.loads(DEFAULT_RESULT_JSON.read_text(encoding="utf-8"))

    setup_memory_db(DB_PATH)
    enabled_proc = run_command(
        "--db",
        str(DB_PATH),
        "--apply-plan",
        str(PLAN_JSON_OUT),
        "--operator-id",
        "operator_command_regression",
        "--confirm-operator",
        "--enable-mutation",
        "--no-dry-run",
        "--write-audit",
        "--out-json",
        str(ENABLED_RESULT_JSON),
    )
    after_enabled = deprecated_map(DB_PATH)
    enabled_audit_count = audit_count(DB_PATH)
    enabled_result = json.loads(ENABLED_RESULT_JSON.read_text(encoding="utf-8"))
    checks = {
        "plan_has_duplicate_operation": apply_plan.get("duplicate_deprecation_operation_count") == 1,
        "default_command_exits_ok": default_proc.returncode == 0,
        "default_command_preserves_rows": default_result.get("applied_count") == 0
        and before_default == after_default
        and default_audit_count == 1,
        "default_command_is_blocked": default_result.get("blocked_count") == 1
        and default_result.get("safety_mode") == "report_only_or_blocked",
        "enabled_command_exits_ok": enabled_proc.returncode == 0,
        "enabled_command_mutates_only_duplicate_fixture": enabled_result.get("applied_count") == 1
        and after_enabled.get("dup_alpha_r1") == 0
        and after_enabled.get("dup_alpha_r2") == 1
        and after_enabled.get("stale_beta_r1") == 0
        and after_enabled.get("stale_beta_r2") == 0
        and enabled_audit_count == 1,
        "enabled_command_requires_explicit_flags": enabled_result.get("safety_mode") == "mutation_enabled"
        and enabled_result.get("operator_confirmed") is True
        and enabled_result.get("mutation_enabled") is True
        and enabled_result.get("dry_run") is False,
    }
    result = {
        "schema": "memory_maintenance_apply_operator_command_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "default_stdout": default_proc.stdout,
        "default_stderr": default_proc.stderr,
        "enabled_stdout": enabled_proc.stdout,
        "enabled_stderr": enabled_proc.stderr,
        "default_result": default_result,
        "enabled_result": enabled_result,
        "final_deprecated_map": after_enabled,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Apply Operator Command Regression",
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
