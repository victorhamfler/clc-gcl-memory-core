from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from eval.controller_packet_calibration_guard import build_report as build_guard_report, write_report as write_guard_report  # noqa: E402
from eval.controller_packet_calibration_proposals import build_report as build_proposals_report, write_report as write_proposals_report  # noqa: E402
from eval.controller_packet_bridge_separator import build_report as build_bridge_separator_report, write_report as write_bridge_separator_report  # noqa: E402
from eval.controller_packet_bridge_separator_holdout import build_report as build_bridge_holdout_report, write_report as write_bridge_holdout_report  # noqa: E402
from eval.controller_packet_collector import collect_packets, parse_paths as parse_log_paths, summarize as summarize_packets, write_outputs as write_packet_outputs  # noqa: E402
from eval.controller_packet_memory_bank import build_report as build_bank_report, write_report as write_bank_report  # noqa: E402
from eval.controller_packet_ogcf_bridge_leave_one_source_out import build_report as build_bridge_loso_report, write_report as write_bridge_loso_report  # noqa: E402
from eval.controller_packet_review_separation import build_report as build_review_separation_report, write_report as write_review_separation_report  # noqa: E402


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_benefit_opportunity_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_report.md"


def clean_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_calibration_manifest(
    *,
    collector_report: dict[str, Any],
    bank_report: dict[str, Any],
    proposals_report: dict[str, Any],
    guard_report: dict[str, Any],
    review_separation_report: dict[str, Any],
    bridge_separator_report: dict[str, Any],
    bridge_holdout_report: dict[str, Any],
    bridge_loso_report: dict[str, Any],
) -> dict[str, Any]:
    """Describe the report-only calibration subsystem as one explicit contract."""

    guard_ready = int(guard_report.get("ready_count") or 0)
    evidence_blocked = int(guard_report.get("evidence_ready_blocked_count") or 0)
    bridge_holdout = bridge_holdout_report.get("match_rate")
    if guard_ready:
        next_target = "manual_review_of_guard_ready_candidates"
    elif evidence_blocked:
        next_target = "model_or_resolve_related_review_families"
    elif bridge_loso_report.get("readiness_blockers"):
        next_target = "collect_enough_independent_bridge_sources_for_leave_one_source_out"
    elif bridge_holdout is not None:
        next_target = "collect_broader_unseen_holdout_logs"
    else:
        next_target = "collect_more_controller_packets"
    return {
        "schema": "controller_packet_calibration_system_manifest/v1",
        "description": "Unified report-only architecture contract for packet-based adaptive controller calibration.",
        "stages": [
            {
                "name": "packet_collection",
                "input": "outcome_log ask/feedback events or embedded controller_evidence_packet/v1 rows",
                "output": "controller_evidence_packet/v1 JSONL",
                "status": "ok" if collector_report.get("ok") else "blocked",
                "count": collector_report.get("packet_count"),
            },
            {
                "name": "packet_memory_bank",
                "input": "controller_evidence_packet/v1 JSONL",
                "output": "controller_packet_memory_bank/v1 clusters",
                "status": "ok" if bank_report.get("ok") else "blocked",
                "count": bank_report.get("cluster_count"),
            },
            {
                "name": "calibration_proposals",
                "input": "packet memory-bank clusters",
                "output": "controller_packet_calibration_proposals/v1",
                "status": "ok" if proposals_report.get("ok") else "blocked",
                "count": proposals_report.get("proposal_count"),
            },
            {
                "name": "promotion_guard",
                "input": "calibration proposals",
                "output": "controller_packet_calibration_guard/v1 readiness tiers",
                "status": "ok" if guard_report.get("ok") else "blocked",
                "count": guard_report.get("proposal_count"),
            },
            {
                "name": "review_separation",
                "input": "guard-blocked candidates and related review evidence",
                "output": "controller_packet_review_separation/v1",
                "status": "ok" if review_separation_report.get("ok") else "blocked",
                "count": review_separation_report.get("analysis_count"),
            },
            {
                "name": "bridge_separator",
                "input": "review separation analyses",
                "output": "controller_packet_bridge_separator/v1 candidate separators",
                "status": "ok" if bridge_separator_report.get("ok") else "blocked",
                "count": bridge_separator_report.get("separator_count"),
            },
            {
                "name": "bridge_separator_holdout",
                "input": "bridge separator candidates and packet holdout data",
                "output": "controller_packet_bridge_separator_holdout/v1 replay report",
                "status": "ok" if bridge_holdout_report.get("ok") else "blocked",
                "count": bridge_holdout_report.get("scored_count"),
            },
            {
                "name": "bridge_leave_one_source_out",
                "input": "packet source groups and bridge separator candidates",
                "output": "controller_packet_ogcf_bridge_leave_one_source_out/v1 evidence-readiness report",
                "status": "ok" if bridge_loso_report.get("ok") else "blocked",
                "count": bridge_loso_report.get("sample_count"),
            },
        ],
        "maturity": {
            "runtime_mutation_allowed": False,
            "config_mutation_allowed": False,
            "promotion_ready": False,
            "reason": "packet calibration remains report-only until broad unseen holdout logs and manual review pass",
        },
        "next_development_target": next_target,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


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
    review_separation_json = out_prefix.with_name(out_prefix.name + "_review_separation.json")
    review_separation_md = out_prefix.with_name(out_prefix.name + "_review_separation.md")
    bridge_separator_json = out_prefix.with_name(out_prefix.name + "_bridge_separator.json")
    bridge_separator_md = out_prefix.with_name(out_prefix.name + "_bridge_separator.md")
    bridge_holdout_json = out_prefix.with_name(out_prefix.name + "_bridge_separator_holdout.json")
    bridge_holdout_md = out_prefix.with_name(out_prefix.name + "_bridge_separator_holdout.md")
    bridge_loso_json = out_prefix.with_name(out_prefix.name + "_bridge_leave_one_source_out.json")
    bridge_loso_md = out_prefix.with_name(out_prefix.name + "_bridge_leave_one_source_out.md")

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
    review_separation_report = build_review_separation_report(proposals_json, guard_json)
    write_review_separation_report(review_separation_report, review_separation_json, review_separation_md)
    bridge_separator_report = build_bridge_separator_report(review_separation_json)
    write_bridge_separator_report(bridge_separator_report, bridge_separator_json, bridge_separator_md)
    bridge_holdout_report = build_bridge_holdout_report(bridge_separator_json, [packets_jsonl])
    write_bridge_holdout_report(bridge_holdout_report, bridge_holdout_json, bridge_holdout_md)
    bridge_loso_report = build_bridge_loso_report([packets_jsonl], bridge_separator_json, policy_config=load_config(ROOT))
    write_bridge_loso_report(bridge_loso_report, bridge_loso_json, bridge_loso_md)
    calibration_manifest = build_calibration_manifest(
        collector_report=collector_report,
        bank_report=bank_report,
        proposals_report=proposals_report,
        guard_report=guard_report,
        review_separation_report=review_separation_report,
        bridge_separator_report=bridge_separator_report,
        bridge_holdout_report=bridge_holdout_report,
        bridge_loso_report=bridge_loso_report,
    )

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
            "review_separation_json": str(review_separation_json),
            "review_separation_md": str(review_separation_md),
            "bridge_separator_json": str(bridge_separator_json),
            "bridge_separator_md": str(bridge_separator_md),
            "bridge_separator_holdout_json": str(bridge_holdout_json),
            "bridge_separator_holdout_md": str(bridge_holdout_md),
            "bridge_leave_one_source_out_json": str(bridge_loso_json),
            "bridge_leave_one_source_out_md": str(bridge_loso_md),
        },
        "readiness_counts": bank_report.get("readiness_counts"),
        "diagnostics": bank_report.get("diagnostics"),
        "guard_thresholds": guard_report.get("thresholds"),
        "guard_readiness_tier_counts": guard_report.get("readiness_tier_counts"),
        "guard_next_actions": guard_report.get("next_actions"),
        "review_separation_action_counts": review_separation_report.get("action_counts"),
        "bridge_separator_count": bridge_separator_report.get("separator_count"),
        "bridge_separator_holdout": {
            "ok": bridge_holdout_report.get("ok"),
            "match_rate": bridge_holdout_report.get("match_rate"),
            "scored_count": bridge_holdout_report.get("scored_count"),
        },
        "bridge_leave_one_source_out": {
            "ok": bridge_loso_report.get("ok"),
            "source_count": bridge_loso_report.get("source_count"),
            "sample_count": bridge_loso_report.get("sample_count"),
            "minimum_sources_for_candidate": bridge_loso_report.get("minimum_sources_for_candidate"),
            "minimum_samples_for_candidate": bridge_loso_report.get("minimum_samples_for_candidate"),
            "learned_scorer_candidate": bridge_loso_report.get("learned_scorer_candidate"),
            "readiness_blockers": bridge_loso_report.get("readiness_blockers"),
        },
        "calibration_system": calibration_manifest,
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
            "## Guard Readiness Tiers",
            "",
            "```json",
            json.dumps(report.get("guard_readiness_tier_counts"), indent=2),
            "```",
            "",
            "## Guard Next Actions",
            "",
            "```json",
            json.dumps(report.get("guard_next_actions"), indent=2),
            "```",
            "",
            "## Bridge Separators",
            "",
            f"Count: `{report.get('bridge_separator_count')}`",
            "",
            "## Bridge Separator Holdout",
            "",
            "```json",
            json.dumps(report.get("bridge_separator_holdout"), indent=2),
            "```",
            "",
            "## Bridge Leave-One-Source-Out",
            "",
            "```json",
            json.dumps(report.get("bridge_leave_one_source_out"), indent=2),
            "```",
            "",
            "## Calibration System Manifest",
            "",
            "```json",
            json.dumps(report.get("calibration_system"), indent=2),
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
