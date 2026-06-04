from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_challenge_log import build_report as build_challenge_log  # noqa: E402
from eval.adaptive_behavior_feature_scorer_eval import build_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_regression_report.md"
FIXTURE_BASE_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_regression_missing_base.jsonl"
FIXTURE_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_regression_fixture.jsonl"
FIXTURE_COMBINED_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_regression_combined.jsonl"


def main() -> int:
    challenge = build_challenge_log(FIXTURE_BASE_LOG, FIXTURE_LOG, FIXTURE_COMBINED_LOG)
    report = build_report(FIXTURE_COMBINED_LOG)
    checks = {
        "schema_ok": report.get("schema") == "adaptive_behavior_feature_scorer_eval/v1",
        "report_only": report.get("report_only") is True,
        "no_runtime_mutation": report.get("mutates_runtime") is False,
        "no_config_mutation": report.get("mutates_config") is False,
        "fixture_log_generated": challenge.get("ok") is True and FIXTURE_COMBINED_LOG.exists(),
        "feature_exports_present": report.get("feature_export_count") == report.get("sample_count"),
        "ogcf_structural_pressure_feature_present": "ogcf_structural_pressure" in (report.get("feature_keys") or []),
        "erg_feature_keys_present": all(
            key in (report.get("feature_keys") or [])
            for key in (
                "ogcf_omega_norm",
                "ogcf_core_halo_score",
                "ogcf_core_halo_slope",
                "ogcf_projector_graph_anomaly",
            )
        ),
        "has_train_and_test": int(report.get("train_count") or 0) > 0 and int(report.get("test_count") or 0) > 0,
        "promotion_blocked": report.get("promotion_ready") is False,
        "symbolic_baseline_present": "test_symbolic_match_rate" in report,
        "learned_score_present": "test_learned_match_rate" in report,
    }
    result = {
        "schema": "adaptive_behavior_feature_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "fixture_log": str(FIXTURE_COMBINED_LOG),
        "sample_count": report.get("sample_count"),
        "test_learned_match_rate": report.get("test_learned_match_rate"),
        "test_symbolic_match_rate": report.get("test_symbolic_match_rate"),
        "promotion_ready": report.get("promotion_ready"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Feature Scorer Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
