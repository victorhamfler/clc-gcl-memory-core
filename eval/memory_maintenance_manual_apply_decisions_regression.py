from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import APPLY_DECISION_SCHEMA, build_manual_apply_decisions  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_manual_apply_decisions_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_manual_apply_decisions_regression_report.md"


def main() -> int:
    build_outcome_fixture()
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_JSON.read_text(encoding="utf-8"))
    report = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    decisions = {item.get("outcome"): item for item in report.get("decisions") or []}
    checks = {
        "schema_ok": report.get("schema") == APPLY_DECISION_SCHEMA,
        "dry_run": report.get("dry_run") is True,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
        "two_decisions": report.get("decision_count") == 2,
        "one_ready_for_manual_apply": report.get("ready_for_manual_apply_count") == 1,
        "one_held": report.get("held_count") == 1,
        "accept_is_ready": (decisions.get("accept") or {}).get("decision") == "ready_for_manual_apply",
        "needs_more_evidence_is_held": (decisions.get("needs_more_evidence") or {}).get("decision")
        == "hold_for_more_evidence",
        "no_applied_count": report.get("applied_count") == 0,
        "promotion_blocked": report.get("promotion_ready") is False and bool(report.get("promotion_blockers")),
    }
    result = {
        "schema": "memory_maintenance_manual_apply_decisions_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "manual_apply_decisions": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Manual Apply Decisions Regression",
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
            "## Decision Summary",
            "",
            "```json",
            json.dumps(
                {
                    "decision_count": report.get("decision_count"),
                    "ready_for_manual_apply_count": report.get("ready_for_manual_apply_count"),
                    "held_count": report.get("held_count"),
                    "next_action": report.get("next_action"),
                    "applied_count": report.get("applied_count"),
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
