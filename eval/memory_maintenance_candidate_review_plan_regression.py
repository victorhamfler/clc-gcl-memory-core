from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import PLAN_SCHEMA, build_review_plan  # noqa: E402
from eval.ogcf_maintenance_candidate_guard import build_report as build_guard  # noqa: E402
from eval.ogcf_maintenance_review_memory_bank import build_memory_bank  # noqa: E402
from eval.ogcf_maintenance_review_memory_bank_regression import write_fixture  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
BANK_JSON = OUT_DIR / "memory_maintenance_review_plan_fixture_bank.json"
GUARD_JSON = OUT_DIR / "memory_maintenance_review_plan_fixture_guard.json"
OUT_JSON = OUT_DIR / "memory_maintenance_candidate_review_plan_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_candidate_review_plan_regression_report.md"


def build_plan_fixture() -> dict:
    bank = build_memory_bank(write_fixture(), top_k=3, min_runs=2, min_useful=2)
    BANK_JSON.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    guard = build_guard(BANK_JSON, min_runs=2, min_support=2, min_mean_priority=0.65)
    GUARD_JSON.write_text(json.dumps(guard, indent=2), encoding="utf-8")
    return build_review_plan(guard)


def main() -> int:
    plan = build_plan_fixture()
    kinds = plan.get("memory_review_kind_counts") or {}
    blocked_kinds = plan.get("blocked_review_kind_counts") or {}
    checks = {
        "schema_ok": plan.get("schema") == PLAN_SCHEMA,
        "source_guard_ok": plan.get("source_guard_ok") is True,
        "report_only": plan.get("report_only") is True
        and plan.get("mutates_db") is False
        and plan.get("mutates_runtime") is False
        and plan.get("mutates_config") is False,
        "promotion_blocked": plan.get("promotion_ready") is False and bool(plan.get("promotion_blockers")),
        "two_review_items": plan.get("candidate_count") == 2,
        "duplicate_kind_present": kinds.get("duplicate_deprecation_review") == 1,
        "stale_kind_present": kinds.get("stale_deprecation_review") == 1,
        "bridge_blocked": blocked_kinds.get("bridge_split_or_canonicalization_review") == 1,
        "next_action_manual_review": plan.get("next_action") == "manual_review_memory_maintenance_candidates",
    }
    result = {
        "schema": "memory_maintenance_candidate_review_plan_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "plan": plan,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Candidate Review Plan Regression",
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
            "## Plan Summary",
            "",
            "```json",
            json.dumps(
                {
                    "candidate_count": plan.get("candidate_count"),
                    "blocked_count": plan.get("blocked_count"),
                    "memory_review_kind_counts": plan.get("memory_review_kind_counts"),
                    "blocked_review_kind_counts": plan.get("blocked_review_kind_counts"),
                    "next_action": plan.get("next_action"),
                    "promotion_ready": plan.get("promotion_ready"),
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
