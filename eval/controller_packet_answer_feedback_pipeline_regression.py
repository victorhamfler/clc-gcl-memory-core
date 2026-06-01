from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.answer_feedback_signal_eval import build_report as build_log_report  # noqa: E402
from eval.controller_packet_answer_feedback_eval import build_report as build_packet_report  # noqa: E402
from eval.controller_packet_collector import collect_packets, summarize, write_outputs  # noqa: E402
from eval.neural_symbolic_outcome_holdout_workflow import main as generate_source_log  # noqa: E402


SOURCE_LOG = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_workflow.jsonl"
PACKETS_JSONL = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_pipeline_regression_packets.jsonl"
COLLECTOR_JSON = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_pipeline_regression_collector.json"
COLLECTOR_MD = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_pipeline_regression_collector.md"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_pipeline_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_pipeline_regression_report.md"


def comparable(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer_feedback_count": report.get("answer_feedback_count"),
        "signal_count": report.get("signal_count"),
        "label_counts": report.get("label_counts"),
        "family_counts": report.get("family_counts"),
        "recommendation_counts": report.get("recommendation_counts"),
    }


def main() -> int:
    if not SOURCE_LOG.exists():
        generated = generate_source_log()
        if generated != 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "failed_to_generate_source_log",
                        "source_log": str(SOURCE_LOG),
                    },
                    indent=2,
                )
            )
            return 1

    packets, skipped = collect_packets([SOURCE_LOG])
    collector_report = summarize(packets, skipped, [SOURCE_LOG])
    write_outputs(packets, collector_report, PACKETS_JSONL, COLLECTOR_JSON, COLLECTOR_MD)

    log_report = build_log_report(SOURCE_LOG)
    packet_report = build_packet_report(PACKETS_JSONL)
    checks = {
        "source_log_exists": SOURCE_LOG.exists(),
        "collector_ok": bool(collector_report.get("ok")),
        "packet_eval_ok": bool(packet_report.get("ok")),
        "legacy_log_eval_ok": bool(log_report.get("ok")),
        "counts_match": comparable(packet_report) == comparable(log_report),
        "no_collector_skips": not skipped,
    }
    report = {
        "schema": "controller_packet_answer_feedback_pipeline_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "source_log": str(SOURCE_LOG),
        "packet_jsonl": str(PACKETS_JSONL),
        "legacy_comparable": comparable(log_report),
        "packet_comparable": comparable(packet_report),
        "collector_summary": collector_report,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Answer Feedback Pipeline Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Legacy Comparable",
            "",
            "```json",
            json.dumps(report["legacy_comparable"], indent=2),
            "```",
            "",
            "## Packet Comparable",
            "",
            "```json",
            json.dumps(report["packet_comparable"], indent=2),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
