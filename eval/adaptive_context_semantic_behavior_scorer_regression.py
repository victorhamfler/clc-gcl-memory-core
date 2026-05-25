from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config
from eval.adaptive_context_semantic_behavior_scorer import build_report, write_report


DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_regression_report.md"
SCORER_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_regression_scorer_results.json"
SCORER_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_regression_scorer_report.md"


def main() -> int:
    report = build_report(DATASET, load_config(ROOT).get("adaptive_behavior"))
    write_report(report, SCORER_JSON, SCORER_MD)
    holdout = report.get("evaluations", {}).get("adaptive_behavior_holdout", {}).get("weighted", {})
    semantic = holdout.get("semantic_hybrid", {})
    symbolic = holdout.get("symbolic_health_baseline", {})
    checks = {
        "report_ok": report.get("ok") is True,
        "analysis_ready": report.get("readiness") == "analysis_ready",
        "report_only": report.get("mutates_runtime") is False and report.get("mutates_config") is False,
        "semantic_beats_symbolic_accuracy": float(semantic.get("accuracy", 0.0)) > float(symbolic.get("accuracy", 1.0)),
        "semantic_beats_symbolic_brier": float(semantic.get("brier", 1.0)) < float(symbolic.get("brier", 0.0)),
        "has_config_superfamily_map": bool(report.get("behavior_config", {}).get("superfamilies")),
        "config_schema_ok": report.get("behavior_config", {}).get("schema") == "adaptive_behavior_config/v1",
    }
    regression = {
        "schema": "adaptive_context_semantic_behavior_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "scorer_summary": {
            "readiness": report.get("readiness"),
            "adaptive_example_count": report.get("adaptive_example_count"),
            "holdout_weighted": holdout,
            "behavior_config": report.get("behavior_config"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(regression, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Behavior Scorer Regression",
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
