from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_challenge_log import (  # noqa: E402
    BASE_LOG,
    OUT_COMBINED,
    OUT_LOG,
    build_report as build_challenge_report,
)
from eval.adaptive_behavior_feature_scorer_hybrid_eval import build_report as build_hybrid_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_regression_report.md"


def main() -> int:
    challenge = build_challenge_report(BASE_LOG, OUT_LOG, OUT_COMBINED)
    hybrid = build_hybrid_report(OUT_COMBINED)
    symbolic = float(hybrid.get("test_symbolic_match_rate") or 0.0)
    hybrid_rate = float(hybrid.get("test_hybrid_match_rate") or 0.0)
    checks = {
        "challenge_schema_ok": challenge.get("schema") == "adaptive_behavior_feature_challenge_log/v1",
        "challenge_report_only": challenge.get("report_only") is True,
        "challenge_has_symbolic_errors": int(challenge.get("symbolic_wrong_decision_count") or 0) > 0,
        "combined_log_exists": OUT_COMBINED.exists(),
        "hybrid_schema_ok": hybrid.get("schema") == "adaptive_behavior_feature_scorer_hybrid_eval/v1",
        "hybrid_report_only": hybrid.get("report_only") is True,
        "hybrid_no_runtime_mutation": hybrid.get("mutates_runtime") is False,
        "hybrid_no_config_mutation": hybrid.get("mutates_config") is False,
        "hybrid_beats_symbolic_on_challenge_mix": hybrid_rate > symbolic,
        "promotion_blocked": hybrid.get("promotion_ready") is False,
    }
    result = {
        "schema": "adaptive_behavior_feature_challenge_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "challenge_log": challenge.get("challenge_log"),
        "combined_log": challenge.get("combined_log"),
        "symbolic_wrong_decision_count": challenge.get("symbolic_wrong_decision_count"),
        "test_symbolic_match_rate": symbolic,
        "test_hybrid_match_rate": hybrid_rate,
        "hybrid_delta_vs_symbolic": hybrid.get("hybrid_delta_vs_symbolic"),
        "promotion_ready": hybrid.get("promotion_ready"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Feature Challenge Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": result["ok"], "hybrid_delta_vs_symbolic": result["hybrid_delta_vs_symbolic"], "json": str(OUT_JSON)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
