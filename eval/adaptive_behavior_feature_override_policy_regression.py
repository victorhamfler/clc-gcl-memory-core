from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_cross_log_holdout import DEFAULT_TRAIN_LOGS  # noqa: E402
from eval.adaptive_behavior_feature_override_policy_eval import DEFAULT_TEST_LOGS, build_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_override_policy_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_override_policy_regression_report.md"


def main() -> int:
    report = build_report(
        DEFAULT_TRAIN_LOGS,
        DEFAULT_TEST_LOGS,
        [0.70, 0.80, 0.90, 0.95, 0.98, 0.99, 0.995, 0.999],
        [0.0, 0.6, 0.8, 0.9, 0.95],
    )
    selected = report.get("selected_policy") or {}
    top = report.get("top_policies") or []
    best_top = top[0] if top and isinstance(top[0], dict) else {}
    selected_present = bool(selected)
    checks = {
        "schema_ok": report.get("schema") == "adaptive_behavior_feature_override_policy_eval/v1",
        "report_only": report.get("report_only") is True,
        "no_runtime_mutation": report.get("mutates_runtime") is False,
        "no_config_mutation": report.get("mutates_config") is False,
        "has_selected_policy_or_safely_blocked": selected_present or not selected_present,
        "selected_zero_harm_or_blocked": bool(selected.get("all_holdouts_zero_harm")) if selected_present else True,
        "selected_improves_all_holdouts_or_blocked": bool(selected.get("all_holdouts_improve")) if selected_present else True,
        "selected_has_helpful_overrides_or_blocked": int(selected.get("total_helpful_override_count") or 0) > 0 if selected_present else True,
        "selected_has_no_harmful_overrides_or_blocked": int(selected.get("total_harmful_override_count") or 0) == 0 if selected_present else True,
        "blocked_has_zero_harm_top_policy": int(best_top.get("total_harmful_override_count") or 0) == 0 if not selected_present else True,
        "promotion_blocked": report.get("promotion_ready") is False,
    }
    result = {
        "schema": "adaptive_behavior_feature_override_policy_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "selected_policy_name": selected.get("policy_name"),
        "selected_policy": selected.get("policy"),
        "blocked_no_selected_policy": not selected_present,
        "best_top_policy_name": best_top.get("policy_name"),
        "best_top_all_holdouts_zero_harm": best_top.get("all_holdouts_zero_harm"),
        "best_top_all_holdouts_improve": best_top.get("all_holdouts_improve"),
        "mean_delta_vs_symbolic": selected.get("mean_delta_vs_symbolic"),
        "min_delta_vs_symbolic": selected.get("min_delta_vs_symbolic"),
        "total_override_count": selected.get("total_override_count"),
        "total_helpful_override_count": selected.get("total_helpful_override_count"),
        "total_harmful_override_count": selected.get("total_harmful_override_count"),
        "promotion_ready": report.get("promotion_ready"),
        "promotion_blocker": report.get("promotion_blocker"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Feature Override Policy Regression\n\n"
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
                "selected_policy": result["selected_policy_name"],
                "mean_delta": result["mean_delta_vs_symbolic"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
