from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_cross_log_holdout import (  # noqa: E402
    DEFAULT_TEST_LOG,
    DEFAULT_TRAIN_LOGS,
    build_report,
    parse_thresholds,
)


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_cross_log_holdout_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_cross_log_holdout_regression_report.md"


def main() -> int:
    report = build_report(DEFAULT_TRAIN_LOGS, DEFAULT_TEST_LOG, parse_thresholds(""))
    best_safe = report.get("best_zero_harm_threshold") or {}
    best_any = report.get("best_any_threshold") or {}
    checks = {
        "schema_ok": report.get("schema") == "adaptive_behavior_feature_cross_log_holdout/v1",
        "report_only": report.get("report_only") is True,
        "no_runtime_mutation": report.get("mutates_runtime") is False,
        "no_config_mutation": report.get("mutates_config") is False,
        "has_train_samples": int(report.get("train_sample_count") or 0) > 0,
        "has_test_samples": int(report.get("test_sample_count") or 0) > 0,
        "has_family_models": int(report.get("family_model_count") or 0) >= 1,
        "best_any_found": bool(best_any),
        "best_zero_harm_found": bool(best_safe),
        "best_zero_harm_has_no_harmful_overrides": int(best_safe.get("harmful_override_count") or 0) == 0,
        "zero_harm_beats_symbolic": report.get("zero_harm_beats_symbolic") is True,
        "promotion_blocked": report.get("promotion_ready") is False,
    }
    result = {
        "schema": "adaptive_behavior_feature_cross_log_holdout_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "train_sample_count": report.get("train_sample_count"),
        "test_sample_count": report.get("test_sample_count"),
        "symbolic_match_rate": report.get("symbolic_match_rate"),
        "best_any_threshold": {
            "threshold": best_any.get("threshold"),
            "hybrid_delta_vs_symbolic": best_any.get("hybrid_delta_vs_symbolic"),
            "harmful_override_count": best_any.get("harmful_override_count"),
        },
        "best_zero_harm_threshold": {
            "threshold": best_safe.get("threshold"),
            "hybrid_delta_vs_symbolic": best_safe.get("hybrid_delta_vs_symbolic"),
            "helpful_override_count": best_safe.get("helpful_override_count"),
            "harmful_override_count": best_safe.get("harmful_override_count"),
            "neutral_wrong_override_count": best_safe.get("neutral_wrong_override_count"),
        },
        "promotion_ready": report.get("promotion_ready"),
        "promotion_blocker": report.get("promotion_blocker"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Feature Cross-Log Holdout Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "best_zero_harm_delta": result["best_zero_harm_threshold"]["hybrid_delta_vs_symbolic"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
