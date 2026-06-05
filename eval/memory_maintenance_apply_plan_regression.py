from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import (  # noqa: E402
    APPLY_PLAN_SCHEMA,
    build_manual_apply_decisions,
    build_manual_apply_plan,
)
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_apply_plan_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_apply_plan_regression_report.md"


def main() -> int:
    build_outcome_fixture()
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_JSON.read_text(encoding="utf-8"))
    decisions = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    report = build_manual_apply_plan(decisions, dry_run=True, operator_id="regression_operator")
    planned = report.get("planned_operations") or []
    blocked = report.get("blocked_operations") or []
    duplicate_operation = next(
        (item for item in planned if item.get("operation_kind") == "duplicate_deprecation"),
        {},
    )
    checks = {
        "schema_ok": report.get("schema") == APPLY_PLAN_SCHEMA,
        "source_decision_ok": report.get("source_apply_decision_ok") is True,
        "dry_run": report.get("dry_run") is True,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
        "one_duplicate_deprecation_planned": report.get("duplicate_deprecation_operation_count") == 1,
        "held_or_unsupported_blocked": report.get("blocked_operation_count") == 1,
        "no_ready_execute": report.get("ready_to_execute_count") == 0,
        "no_applied_count": report.get("applied_count") == 0,
        "duplicate_requires_operator_confirmation": "operator_confirmation_required"
        in (duplicate_operation.get("blocked_reasons") or []),
        "duplicate_requires_audit_and_rollback": bool(duplicate_operation.get("rollback", {}).get("required"))
        and bool(duplicate_operation.get("before_after_audit", {}).get("before_required"))
        and bool(duplicate_operation.get("before_after_audit", {}).get("after_required")),
        "blocked_never_mutates": all(item.get("mutates_db") is False and item.get("applied") is False for item in blocked),
        "promotion_blocked": report.get("promotion_ready") is False and bool(report.get("promotion_blockers")),
    }
    result = {
        "schema": "memory_maintenance_apply_plan_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "apply_plan": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Apply Plan Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Apply Plan Summary",
            "",
            "```json",
            json.dumps(
                {
                    "operation_count": report.get("operation_count"),
                    "planned_operation_count": report.get("planned_operation_count"),
                    "blocked_operation_count": report.get("blocked_operation_count"),
                    "ready_to_execute_count": report.get("ready_to_execute_count"),
                    "applied_count": report.get("applied_count"),
                    "next_action": report.get("next_action"),
                },
                indent=2,
            ),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
