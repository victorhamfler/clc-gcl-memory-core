from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_semantic_shadow_multibatch_eval import main as run_multibatch_eval


EVAL_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_multibatch_eval_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_multibatch_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_multibatch_regression_report.md"


def main() -> int:
    result_code = run_multibatch_eval()
    evaluation = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    summary = evaluation.get("summary") or {}
    checks = {
        "eval_command_ok": result_code == 0,
        "eval_ok": evaluation.get("ok") is True,
        "multibatch_candidate": evaluation.get("readiness") == "multibatch_shadow_candidate",
        "total_examples_at_least_40": int(summary.get("total_examples") or 0) >= 40,
        "weighted_precision_one": float(summary.get("weighted_precision") or 0.0) == 1.0,
        "weighted_coverage_at_least_0_40": float(summary.get("weighted_coverage") or 0.0) >= 0.40,
        "report_only": evaluation.get("mutates_runtime") is False and evaluation.get("mutates_config") is False,
    }
    report = {
        "schema": "adaptive_context_semantic_shadow_multibatch_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "summary": summary,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Multibatch Regression",
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
