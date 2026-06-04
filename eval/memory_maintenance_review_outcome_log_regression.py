from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import (  # noqa: E402
    OUTCOME_SCHEMA,
    OUTCOME_SUMMARY_SCHEMA,
    build_outcome_template,
    summarize_review_outcomes,
)
from eval.memory_maintenance_candidate_review_plan_regression import build_plan_fixture  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
PLAN_JSON = OUT_DIR / "memory_maintenance_review_outcome_log_fixture_plan.json"
OUTCOMES_JSON = OUT_DIR / "memory_maintenance_review_outcome_log_fixture_outcomes.json"
OUT_JSON = OUT_DIR / "memory_maintenance_review_outcome_log_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_review_outcome_log_regression_report.md"


def build_outcome_fixture() -> tuple[dict, dict, dict, dict]:
    plan = build_plan_fixture()
    PLAN_JSON.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    template = build_outcome_template(plan)
    items = plan.get("items") or []
    outcomes = {
        "schema": OUTCOME_SCHEMA,
        "source_plan_schema": plan.get("schema"),
        "outcomes": [
            {
                "candidate_id": items[0]["candidate_id"],
                "memory_review_kind": items[0]["memory_review_kind"],
                "outcome": "accept",
                "reviewer": "regression",
                "reason": "duplicate cleanup is useful",
                "apply_note": "manual apply path still disabled",
            },
            {
                "candidate_id": items[1]["candidate_id"],
                "memory_review_kind": items[1]["memory_review_kind"],
                "outcome": "needs_more_evidence",
                "reviewer": "regression",
                "reason": "stale candidate needs another source before applying",
                "apply_note": "",
            },
        ],
        "report_only": True,
        "mutates_db": False,
    }
    OUTCOMES_JSON.write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
    summary = summarize_review_outcomes(plan, outcomes)
    return plan, template, outcomes, summary


def main() -> int:
    plan, template, outcomes, summary = build_outcome_fixture()
    checks = {
        "template_schema_ok": template.get("schema") == OUTCOME_SCHEMA,
        "summary_schema_ok": summary.get("schema") == OUTCOME_SUMMARY_SCHEMA,
        "two_outcomes": summary.get("outcome_count") == 2,
        "known_outcomes": summary.get("known_outcome_count") == 2,
        "accept_count": summary.get("outcome_counts", {}).get("accept") == 1,
        "needs_more_evidence_count": summary.get("outcome_counts", {}).get("needs_more_evidence") == 1,
        "no_unknown_candidates": not summary.get("unknown_candidate_ids"),
        "no_invalid_outcomes": not summary.get("invalid_outcomes"),
        "promotion_blocked": summary.get("promotion_ready") is False and bool(summary.get("promotion_blockers")),
        "report_only": summary.get("report_only") is True
        and summary.get("mutates_db") is False
        and summary.get("mutates_runtime") is False
        and summary.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_review_outcome_log_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "summary": summary,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Review Outcome Log Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Summary", "", "```json", json.dumps({
        "outcome_count": summary.get("outcome_count"),
        "outcome_counts": summary.get("outcome_counts"),
        "readiness": summary.get("readiness"),
        "next_action": summary.get("next_action"),
        "promotion_ready": summary.get("promotion_ready"),
    }, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
