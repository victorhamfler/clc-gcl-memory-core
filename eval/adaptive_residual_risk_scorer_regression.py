from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_risk_scorer_eval import build_report  # noqa: E402
from eval.adaptive_residual_shadow_multi_log_eval import (  # noqa: E402
    PROCESSED_FAILURE_LOG_NAMES,
    discover_logs,
    filter_logs,
)


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_risk_scorer_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_risk_scorer_regression_report.md"


def main() -> int:
    logs = filter_logs(discover_logs("adaptive_residual_shadow_*_outcomes.jsonl"), PROCESSED_FAILURE_LOG_NAMES)
    report = build_report(logs)
    checks = {
        "schema_ok": report.get("schema") == "adaptive_residual_risk_scorer_eval/v1",
        "eval_ok": bool(report.get("ok")),
        "report_only": report.get("report_only") is True,
        "no_runtime_mutation": report.get("mutates_runtime") is False,
        "no_config_mutation": report.get("mutates_config") is False,
        "promotion_blocked": report.get("promotion_ready") is False,
        "has_logged_samples": int(report.get("logged_sample_count") or 0) > 0,
        "has_boundary_rows": bool(report.get("boundary_rows")),
        "protected_boundary_recall_ok": (report.get("boundary_summary") or {}).get("protected_risk_recall", 0) >= 0.75,
    }
    result = {
        "schema": "adaptive_residual_risk_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "sample_count": report.get("sample_count"),
        "logged_sample_count": report.get("logged_sample_count"),
        "test_summary": report.get("test_summary"),
        "boundary_summary": report.get("boundary_summary"),
        "promotion_ready": report.get("promotion_ready"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Risk Scorer Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
