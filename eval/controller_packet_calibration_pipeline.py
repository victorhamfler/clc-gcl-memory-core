from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_guard import build_report as build_guard_report, write_report as write_guard_report  # noqa: E402
from eval.controller_packet_calibration_proposals import build_report as build_proposals_report, write_report as write_proposals_report  # noqa: E402
from eval.controller_packet_collector import collect_packets, parse_paths as parse_log_paths, summarize as summarize_packets, write_outputs as write_packet_outputs  # noqa: E402
from eval.controller_packet_memory_bank import build_report as build_bank_report, write_report as write_bank_report  # noqa: E402


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_benefit_opportunity_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_report.md"


def clean_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_pipeline(
    log_paths: list[Path],
    *,
    out_prefix: Path,
    ready_support: int = 2,
    ready_logs: int = 1,
    min_support: int = 4,
    min_source_logs: int = 2,
) -> dict[str, Any]:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    packets_jsonl = out_prefix.with_name(out_prefix.name + "_packets.jsonl")
    collector_json = out_prefix.with_name(out_prefix.name + "_collector.json")
    collector_md = out_prefix.with_name(out_prefix.name + "_collector.md")
    bank_json = out_prefix.with_name(out_prefix.name + "_bank.json")
    bank_md = out_prefix.with_name(out_prefix.name + "_bank.md")
    proposals_json = out_prefix.with_name(out_prefix.name + "_proposals.json")
    proposals_md = out_prefix.with_name(out_prefix.name + "_proposals.md")
    guard_json = out_prefix.with_name(out_prefix.name + "_guard.json")
    guard_md = out_prefix.with_name(out_prefix.name + "_guard.md")

    packets, skipped = collect_packets(log_paths)
    collector_report = summarize_packets(packets, skipped, log_paths)
    write_packet_outputs(packets, collector_report, packets_jsonl, collector_json, collector_md)

    bank_report = build_bank_report([packets_jsonl], ready_support=ready_support, ready_logs=ready_logs)
    write_bank_report(bank_report, bank_json, bank_md)

    proposals_report = build_proposals_report(bank_json)
    write_proposals_report(proposals_report, proposals_json, proposals_md)

    guard_report = build_guard_report(
        proposals_json,
        min_support=min_support,
        min_source_logs=min_source_logs,
    )
    write_guard_report(guard_report, guard_json, guard_md)

    return {
        "schema": "controller_packet_calibration_pipeline/v1",
        "description": "Report-only pipeline from outcome logs to packets, packet bank, calibration proposals, and promotion guard.",
        "ok": bool(collector_report.get("ok")) and bool(bank_report.get("ok")) and bool(proposals_report.get("ok")) and bool(guard_report.get("ok")),
        "logs": [str(path) for path in log_paths],
        "summary": {
            "packet_count": collector_report.get("packet_count"),
            "cluster_count": bank_report.get("cluster_count"),
            "proposal_count": proposals_report.get("proposal_count"),
            "promotion_candidate_count": proposals_report.get("promotion_candidate_count"),
            "review_item_count": proposals_report.get("review_item_count"),
            "guard_ready_count": guard_report.get("ready_count"),
            "guard_blocked_count": guard_report.get("blocked_count"),
        },
        "artifacts": {
            "packets_jsonl": str(packets_jsonl),
            "collector_json": str(collector_json),
            "collector_md": str(collector_md),
            "bank_json": str(bank_json),
            "bank_md": str(bank_md),
            "proposals_json": str(proposals_json),
            "proposals_md": str(proposals_md),
            "guard_json": str(guard_json),
            "guard_md": str(guard_md),
        },
        "readiness_counts": bank_report.get("readiness_counts"),
        "diagnostics": bank_report.get("diagnostics"),
        "guard_thresholds": guard_report.get("thresholds"),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_pipeline_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = report["summary"]
    lines = [
        "# Controller Packet Calibration Pipeline",
        "",
        "This pipeline is report-only. It does not mutate memory, selector policy, resolver policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in summary.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Readiness Counts",
            "",
            "```json",
            json.dumps(report.get("readiness_counts"), indent=2),
            "```",
            "",
            "## Diagnostics",
            "",
            "```json",
            json.dumps(report.get("diagnostics"), indent=2),
            "```",
            "",
            "## Logs",
            "",
        ]
    )
    for path in report["logs"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Artifacts", ""])
    for label, path in report["artifacts"].items():
        lines.append(f"- `{label}`: `{clean_cell(path)}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the report-only controller packet calibration pipeline.")
    parser.add_argument("--log", action="append", help="Outcome JSONL log. Can be passed multiple times.")
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    parser.add_argument("--out-prefix", type=Path, default=REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline")
    parser.add_argument("--ready-support", type=int, default=2)
    parser.add_argument("--ready-logs", type=int, default=1)
    parser.add_argument("--min-support", type=int, default=4)
    parser.add_argument("--min-source-logs", type=int, default=2)
    args = parser.parse_args()

    log_paths = parse_log_paths(args.log) if args.log else [DEFAULT_LOG]
    report = build_pipeline(
        log_paths,
        out_prefix=args.out_prefix,
        ready_support=args.ready_support,
        ready_logs=args.ready_logs,
        min_support=args.min_support,
        min_source_logs=args.min_source_logs,
    )
    write_pipeline_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                **report["summary"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
