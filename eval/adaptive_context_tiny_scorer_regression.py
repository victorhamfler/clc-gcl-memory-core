from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_tiny_scorer import build_report, write_report


DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_regression_report.md"
SCORER_JSON = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_regression_scorer_results.json"
SCORER_MD = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_regression_scorer_report.md"


def main() -> int:
    report = build_report(DATASET)
    write_report(report, SCORER_JSON, SCORER_MD)
    fresh_eval = report.get("evaluations", {}).get("adaptive_only_leave_style", {})
    holdout = report.get("evaluations", {}).get("adaptive_behavior_holdout", {})
    learned = fresh_eval.get("learned", {})
    majority = fresh_eval.get("majority_baseline", {})
    symbolic = fresh_eval.get("symbolic_health_baseline", {})
    checks = {
        "report_ok": report.get("ok") is True,
        "fresh_dataset_used": report.get("dataset_path") == str(DATASET),
        "has_adaptive_eval": bool(fresh_eval),
        "has_behavior_holdout": bool(holdout),
        "readiness_blocks_promotion": report.get("readiness") == "blocked_behavior_generalization",
        "learned_beats_majority_accuracy": float(learned.get("accuracy", 0.0)) > float(majority.get("accuracy", 1.0)),
        "learned_beats_symbolic_brier": float(learned.get("brier", 1.0)) < float(symbolic.get("brier", 0.0)),
        "report_only": report.get("mutates_runtime") is False and report.get("mutates_config") is False,
    }
    regression = {
        "schema": "adaptive_context_tiny_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "scorer_summary": {
            "example_count": report.get("example_count"),
            "target_counts": report.get("target_counts"),
            "readiness": report.get("readiness"),
            "adaptive_only_leave_style": fresh_eval,
            "adaptive_behavior_holdout": holdout.get("weighted"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(regression, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Tiny Scorer Regression",
        "",
        f"Passed: **{regression['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": regression["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if regression["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
