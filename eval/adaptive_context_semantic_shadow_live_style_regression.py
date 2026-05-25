from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_semantic_shadow_live_style_eval import main as run_live_style_eval


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_regression_report.md"
EVAL_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_eval_results.json"


def main() -> int:
    result_code = run_live_style_eval()
    evaluation = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    eval_summary = evaluation.get("eval", {})
    checks = {
        "eval_command_ok": result_code == 0,
        "eval_ok": evaluation.get("ok") is True,
        "live_style_candidate": evaluation.get("readiness") == "live_style_shadow_candidate",
        "report_only": evaluation.get("mutates_runtime") is False and evaluation.get("mutates_config") is False,
        "actioned_precision_one": float(eval_summary.get("actioned_precision") or 0.0) == 1.0,
        "coverage_at_least_0_40": float(eval_summary.get("coverage") or 0.0) >= 0.40,
        "has_uncertain_fallback": int((eval_summary.get("advisory_counts") or {}).get("uncertain_keep_symbolic", 0)) > 0,
    }
    report = {
        "schema": "adaptive_context_semantic_shadow_live_style_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "eval_summary": {
            "readiness": evaluation.get("readiness"),
            "eval_count": eval_summary.get("eval_count"),
            "advisory_counts": eval_summary.get("advisory_counts"),
            "route_counts": eval_summary.get("route_counts"),
            "actioned_precision": eval_summary.get("actioned_precision"),
            "coverage": eval_summary.get("coverage"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Live-Style Regression",
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
