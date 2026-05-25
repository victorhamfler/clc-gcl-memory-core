from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_regression_report.md"
EVAL_JSON = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_eval_results.json"


def main() -> int:
    command = [sys.executable, str(ROOT / "eval" / "adaptive_context_gemma_shadow_eval.py")]
    proc = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)
    report = json.loads(EVAL_JSON.read_text(encoding="utf-8")) if EVAL_JSON.exists() else {}
    evaluation = report.get("eval") or {}
    checks = {
        "eval_command_ok": proc.returncode == 0,
        "eval_ok": report.get("ok") is True,
        "gemma_shadow_candidate": report.get("readiness") == "gemma_shadow_candidate",
        "eval_count_at_least_20": int(evaluation.get("eval_count") or 0) >= 20,
        "actioned_precision_at_least_0_70": float(evaluation.get("actioned_precision") or 0.0) >= 0.70,
        "coverage_at_least_0_20": float(evaluation.get("coverage") or 0.0) >= 0.20,
        "report_only": report.get("mutates_runtime") is False and report.get("mutates_config") is False,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "eval_json": str(EVAL_JSON),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "eval_summary": {
            key: evaluation.get(key)
            for key in ("eval_count", "advisory_counts", "route_counts", "actioned_count", "actioned_precision", "coverage")
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Context Gemma Shadow Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({k: result[k] for k in ("checks", "eval_summary", "eval_json")}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
