from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_recurring_holdout import build_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_recurring_holdout_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_recurring_holdout_regression_report.md"
MULTIRUN_JSON = REPO_ROOT / "experiments" / "controller_packet_recurring_holdout_regression_multirun.json"


def write_fixture() -> None:
    artifact = {
        "schema": "controller_packet_multirun_calibration/v1",
        "description": "fixture",
        "ok": True,
        "run_count": 2,
        "min_runs": 2,
        "runs": [
            {"run_index": 1, "ok": True, "packet_count": 12, "proposal_count": 3},
            {"run_index": 2, "ok": True, "packet_count": 12, "proposal_count": 3},
        ],
        "proposal_cluster_count": 3,
        "recurring_cluster_count": 3,
        "guard_readiness_tier_counts": {"evidence_ready_blocked_by_related_review": 2, "review_evidence": 2},
        "bridge_holdout": {"observed_run_count": 2, "average_match_rate": 1.0, "all_clean": True},
        "bridge_leave_one_source_out": {
            "observed_run_count": 2,
            "candidate_run_count": 0,
            "max_source_count": 2,
            "max_sample_count": 12,
            "readiness_blocker_counts": {
                "source_count_below_minimum": 2,
                "sample_count_below_minimum": 2,
            },
            "all_candidate_ready": False,
        },
        "clusters": [
            {
                "key": "ogcf_bridge|ogcf_bridge_behavior_candidate",
                "run_count": 2,
                "runs": [1, 2],
                "proposal_count": 2,
                "kinds": {"ogcf_bridge_behavior_candidate": 2},
                "feedback_labels": {"answer_bridge_warning_useful": 6, "bridge_relevant": 6},
                "combined_support": 12,
                "combined_source_log_count": 4,
                "evidence_ready_count": 2,
                "related_review_blocked_count": 2,
                "recurring": True,
                "recommendation": "build_or_validate_separator_for_recurring_related_review_family",
                "examples": [],
            },
            {
                "key": "missing_support|missing_support_review",
                "run_count": 2,
                "runs": [1, 2],
                "proposal_count": 2,
                "kinds": {"missing_support_review": 2},
                "feedback_labels": {"answer_missing_support": 4},
                "combined_support": 4,
                "combined_source_log_count": 2,
                "evidence_ready_count": 0,
                "related_review_blocked_count": 0,
                "recurring": True,
                "recommendation": "preserve_as_recurring_review_or_collection_signal",
                "examples": [],
            },
            {
                "key": "stale_conflict|stale_answer_review",
                "run_count": 2,
                "runs": [1, 2],
                "proposal_count": 2,
                "kinds": {"stale_answer_review": 2},
                "feedback_labels": {"answer_stale": 4},
                "combined_support": 4,
                "combined_source_log_count": 2,
                "evidence_ready_count": 0,
                "related_review_blocked_count": 0,
                "recurring": True,
                "recommendation": "preserve_as_recurring_review_or_collection_signal",
                "examples": [],
            },
        ],
        "next_development_target": "collect_more_independent_bridge_sources_for_loso",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    MULTIRUN_JSON.write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def main() -> int:
    write_fixture()
    report = build_report(MULTIRUN_JSON, min_holdout_runs=2, min_support=4)
    tasks = report["tasks"]
    checks = {
        "report_ok": report["ok"] is True,
        "task_count": report["task_count"] == 3,
        "ready_task_count": report["ready_task_count"] == 3,
        "ogcf_task_ready": any(
            task["family"] == "ogcf_bridge"
            and task["task_type"] == "ogcf_bridge_separator_holdout"
            and task["ready_for_holdout"]
            for task in tasks
        ),
        "learned_scorer_blocked_by_loso": report["learned_scorer_candidate"] is False
        and "leave_one_source_out_not_candidate_ready_across_runs" in report["learned_scorer_blockers"]
        and "leave_one_source_out_source_count_below_minimum" in report["learned_scorer_blockers"]
        and "leave_one_source_out_sample_count_below_minimum" in report["learned_scorer_blockers"],
        "next_target": report["next_development_target"] == "run_or_generate_broader_recurring_cluster_holdouts",
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_recurring_holdout_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "holdout": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Recurring Holdout Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
