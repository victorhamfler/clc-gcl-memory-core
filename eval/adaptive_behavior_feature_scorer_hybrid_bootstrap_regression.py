from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_scorer_eval import FEATURE_KEYS  # noqa: E402
from eval.adaptive_behavior_feature_scorer_hybrid_eval import residual_predict, softmax  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_hybrid_bootstrap_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_hybrid_bootstrap_regression_report.md"


def sample() -> dict:
    return {
        "behavior_family": "supported_evidence",
        "symbolic_advisory": "likely_helpful",
        "expected_advisory": "likely_helpful",
        "answer_has_refusal": False,
        "evidence_context_features": {key: 0.0 for key in FEATURE_KEYS},
    }


def main() -> int:
    prediction, confidence = residual_predict({"weights": [], "means": [], "scales": []}, sample())
    checks = {
        "empty_softmax_returns_empty": softmax([]) == [],
        "empty_residual_model_does_not_crash": prediction == "symbolic_correct" and confidence == 1.0,
        "empty_residual_model_blocks_override": prediction != "symbolic_wrong",
    }
    result = {
        "schema": "adaptive_behavior_feature_scorer_hybrid_bootstrap_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "prediction": prediction,
        "confidence": confidence,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Feature Scorer Hybrid Bootstrap Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
