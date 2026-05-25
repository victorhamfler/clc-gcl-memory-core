from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.resolver_shadow_outcome_collector import DEFAULT_LOGS, build_report


OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_outcome_collector_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_outcome_collector_regression_report.md"


def main() -> int:
    logs = [path for path in DEFAULT_LOGS if path.exists()]
    default_report = build_report(logs, score_threshold=0.70, effective_threshold=0.50)
    strict_report = build_report(logs, score_threshold=0.95, effective_threshold=0.75)
    checks = {
        "default_schema_ok": default_report.get("schema") == "resolver_shadow_outcome_dataset/v1",
        "default_ok": default_report.get("ok") is True,
        "strict_ok": strict_report.get("ok") is True,
        "example_count_16": default_report.get("example_count") == 16,
        "strict_same_example_count": strict_report.get("example_count") == default_report.get("example_count"),
        "has_bridge_positive": default_report.get("checks", {}).get("has_bridge_positive") is True,
        "has_bridge_negative": default_report.get("checks", {}).get("has_bridge_negative") is True,
        "has_missing_support": default_report.get("checks", {}).get("has_missing_support") is True,
        "has_supported_answer": default_report.get("checks", {}).get("has_supported_answer") is True,
        "all_report_only": default_report.get("checks", {}).get("all_report_only") is True,
        "contains_true_positive": int(default_report.get("outcome_counts", {}).get("bridge_warning_true_positive", 0)) >= 1,
        "contains_true_negative": int(default_report.get("outcome_counts", {}).get("bridge_warning_true_negative", 0)) >= 1,
    }
    report = {
        "schema": "resolver_shadow_outcome_collector_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "default_example_count": default_report.get("example_count"),
        "strict_example_count": strict_report.get("example_count"),
        "default_outcome_counts": default_report.get("outcome_counts"),
        "strict_outcome_counts": strict_report.get("outcome_counts"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Outcome Collector Regression",
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
