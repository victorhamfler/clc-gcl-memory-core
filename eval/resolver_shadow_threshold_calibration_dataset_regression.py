from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.resolver_shadow_outcome_collector import DEFAULT_LOGS, build_report as build_outcome_report
from eval.resolver_shadow_threshold_calibration import (
    DEFAULT_DATASET,
    build_report,
    build_report_from_dataset,
)


OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_threshold_calibration_dataset_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_threshold_calibration_dataset_regression_report.md"


SCORE_VALUES = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
EFFECTIVE_VALUES = [0.10, 0.25, 0.35, 0.50, 0.65, 0.75, 0.90, 0.95]


def ensure_dataset() -> None:
    if DEFAULT_DATASET.exists():
        return
    logs = [path for path in DEFAULT_LOGS if path.exists()]
    report = build_outcome_report(logs, score_threshold=0.70, effective_threshold=0.50)
    DEFAULT_DATASET.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_DATASET.write_text(json.dumps(report, indent=2), encoding="utf-8")


def candidate_signature(report: dict) -> dict:
    candidate = report.get("candidate") or {}
    return {
        "score_threshold": candidate.get("score_threshold"),
        "effective_ratio_threshold": candidate.get("effective_ratio_threshold"),
        "failed_count": candidate.get("failed_count"),
        "bridge_false_positive_count": candidate.get("bridge_false_positive_count"),
        "bridge_false_negative_count": candidate.get("bridge_false_negative_count"),
    }


def main() -> int:
    ensure_dataset()
    logs = [path for path in DEFAULT_LOGS if path.exists()]
    dataset_report = build_report_from_dataset([DEFAULT_DATASET], SCORE_VALUES, EFFECTIVE_VALUES)
    raw_report = build_report(logs, SCORE_VALUES, EFFECTIVE_VALUES)
    current_default = build_report_from_dataset([DEFAULT_DATASET], [0.70], [0.50])
    strict_default = build_report_from_dataset([DEFAULT_DATASET], [0.95], [0.75])

    checks = {
        "dataset_schema_ok": dataset_report.get("schema") == "resolver_shadow_threshold_calibration/v1",
        "dataset_input_mode": dataset_report.get("input_mode") == "dataset",
        "dataset_ok": dataset_report.get("ok") is True,
        "raw_log_ok": raw_report.get("ok") is True,
        "same_case_count": dataset_report.get("case_count") == raw_report.get("case_count") == 16,
        "same_label_counts": dataset_report.get("label_counts") == raw_report.get("label_counts"),
        "same_candidate": candidate_signature(dataset_report) == candidate_signature(raw_report),
        "current_default_ok": current_default.get("ok") is True,
        "strict_default_ok": strict_default.get("ok") is True,
    }
    report = {
        "schema": "resolver_shadow_threshold_calibration_dataset_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "dataset_candidate": candidate_signature(dataset_report),
        "raw_log_candidate": candidate_signature(raw_report),
        "current_default_candidate": candidate_signature(current_default),
        "strict_default_candidate": candidate_signature(strict_default),
        "dataset_path": str(DEFAULT_DATASET),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Threshold Calibration Dataset Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Candidate Parity", "", "```json", json.dumps({
        "dataset": report["dataset_candidate"],
        "raw_log": report["raw_log_candidate"],
        "current_default": report["current_default_candidate"],
        "strict_default": report["strict_default_candidate"],
    }, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
