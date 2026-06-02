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


DEFAULT_PIPELINE = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_report.md"


def read_pipeline(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read controller packet calibration pipeline report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Pipeline report must be a JSON object: {path}")
    if value.get("schema") != "controller_packet_calibration_pipeline/v1":
        raise ValueError(f"Unsupported pipeline report schema in {path}: {value.get('schema')}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths or [DEFAULT_PIPELINE]


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def proposal_family(kind: str, labels: dict[str, Any] | None = None) -> str:
    text = " ".join([kind, *(labels or {}).keys()]).lower()
    if "ogcf" in text or "bridge" in text:
        return "ogcf_bridge"
    if "missing" in text or "wrong_scope" in text:
        return "missing_support"
    if "stale" in text or "conflict" in text:
        return "stale_conflict"
    if "citation" in text:
        return "citation"
    return "general_answer"


def proposal_key(proposal: dict[str, Any]) -> str:
    kind = str(proposal.get("kind") or "unknown")
    labels = proposal.get("feedback_labels") if isinstance(proposal.get("feedback_labels"), dict) else {}
    family = proposal_family(kind, labels)
    return f"{family}|{kind}"


def load_proposals(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = pipeline.get("artifacts") if isinstance(pipeline.get("artifacts"), dict) else {}
    proposals_path = artifacts.get("proposals_json")
    if not proposals_path:
        return []
    proposals = read_json(Path(proposals_path))
    return [item for item in proposals.get("proposals") or [] if isinstance(item, dict)]


def load_guard_rows(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = pipeline.get("artifacts") if isinstance(pipeline.get("artifacts"), dict) else {}
    guard_path = artifacts.get("guard_json")
    if not guard_path:
        return []
    guard = read_json(Path(guard_path))
    return [item for item in guard.get("guarded_proposals") or [] if isinstance(item, dict)]


def build_report(pipeline_paths: list[Path], *, min_runs: int = 2) -> dict[str, Any]:
    run_summaries: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tier_counts = Counter()
    bridge_holdout_rates: list[float] = []
    bridge_loso_observed_runs = 0
    bridge_loso_candidates = 0
    bridge_loso_source_counts: list[int] = []
    bridge_loso_sample_counts: list[int] = []
    bridge_loso_blockers = Counter()
    for idx, path in enumerate(pipeline_paths, start=1):
        pipeline = read_pipeline(path)
        proposals = load_proposals(pipeline)
        guard_rows = load_guard_rows(pipeline)
        for proposal in proposals:
            grouped[proposal_key(proposal)].append({"run_index": idx, "path": str(path), "proposal": proposal})
        for row in guard_rows:
            tier_counts[str(row.get("readiness_tier") or "unknown")] += 1
        holdout = pipeline.get("bridge_separator_holdout") if isinstance(pipeline.get("bridge_separator_holdout"), dict) else {}
        if isinstance(holdout.get("match_rate"), (int, float)):
            bridge_holdout_rates.append(float(holdout["match_rate"]))
        loso = pipeline.get("bridge_leave_one_source_out") if isinstance(pipeline.get("bridge_leave_one_source_out"), dict) else {}
        if loso:
            bridge_loso_observed_runs += 1
            if loso.get("learned_scorer_candidate"):
                bridge_loso_candidates += 1
            if isinstance(loso.get("source_count"), int):
                bridge_loso_source_counts.append(int(loso["source_count"]))
            if isinstance(loso.get("sample_count"), int):
                bridge_loso_sample_counts.append(int(loso["sample_count"]))
            for blocker in loso.get("readiness_blockers") or []:
                bridge_loso_blockers[str(blocker).split(":", 1)[0]] += 1
        summary = pipeline.get("summary") if isinstance(pipeline.get("summary"), dict) else {}
        run_summaries.append(
            {
                "run_index": idx,
                "path": str(path),
                "ok": bool(pipeline.get("ok")),
                "packet_count": summary.get("packet_count"),
                "proposal_count": summary.get("proposal_count"),
                "promotion_candidate_count": summary.get("promotion_candidate_count"),
                "review_item_count": summary.get("review_item_count"),
                "guard_ready_count": summary.get("guard_ready_count"),
                "guard_blocked_count": summary.get("guard_blocked_count"),
                "next_target": (pipeline.get("calibration_system") or {}).get("next_development_target"),
            }
        )
    clusters: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        run_ids = sorted({int(item["run_index"]) for item in items})
        kinds = Counter(str(item["proposal"].get("kind") or "unknown") for item in items)
        labels = Counter()
        support = 0
        source_logs = 0
        evidence_ready = 0
        related_review_blocked = 0
        examples = []
        for item in items:
            proposal = item["proposal"]
            support += int(proposal.get("support") or 0)
            source_logs += int(proposal.get("source_log_count") or 0)
            proposal_labels = proposal.get("feedback_labels") if isinstance(proposal.get("feedback_labels"), dict) else {}
            labels.update({str(label): int(count or 0) for label, count in proposal_labels.items()})
            if proposal.get("readiness") == "calibration_candidate":
                evidence_ready += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "run_index": item["run_index"],
                        "id": proposal.get("id"),
                        "kind": proposal.get("kind"),
                        "support": proposal.get("support"),
                        "source_log_count": proposal.get("source_log_count"),
                    }
                )
        for path in pipeline_paths:
            pipeline = read_pipeline(path)
            for row in load_guard_rows(pipeline):
                row_key = f"{proposal_family(str(row.get('kind') or 'unknown'))}|{row.get('kind')}"
                if row_key == key and row.get("readiness_tier") == "evidence_ready_blocked_by_related_review":
                    related_review_blocked += 1
        recurring = len(run_ids) >= max(1, int(min_runs))
        if recurring and related_review_blocked:
            recommendation = "build_or_validate_separator_for_recurring_related_review_family"
        elif recurring and evidence_ready:
            recommendation = "collect_holdout_and_prepare_manual_review"
        elif recurring:
            recommendation = "preserve_as_recurring_review_or_collection_signal"
        else:
            recommendation = "collect_more_independent_runs"
        clusters.append(
            {
                "key": key,
                "run_count": len(run_ids),
                "runs": run_ids,
                "proposal_count": len(items),
                "kinds": dict(sorted(kinds.items())),
                "feedback_labels": dict(sorted(labels.items())),
                "combined_support": support,
                "combined_source_log_count": source_logs,
                "evidence_ready_count": evidence_ready,
                "related_review_blocked_count": related_review_blocked,
                "recurring": recurring,
                "recommendation": recommendation,
                "examples": examples,
            }
        )
    recurring_clusters = [cluster for cluster in clusters if cluster["recurring"]]
    avg_bridge_holdout = sum(bridge_holdout_rates) / len(bridge_holdout_rates) if bridge_holdout_rates else None
    loso_observed = bool(bridge_loso_source_counts or bridge_loso_sample_counts or bridge_loso_blockers)
    return {
        "schema": "controller_packet_multirun_calibration/v1",
        "description": "Report-only cross-run aggregation of packet calibration pipeline outputs.",
        "ok": bool(run_summaries) and all(item["ok"] for item in run_summaries),
        "run_count": len(run_summaries),
        "min_runs": max(1, int(min_runs)),
        "runs": run_summaries,
        "proposal_cluster_count": len(clusters),
        "recurring_cluster_count": len(recurring_clusters),
        "guard_readiness_tier_counts": dict(sorted(tier_counts.items())),
        "bridge_holdout": {
            "observed_run_count": len(bridge_holdout_rates),
            "average_match_rate": avg_bridge_holdout,
            "all_clean": bool(bridge_holdout_rates) and all(rate == 1.0 for rate in bridge_holdout_rates),
        },
        "bridge_leave_one_source_out": {
            "observed_run_count": bridge_loso_observed_runs,
            "candidate_run_count": bridge_loso_candidates,
            "max_source_count": max(bridge_loso_source_counts) if bridge_loso_source_counts else None,
            "max_sample_count": max(bridge_loso_sample_counts) if bridge_loso_sample_counts else None,
            "readiness_blocker_counts": dict(sorted(bridge_loso_blockers.items())),
            "all_candidate_ready": loso_observed and bridge_loso_candidates == len(run_summaries),
        },
        "clusters": clusters,
        "next_development_target": "collect_more_independent_bridge_sources_for_loso"
        if loso_observed and bridge_loso_candidates < len(run_summaries)
        else "broader_holdout_for_recurring_clusters"
        if recurring_clusters
        else "collect_more_independent_runs",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Multi-Run Calibration",
        "",
        "This report is advisory only. It does not mutate memory, selector policy, resolver policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Runs: `{report['run_count']}`",
        f"Recurring clusters: `{report['recurring_cluster_count']}`",
        f"Next target: `{report['next_development_target']}`",
        "",
        "## Bridge Holdout",
        "",
        "```json",
        json.dumps(report["bridge_holdout"], indent=2),
        "```",
        "",
        "## Bridge Leave-One-Source-Out",
        "",
        "```json",
        json.dumps(report["bridge_leave_one_source_out"], indent=2),
        "```",
        "",
        "## Clusters",
            "",
        "| recurring | runs | key | support | source logs | labels | recommendation |",
        "| --- | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for cluster in report["clusters"]:
        lines.append(
            "| `{}` | {} | `{}` | {} | {} | `{}` | {} |".format(
                cluster["recurring"],
                cluster["run_count"],
                clean_cell(cluster["key"]),
                cluster["combined_support"],
                cluster["combined_source_log_count"],
                clean_cell(", ".join(cluster["feedback_labels"].keys())),
                clean_cell(cluster["recommendation"]),
            )
        )
    lines.extend(["", "## Runs", ""])
    for run in report["runs"]:
        lines.append(f"- `{run['path']}`: `{run['packet_count']}` packets, `{run['proposal_count']}` proposals")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate multiple controller packet calibration pipeline reports.")
    parser.add_argument("--pipeline", action="append", help="Pipeline result JSON. May repeat or be comma-separated.")
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(parse_paths(args.pipeline), min_runs=args.min_runs)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "run_count": report["run_count"],
                "proposal_cluster_count": report["proposal_cluster_count"],
                "recurring_cluster_count": report["recurring_cluster_count"],
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
