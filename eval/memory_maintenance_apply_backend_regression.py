from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_apply_backend import apply_memory_maintenance_plan_to_sqlite  # noqa: E402
from core.maintenance_candidate_contract import build_manual_apply_decisions, build_manual_apply_plan  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)


OUT_DIR = REPO_ROOT / "experiments"
DB_PATH = OUT_DIR / "memory_maintenance_apply_backend_fixture.db"
OUT_JSON = OUT_DIR / "memory_maintenance_apply_backend_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_apply_backend_regression_report.md"


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
        """
    )
    rows = [
        ("dup_alpha_r1", "Alpha duplicate maintenance fixture should keep this canonical row.", 0),
        ("dup_alpha_r2", "Alpha duplicate maintenance fixture should deprecate this duplicate row.", 0),
        ("stale_beta_r1", "Beta stale fixture row one should not be touched by duplicate backend.", 0),
        ("stale_beta_r2", "Beta stale fixture row two should not be touched by duplicate backend.", 0),
    ]
    for memory_id, text, deprecated in rows:
        conn.execute(
            """
            INSERT INTO memories (id, text, domain_id, namespace, created_at, updated_at, deprecated)
            VALUES (?, ?, 'maintenance_fixture', 'global', '2026-06-04T00:00:00Z', '2026-06-04T00:00:00Z', ?)
            """,
            (memory_id, text, deprecated),
        )
    conn.commit()
    conn.close()


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
    return build_manual_apply_plan(decisions, dry_run=True, operator_id="backend_regression")


def main() -> int:
    apply_plan = build_fixture_plan()

    setup_db(DB_PATH)
    before_dry = deprecated_map(DB_PATH)
    dry_result = apply_memory_maintenance_plan_to_sqlite(
        DB_PATH,
        apply_plan,
        operator_id="backend_regression",
        operator_confirmed=False,
        mutation_enabled=False,
        dry_run=True,
        write_audit=True,
    )
    after_dry = deprecated_map(DB_PATH)
    dry_audit_count = audit_count(DB_PATH)

    setup_db(DB_PATH)
    disabled_result = apply_memory_maintenance_plan_to_sqlite(
        DB_PATH,
        apply_plan,
        operator_id="backend_regression",
        operator_confirmed=True,
        mutation_enabled=False,
        dry_run=False,
        write_audit=True,
    )
    after_disabled = deprecated_map(DB_PATH)
    disabled_audit_count = audit_count(DB_PATH)

    setup_db(DB_PATH)
    enabled_result = apply_memory_maintenance_plan_to_sqlite(
        DB_PATH,
        apply_plan,
        operator_id="backend_regression",
        operator_confirmed=True,
        mutation_enabled=True,
        dry_run=False,
        write_audit=True,
    )
    after_enabled = deprecated_map(DB_PATH)
    enabled_audit_count = audit_count(DB_PATH)
    enabled_event = ((enabled_result.get("results") or [{}])[0] or {}).get("audit_event") or {}

    checks = {
        "plan_has_one_duplicate_operation": apply_plan.get("duplicate_deprecation_operation_count") == 1,
        "dry_run_blocks_and_preserves_rows": dry_result.get("applied_count") == 0 and before_dry == after_dry,
        "dry_run_writes_non_applied_audit": dry_audit_count == 1,
        "confirmed_but_disabled_preserves_rows": disabled_result.get("applied_count") == 0
        and all(value == 0 for value in after_disabled.values())
        and disabled_audit_count == 1,
        "confirmed_enabled_mutates_only_duplicate": enabled_result.get("applied_count") == 1
        and after_enabled.get("dup_alpha_r1") == 0
        and after_enabled.get("dup_alpha_r2") == 1
        and after_enabled.get("stale_beta_r1") == 0
        and after_enabled.get("stale_beta_r2") == 0
        and enabled_audit_count == 1,
        "enabled_audit_has_before_after": bool(enabled_event.get("before_memory_rows"))
        and bool(enabled_event.get("after_memory_rows")),
        "enabled_audit_has_rollback": bool((enabled_event.get("rollback") or {}).get("required"))
        and bool((enabled_event.get("rollback") or {}).get("audit_event_id")),
    }
    result = {
        "schema": "memory_maintenance_apply_backend_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "dry_result": dry_result,
        "disabled_result": disabled_result,
        "enabled_result": enabled_result,
        "final_deprecated_map": after_enabled,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Apply Backend Regression",
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
