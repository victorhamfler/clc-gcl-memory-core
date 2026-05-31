from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_risk_logged_eval import build_report as build_logged_risk_report  # noqa: E402


LOGS = [
    REPO_ROOT / "experiments" / "adaptive_residual_shadow_seventh_agent_style_outcomes.jsonl",
    REPO_ROOT / "experiments" / "adaptive_residual_shadow_eighth_meta_recurrence_outcomes.jsonl",
]
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_risk_overprotection_recurrence_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_risk_overprotection_recurrence_report.md"


def compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": row.get("query"),
        "term_risk_label": row.get("term_risk_label"),
        "learned_risk_label": row.get("learned_risk_label"),
        "learned_risk_confidence": row.get("learned_risk_confidence"),
        "suppression_reasons": row.get("suppression_reasons"),
    }


def build_report(logs: list[Path] | None = None) -> dict[str, Any]:
    selected_logs = logs or LOGS
    reports = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in selected_logs:
        if not log.exists():
            continue
        report = build_logged_risk_report(log)
        reports.append(report)
        for row in report.get("term_overprotection_examples") or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("term_risk_label") or "unknown")
            grouped[key].append({"source_log": log.name, **compact(row)})
    recurrent_groups = []
    for key, rows in sorted(grouped.items()):
        source_count = len({row["source_log"] for row in rows})
        recurrent_groups.append(
            {
                "term_risk_label": key,
                "example_count": len(rows),
                "source_log_count": source_count,
                "recurrence_ready": source_count >= 2,
                "examples": rows[:12],
            }
        )
    recurrent_ready = [row for row in recurrent_groups if row["recurrence_ready"]]
    counters = Counter()
    for report in reports:
        counters["risk_rows"] += int(report.get("risk_diagnostic_row_count") or 0)
        counters["learned_beyond_terms"] += int(report.get("learned_beyond_terms_count") or 0)
        counters["term_overprotection"] += int(report.get("term_overprotection_count") or 0)
    checks = {
        "logs_available": len(reports) >= 2,
        "logged_reports_ok": bool(reports) and all(bool(report.get("ok")) for report in reports),
        "has_recurrent_overprotection_group": bool(recurrent_ready),
        "report_only": True,
        "no_runtime_mutation": True,
        "no_config_mutation": True,
        "promotion_blocked": True,
    }
    return {
        "schema": "adaptive_residual_risk_overprotection_recurrence/v1",
        "description": "Aggregate term-overprotection candidates across independent local residual logs.",
        "ok": all(checks.values()),
        "checks": checks,
        "log_count": len(reports),
        "logs": [str(log) for log in selected_logs if log.exists()],
        "totals": dict(counters),
        "candidate_groups": recurrent_groups,
        "recurrent_group_count": len(recurrent_ready),
        "recommendation": "keep_report_only_collect_external_recurrence" if recurrent_ready else "collect_more_logs",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Risk Overprotection Recurrence\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Logs: `{report['log_count']}`\n"
        + f"Recurrent groups: `{report['recurrent_group_count']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Totals\n\n```json\n"
        + json.dumps(report["totals"], indent=2)
        + "\n```\n\n"
        + "## Candidate Groups\n\n```json\n"
        + json.dumps(report["candidate_groups"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "logs": report["log_count"],
                "recurrent_groups": report["recurrent_group_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
