from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_pipeline import real_log_readiness_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_real_log_readiness_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_real_log_readiness_regression_report.md"


def readiness_case(
    *,
    packet_count: int,
    source_count: int,
    feature_coverage: float,
    review_count: int = 0,
    loso_candidate: bool = False,
    loso_blockers: list[str] | None = None,
    policy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return real_log_readiness_report(
        collector_report={"packet_count": packet_count},
        bank_report={"evidence_context_feature_coverage": feature_coverage},
        guard_report={"ready_count": 0, "review_item_count": review_count},
        bridge_loso_report={
            "learned_scorer_candidate": loso_candidate,
            "readiness_blockers": loso_blockers or [],
        },
        log_paths=[Path(f"source_{idx}.jsonl") for idx in range(source_count)],
        policy_config=policy_config,
    )


def main() -> int:
    analysis_only = readiness_case(
        packet_count=4,
        source_count=1,
        feature_coverage=1.0,
        loso_blockers=["source_count_below_minimum:1<3"],
    )
    runtime_collection = readiness_case(
        packet_count=18,
        source_count=2,
        feature_coverage=1.0,
        loso_blockers=["source_count_below_minimum:2<3"],
    )
    loso_ready = readiness_case(
        packet_count=36,
        source_count=3,
        feature_coverage=1.0,
        loso_candidate=True,
    )
    incomplete_features = readiness_case(
        packet_count=18,
        source_count=2,
        feature_coverage=0.5,
    )
    review_blocked = readiness_case(
        packet_count=36,
        source_count=3,
        feature_coverage=1.0,
        review_count=1,
        loso_candidate=True,
    )
    relaxed_policy = {
        "controller_packet_calibration": {
            "real_log_readiness": {
                "min_packets_for_runtime_collection": 4,
                "min_sources_for_runtime_collection": 1,
                "min_packets_for_learned_scorer_evaluation": 4,
                "min_sources_for_learned_scorer_evaluation": 1,
                "require_full_evidence_context_feature_coverage": False,
                "block_on_review_items": False,
            }
        }
    }
    config_override_ready = readiness_case(
        packet_count=4,
        source_count=1,
        feature_coverage=0.5,
        review_count=1,
        loso_candidate=True,
        policy_config=relaxed_policy,
    )
    checks = {
        "analysis_only_small_single_source": analysis_only["readiness"] == "analysis_only"
        and "packet_count_below_runtime_collection_target" in analysis_only["blockers"]
        and "single_source_log_only" in analysis_only["blockers"]
        and analysis_only["next_action"] == "use_for_diagnostics_but_do_not_train_or_promote",
        "runtime_collection_ready": runtime_collection["readiness"] == "ready_for_runtime_collection"
        and runtime_collection["next_action"] == "collect_more_independent_real_logs_with_same_contract",
        "loso_scorer_eval_ready": loso_ready["readiness"] == "ready_for_loso_learned_scorer_evaluation"
        and loso_ready["next_action"] == "run_broader_real_source_holdout_and_manual_review"
        and loso_ready["blockers"] == [],
        "incomplete_features_block_training": incomplete_features["readiness"] == "analysis_only"
        and "incomplete_evidence_context_feature_coverage" in incomplete_features["blockers"],
        "review_items_block_loso_ready": review_blocked["readiness"] == "ready_for_runtime_collection"
        and "review_items_present" in review_blocked["blockers"],
        "config_override_controls_thresholds": config_override_ready["readiness"]
        == "ready_for_loso_learned_scorer_evaluation"
        and config_override_ready["policy"]["min_packets_for_runtime_collection"] == 4
        and config_override_ready["policy"]["min_sources_for_runtime_collection"] == 1
        and config_override_ready["policy"]["require_full_evidence_context_feature_coverage"] is False
        and config_override_ready["policy"]["block_on_review_items"] is False,
        "report_only": all(
            item["report_only"] is True and item["mutates_runtime"] is False and item["mutates_config"] is False
            for item in (
                analysis_only,
                runtime_collection,
                loso_ready,
                incomplete_features,
                review_blocked,
                config_override_ready,
            )
        ),
    }
    result = {
        "schema": "controller_packet_real_log_readiness_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "cases": {
            "analysis_only": analysis_only,
            "runtime_collection": runtime_collection,
            "loso_ready": loso_ready,
            "incomplete_features": incomplete_features,
            "review_blocked": review_blocked,
            "config_override_ready": config_override_ready,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Real-Log Readiness Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Cases", "", "```json", json.dumps(result["cases"], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
