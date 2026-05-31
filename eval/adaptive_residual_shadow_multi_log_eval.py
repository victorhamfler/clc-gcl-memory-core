from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_shadow_logged_eval import build_report  # noqa: E402

DEFAULT_LOG_GLOB = "adaptive_residual_shadow_*_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_multi_log_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_multi_log_eval_report.md"


def discover_logs(pattern: str) -> list[Path]:
    raw = Path(pattern)
    if raw.exists() and raw.is_file():
        return [raw]
    if any(char in pattern for char in "*?[]"):
        return sorted((REPO_ROOT / "experiments").glob(pattern))
    return []


def merge_family_summaries(reports: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    merged: dict[str, Counter[str]] = defaultdict(Counter)
    for report in reports:
        for family, values in (report.get("family_summary") or {}).items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if isinstance(value, int):
                    merged[str(family)][str(key)] += value
    return {family: dict(sorted(counter.items())) for family, counter in sorted(merged.items())}


def compact_log_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for report in reports:
        rows.append(
            {
                "log_path": report.get("log_path"),
                "ok": report.get("ok"),
                "ask_count": report.get("ask_count"),
                "answer_feedback_count": report.get("answer_feedback_count"),
                "decision_count": report.get("decision_count"),
                "override_count": report.get("override_count"),
                "helpful_override_count": report.get("helpful_override_count"),
                "harmful_override_count": report.get("harmful_override_count"),
                "neutral_wrong_override_count": report.get("neutral_wrong_override_count"),
            }
        )
    return rows


def build_multi_log_report(logs: list[Path], *, min_logs: int = 1) -> dict[str, Any]:
    reports = [build_report(log) for log in logs]
    useful_reports = [report for report in reports if report.get("checks", {}).get("has_residual_decisions")]
    totals = {
        "log_count": len(reports),
        "usable_log_count": len(useful_reports),
        "ask_count": sum(int(report.get("ask_count") or 0) for report in useful_reports),
        "answer_feedback_count": sum(int(report.get("answer_feedback_count") or 0) for report in useful_reports),
        "decision_count": sum(int(report.get("decision_count") or 0) for report in useful_reports),
        "override_count": sum(int(report.get("override_count") or 0) for report in useful_reports),
        "helpful_override_count": sum(int(report.get("helpful_override_count") or 0) for report in useful_reports),
        "harmful_override_count": sum(int(report.get("harmful_override_count") or 0) for report in useful_reports),
        "neutral_wrong_override_count": sum(
            int(report.get("neutral_wrong_override_count") or 0) for report in useful_reports
        ),
    }
    checks = {
        "has_required_log_count": totals["usable_log_count"] >= min_logs,
        "all_usable_logs_pass": bool(useful_reports) and all(bool(report.get("ok")) for report in useful_reports),
        "has_overrides": totals["override_count"] > 0,
        "has_helpful_overrides": totals["helpful_override_count"] > 0,
        "zero_harmful_overrides": totals["harmful_override_count"] == 0,
        "zero_neutral_wrong_overrides": totals["neutral_wrong_override_count"] == 0,
        "report_only": all(bool(report.get("report_only")) for report in useful_reports),
        "no_runtime_mutation": not any(bool(report.get("mutates_runtime")) for report in useful_reports),
        "no_config_mutation": not any(bool(report.get("mutates_config")) for report in useful_reports),
    }
    return {
        "schema": "adaptive_residual_shadow_multi_log_eval/v1",
        "description": "Aggregate logged residual-shadow linked-feedback evaluations across residual outcome logs.",
        "ok": all(checks.values()),
        "min_logs": min_logs,
        "checks": checks,
        "totals": totals,
        "logs": compact_log_rows(reports),
        "family_summary": merge_family_summaries(useful_reports),
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    totals = report["totals"]
    out_md.write_text(
        "# Adaptive Residual Shadow Multi-Log Eval\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Usable logs: `{totals['usable_log_count']}` / `{totals['log_count']}`\n"
        + f"Ask count: `{totals['ask_count']}`\n"
        + f"Decision count: `{totals['decision_count']}`\n"
        + f"Overrides: `{totals['override_count']}` helpful `{totals['helpful_override_count']}` harmful `{totals['harmful_override_count']}` neutral-wrong `{totals['neutral_wrong_override_count']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Logs\n\n```json\n"
        + json.dumps(report["logs"], indent=2)
        + "\n```\n\n"
        + "## Family Summary\n\n```json\n"
        + json.dumps(report["family_summary"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate logged adaptive residual shadow evaluations.")
    parser.add_argument("--log", action="append", default=[], help="Outcome log path. Can be repeated.")
    parser.add_argument("--log-glob", default=DEFAULT_LOG_GLOB)
    parser.add_argument("--min-logs", type=int, default=1)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    logs = [Path(item) for item in args.log] if args.log else discover_logs(args.log_glob)
    logs = [log for log in logs if log.exists() and log.is_file()]
    report = build_multi_log_report(logs, min_logs=args.min_logs)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "usable_logs": report["totals"]["usable_log_count"],
                "overrides": report["totals"]["override_count"],
                "helpful": report["totals"]["helpful_override_count"],
                "harmful": report["totals"]["harmful_override_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
