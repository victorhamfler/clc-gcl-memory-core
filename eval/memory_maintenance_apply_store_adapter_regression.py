from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_apply_backend import apply_memory_maintenance_plan  # noqa: E402
from core.maintenance_candidate_contract import build_manual_apply_decisions, build_manual_apply_plan  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_apply_store_adapter_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_apply_store_adapter_regression_report.md"


class FakeMaintenanceApplyStore:
    def __init__(self) -> None:
        self.rows = {
            "dup_alpha_r1": {"id": "dup_alpha_r1", "text": "canonical duplicate fixture", "deprecated": 0},
            "dup_alpha_r2": {"id": "dup_alpha_r2", "text": "duplicate fixture", "deprecated": 0},
            "stale_beta_r1": {"id": "stale_beta_r1", "text": "stale fixture should not change", "deprecated": 0},
        }
        self.audit_events: list[dict[str, Any]] = []
        self.deprecated_calls: list[list[str]] = []
        self.commit_count = 0
        self.closed = False

    def fetch_memory_rows(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        return [deepcopy(self.rows[memory_id]) for memory_id in memory_ids if memory_id in self.rows]

    def mark_memories_deprecated(self, memory_ids: list[str], *, updated_at: str) -> None:
        self.deprecated_calls.append(list(memory_ids))
        for memory_id in memory_ids:
            if memory_id in self.rows:
                self.rows[memory_id]["deprecated"] = 1
                self.rows[memory_id]["updated_at"] = updated_at

    def write_apply_audit_event(self, event: dict[str, Any]) -> None:
        self.audit_events.append(deepcopy(event))

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        self.closed = True


def build_fixture_plan() -> dict[str, Any]:
    build_outcome_fixture()
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_JSON.read_text(encoding="utf-8"))
    decisions = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    return build_manual_apply_plan(decisions, dry_run=True, operator_id="adapter_regression")


def main() -> int:
    apply_plan = build_fixture_plan()

    dry_store = FakeMaintenanceApplyStore()
    before_dry = deepcopy(dry_store.rows)
    dry_result = apply_memory_maintenance_plan(
        dry_store,
        apply_plan,
        operator_id="adapter_regression",
        operator_confirmed=False,
        mutation_enabled=False,
        dry_run=True,
        write_audit=True,
    )

    enabled_store = FakeMaintenanceApplyStore()
    enabled_result = apply_memory_maintenance_plan(
        enabled_store,
        apply_plan,
        operator_id="adapter_regression",
        operator_confirmed=True,
        mutation_enabled=True,
        dry_run=False,
        write_audit=True,
    )
    enabled_event = enabled_store.audit_events[0] if enabled_store.audit_events else {}
    checks = {
        "plan_has_duplicate_operation": apply_plan.get("duplicate_deprecation_operation_count") == 1,
        "dry_store_preserves_rows": dry_result.get("applied_count") == 0 and dry_store.rows == before_dry,
        "dry_store_no_deprecated_call": dry_store.deprecated_calls == [],
        "dry_store_audit_and_commit": len(dry_store.audit_events) == 1 and dry_store.commit_count == 1,
        "enabled_store_deprecates_only_duplicate": enabled_result.get("applied_count") == 1
        and enabled_store.rows["dup_alpha_r1"]["deprecated"] == 0
        and enabled_store.rows["dup_alpha_r2"]["deprecated"] == 1
        and enabled_store.rows["stale_beta_r1"]["deprecated"] == 0,
        "enabled_store_used_adapter_call": enabled_store.deprecated_calls == [["dup_alpha_r2"]],
        "enabled_store_audit_has_rollback": bool((enabled_event.get("rollback") or {}).get("required")),
        "enabled_store_commit_once": enabled_store.commit_count == 1,
    }
    result = {
        "schema": "memory_maintenance_apply_store_adapter_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "dry_result": dry_result,
        "enabled_result": enabled_result,
        "final_fake_rows": enabled_store.rows,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Apply Store Adapter Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
