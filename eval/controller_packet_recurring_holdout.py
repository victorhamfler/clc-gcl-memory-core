from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_MULTIRUN = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_recurring_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_recurring_holdout_report.md"


def read_multirun(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read multi-run calibration report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Multi-run calibration report must be a JSON object: {path}")
    if value.get("schema") != "controller_packet_multirun_calibration/v1":
        raise ValueError(f"Unsupported multi-run calibration schema: {value.get('schema')}")
    return value


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def cluster_family(cluster: dict[str, Any]) -> str:
    key = str(cluster.get("key") or "")
    if "|" in key:
        return key.split("|", 1)[0]
    return "unknown"


def task_for_cluster(cluster: dict[str, Any], *, min_holdout_runs: int, min_support: int) -> dict[str, Any]:
    family = cluster_family(cluster)
    recurring = bool(cluster.get("recurring"))
    run_count = int(cluster.get("run_count") or 0)
    support = int(cluster.get("combined_support") or 0)
    related_review_blocked = int(cluster.get("related_review_blocked_count") or 0)
    evidence_ready = int(cluster.get("evidence_ready_count") or 0)
    if family == "ogcf_bridge" and related_review_blocked:
        task_type = "ogcf_bridge_separator_holdout"
        target = "validate useful-vs-noisy OGCF bridge separation on broader unseen packet logs"
    elif family == "ogcf_bridge":
        task_type = "ogcf_bridge_metadata_holdout"
        target = "verify bridge labels retain explicit OGCF metadata and separate useful/noisy examples"
    elif family == "missing_support":
        task_type = "missing_support_refusal_holdout"
        target = "verify unsupported or near-topic queries remain refused or low confidence"
    elif family == "stale_conflict":
        task_type = "stale_current_arbitration_holdout"
        target = "verify current evidence wins unless historical information is explicitly requested"
    else:
        task_type = "general_answer_behavior_holdout"
        target = "collect broader answer-feedback holdout before policy calibration"
    ready_for_holdout = recurring and run_count >= max(1, min_holdout_runs) and support >= max(1, min_support)
    if ready_for_holdout and related_review_blocked:
        recommendation = "run_broader_separator_holdout_before_learning"
    elif ready_for_holdout and evidence_ready:
        recommendation = "run_broader_behavior_holdout_before_manual_review"
    elif recurring:
        recommendation = "collect_more_labeled_support_for_recurring_review_family"
    else:
        recommendation = "collect_more_independent_runs"
    return {
        "cluster_key": cluster.get("key"),
        "family": family,
        "task_type": task_type,
        "target": target,
        "run_count": run_count,
        "combined_support": support,
        "combined_source_log_count": cluster.get("combined_source_log_count"),
        "evidence_ready_count": evidence_ready,
        "related_review_blocked_count": related_review_blocked,
        "ready_for_holdout": ready_for_holdout,
        "recommendation": recommendation,
        "labels": cluster.get("feedback_labels") if isinstance(cluster.get("feedback_labels"), dict) else {},
        "examples": cluster.get("examples") if isinstance(cluster.get("examples"), list) else [],
    }


def build_report(multirun_path: Path, *, min_holdout_runs: int = 2, min_support: int = 4) -> dict[str, Any]:
    multirun = read_multirun(multirun_path)
    clusters = [item for item in multirun.get("clusters") or [] if isinstance(item, dict)]
    recurring = [cluster for cluster in clusters if cluster.get("recurring")]
    tasks = [
        task_for_cluster(cluster, min_holdout_runs=min_holdout_runs, min_support=min_support)
        for cluster in recurring
    ]
    ready = [task for task in tasks if task["ready_for_holdout"]]
    ogcf_ready = [task for task in ready if task["family"] == "ogcf_bridge"]
    bridge = multirun.get("bridge_holdout") if isinstance(multirun.get("bridge_holdout"), dict) else {}
    bridge_loso = (
        multirun.get("bridge_leave_one_source_out")
        if isinstance(multirun.get("bridge_leave_one_source_out"), dict)
        else {}
    )
    learned_scorer_blockers: list[str] = []
    if not ogcf_ready:
        learned_scorer_blockers.append("no_recurring_ogcf_bridge_holdout_task_ready")
    if not bridge.get("all_clean"):
        learned_scorer_blockers.append("bridge_holdout_not_clean_across_runs")
    if int(bridge.get("observed_run_count") or 0) < max(1, min_holdout_runs):
        learned_scorer_blockers.append("insufficient_bridge_holdout_runs")
    if bridge_loso and not bridge_loso.get("all_candidate_ready"):
        learned_scorer_blockers.append("leave_one_source_out_not_candidate_ready_across_runs")
    for blocker in (bridge_loso.get("readiness_blocker_counts") or {}):
        learned_scorer_blockers.append(f"leave_one_source_out_{blocker}")
    return {
        "schema": "controller_packet_recurring_holdout/v1",
        "description": "Report-only holdout task planner for recurring packet-calibration clusters.",
        "ok": bool(tasks),
        "source_multirun": str(multirun_path),
        "thresholds": {
            "min_holdout_runs": max(1, int(min_holdout_runs)),
            "min_support": max(1, int(min_support)),
        },
        "task_count": len(tasks),
        "ready_task_count": len(ready),
        "ogcf_ready_task_count": len(ogcf_ready),
        "bridge_leave_one_source_out": bridge_loso,
        "learned_scorer_candidate": bool(ogcf_ready) and not learned_scorer_blockers,
        "learned_scorer_blockers": learned_scorer_blockers,
        "next_development_target": "prototype_report_only_ogcf_bridge_scorer"
        if bool(ogcf_ready) and not learned_scorer_blockers
        else "run_or_generate_broader_recurring_cluster_holdouts",
        "tasks": tasks,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Recurring Holdout",
        "",
        "This report is advisory only. It does not mutate memory, selector policy, resolver policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Tasks: `{report['task_count']}`",
        f"Ready tasks: `{report['ready_task_count']}`",
        f"OGCF ready tasks: `{report['ogcf_ready_task_count']}`",
        f"Learned scorer candidate: `{report['learned_scorer_candidate']}`",
        f"Next target: `{report['next_development_target']}`",
        "",
        "## Learned Scorer Blockers",
        "",
        "```json",
        json.dumps(report["learned_scorer_blockers"], indent=2),
        "```",
        "",
        "## Tasks",
        "",
        "| ready | family | task | runs | support | recommendation |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for task in report["tasks"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} |".format(
                task["ready_for_holdout"],
                task["family"],
                task["task_type"],
                task["run_count"],
                task["combined_support"],
                clean_cell(task["recommendation"]),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan broader holdout tasks for recurring packet calibration clusters.")
    parser.add_argument("--multirun", type=Path, default=DEFAULT_MULTIRUN)
    parser.add_argument("--min-holdout-runs", type=int, default=2)
    parser.add_argument("--min-support", type=int, default=4)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.multirun, min_holdout_runs=args.min_holdout_runs, min_support=args.min_support)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "task_count": report["task_count"],
                "ready_task_count": report["ready_task_count"],
                "learned_scorer_candidate": report["learned_scorer_candidate"],
                "next_development_target": report["next_development_target"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
