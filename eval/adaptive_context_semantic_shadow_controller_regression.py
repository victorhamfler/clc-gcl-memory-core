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
from eval.adaptive_context_semantic_shadow_controller import build_report as build_shadow_report
from eval.adaptive_context_semantic_shadow_controller import write_report as write_shadow_report


DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
SCORER_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_scorer_results.json"
SCORER_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_scorer_report.md"
GUARD_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_guard_results.json"
GUARD_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_guard_report.md"
SHADOW_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_shadow_results.json"
SHADOW_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_shadow_report.md"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_regression_report.md"


def main() -> int:
    config = load_config(ROOT).get("adaptive_behavior")
    scorer = build_scorer_report(DATASET, config)
    write_scorer_report(scorer, SCORER_JSON, SCORER_MD)
    guard = build_guard_report(SCORER_JSON)
    write_guard_report(guard, GUARD_JSON, GUARD_MD)
    shadow = build_shadow_report(DATASET, GUARD_JSON, config)
    write_shadow_report(shadow, SHADOW_JSON, SHADOW_MD)
    checks = {
        "shadow_ok": shadow.get("ok") is True,
        "shadow_candidate": shadow.get("readiness") == "shadow_candidate",
        "requires_guard": shadow.get("checks", {}).get("guard_promotion_candidate") is True,
        "report_only": shadow.get("mutates_runtime") is False and shadow.get("mutates_config") is False,
        "shadow_disabled_by_default": shadow.get("checks", {}).get("shadow_disabled_by_default") is True,
        "has_advisories": bool(shadow.get("advisory_counts")),
        "has_non_symbolic_routes": shadow.get("checks", {}).get("has_non_symbolic_routes") is True,
    }
    report = {
        "schema": "adaptive_context_semantic_shadow_controller_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "shadow_summary": {
            "readiness": shadow.get("readiness"),
            "advisory_counts": shadow.get("advisory_counts"),
            "route_counts": shadow.get("route_counts"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Controller Regression",
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
