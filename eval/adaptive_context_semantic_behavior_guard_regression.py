from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config
from eval.adaptive_context_semantic_behavior_guard import build_report as build_guard_report
from eval.adaptive_context_semantic_behavior_guard import write_report as write_guard_report
from eval.adaptive_context_semantic_behavior_scorer import build_report as build_scorer_report
from eval.adaptive_context_semantic_behavior_scorer import write_report as write_scorer_report


DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
SCORER_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_scorer_results.json"
SCORER_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_scorer_report.md"
GUARD_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_guard_results.json"
GUARD_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_guard_report.md"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_regression_report.md"


def main() -> int:
    scorer = build_scorer_report(DATASET, load_config(ROOT).get("adaptive_behavior"))
    write_scorer_report(scorer, SCORER_JSON, SCORER_MD)
    guard = build_guard_report(SCORER_JSON)
    write_guard_report(guard, GUARD_JSON, GUARD_MD)
    checks = {
        "scorer_ok": scorer.get("ok") is True,
        "guard_ok": guard.get("ok") is True,
        "promotion_candidate": guard.get("readiness") == "promotion_candidate",
        "guard_report_only": guard.get("mutates_runtime") is False and guard.get("mutates_config") is False,
        "config_driven": scorer.get("behavior_config", {}).get("schema") == "adaptive_behavior_config/v1",
    }
    report = {
        "schema": "adaptive_context_semantic_behavior_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "guard_summary": {
            "readiness": guard.get("readiness"),
            "metrics": guard.get("metrics"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Behavior Guard Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
