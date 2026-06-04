from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_candidate_guard import build_report  # noqa: E402
from eval.ogcf_maintenance_review_memory_bank import build_memory_bank  # noqa: E402
from eval.ogcf_maintenance_review_memory_bank_regression import write_fixture  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
BANK_JSON = OUT_DIR / "ogcf_maintenance_candidate_guard_fixture_bank.json"
OUT_JSON = OUT_DIR / "ogcf_maintenance_candidate_guard_regression_results.json"
OUT_MD = OUT_DIR / "ogcf_maintenance_candidate_guard_regression_report.md"


def main() -> int:
    bank = build_memory_bank(write_fixture(), top_k=3, min_runs=2, min_useful=2)
    BANK_JSON.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    report = build_report(BANK_JSON, min_runs=2, min_support=2, min_mean_priority=0.65)
    guarded_actions = {item.get("action") for item in report.get("guarded_candidates") or []}
    blocked_actions = {item.get("action") for item in report.get("blocked_candidates") or []}
    checks = {
        "schema_ok": report.get("schema") == "ogcf_maintenance_candidate_guard/v1",
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
        "promotion_still_blocked": report.get("promotion_ready") is False,
        "two_manual_review_candidates": report.get("manual_review_candidate_count") == 2,
        "exact_duplicate_guarded": "exact_duplicate_group" in guarded_actions,
        "stale_version_guarded": "stale_version_candidate" in guarded_actions,
        "negative_bridge_blocked": "bridge_cluster_review" in blocked_actions,
        "next_action_manual_review": report.get("next_action") == "manual_review_guarded_maintenance_candidates",
        "guarded_candidates_have_blockers": all(
            item.get("promotion_ready") is False and item.get("promotion_blockers")
            for item in report.get("guarded_candidates") or []
        ),
    }
    result = {
        "schema": "ogcf_maintenance_candidate_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "guard": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Candidate Guard Regression",
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
            "## Guard Summary",
            "",
            "```json",
            json.dumps(
                {
                    "manual_review_candidate_count": report.get("manual_review_candidate_count"),
                    "blocked_count": report.get("blocked_count"),
                    "readiness_counts": report.get("readiness_counts"),
                    "next_action": report.get("next_action"),
                    "promotion_ready": report.get("promotion_ready"),
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
