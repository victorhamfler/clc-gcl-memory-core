from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REHEARSAL = REPO_ROOT / "experiments" / "memory_maintenance_copied_db_rehearsal_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_review_memory_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_review_memory_bank_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def parse_runs(values: list[str] | None) -> list[Path]:
    if not values:
        return [DEFAULT_REHEARSAL]
    runs: list[Path] = []
    for value in values:
        for part in str(value).split(";"):
            if part.strip():
                runs.append(Path(part.strip()))
    return runs


def review_family(review: dict[str, Any]) -> str:
    operation_kind = str(review.get("operation_kind") or "unknown")
    decision = str(review.get("decision") or "unknown")
    return f"{operation_kind}|{decision}"


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def rpg_annotation_by_candidate(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rpg = report.get("rpg_rehearsal_annotations") if isinstance(report.get("rpg_rehearsal_annotations"), dict) else {}
    annotations = [item for item in rpg.get("operation_annotations") or [] if isinstance(item, dict)]
    return {str(item.get("candidate_id") or ""): item for item in annotations if str(item.get("candidate_id") or "")}


def rpg_cluster_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    annotations = [
        row.get("rpg_annotation")
        for row in rows
        if isinstance(row.get("rpg_annotation"), dict)
    ]
    target_relations = [float(item.get("target_mean_relation") or 0.0) for item in annotations]
    target_islands = [float(item.get("target_island_ratio") or 0.0) for item in annotations]
    sector_islands = [float(item.get("island_ratio") or 0.0) for item in annotations]
    omega_norms = [float(item.get("omega_norm") or 0.0) for item in annotations]
    target_overlaps = [float(item.get("target_sector_overlap") or 0.0) for item in annotations]
    target_counts = [float(item.get("target_count") or 0.0) for item in annotations]
    duplicate_contradiction = [float(item.get("duplicate_contradiction_sector_overlap") or 0.0) for item in annotations]
    active_deprecated = [float(item.get("active_deprecated_sector_overlap") or 0.0) for item in annotations]
    overlap_ratios = [
        overlap / max(count, 1.0)
        for overlap, count in zip(target_overlaps, target_counts)
    ]
    risk_flags = Counter(
        str(flag)
        for item in annotations
        for flag in (item.get("risk_flags") or [])
    )
    return {
        "schema": "memory_maintenance_rehearsal_rpg_cluster_summary/v1",
        "annotation_count": len(annotations),
        "target_mean_relation_mean": round(average(target_relations), 6),
        "target_mean_relation_min": round(min(target_relations), 6) if target_relations else 0.0,
        "target_mean_relation_max": round(max(target_relations), 6) if target_relations else 0.0,
        "target_island_ratio_mean": round(average(target_islands), 6),
        "sector_island_ratio_mean": round(average(sector_islands), 6),
        "omega_norm_mean": round(average(omega_norms), 12),
        "target_sector_overlap_ratio_mean": round(average(overlap_ratios), 6),
        "duplicate_contradiction_overlap_mean": round(average(duplicate_contradiction), 6),
        "active_deprecated_overlap_mean": round(average(active_deprecated), 6),
        "risk_flags": dict(sorted(risk_flags.items())),
        "report_only": True,
        "mutates_db": False,
    }


def readiness_for_cluster(
    *,
    decision: str,
    run_count: int,
    support: int,
    blocked_count: int,
    min_runs: int,
    min_safe: int,
) -> str:
    if decision == "safe_to_review" and blocked_count == 0 and run_count >= min_runs and support >= min_safe:
        return "rehearsal_safe_evidence_ready"
    if decision == "safe_to_review":
        return "hold_collect_more_safe_rehearsals"
    if decision.startswith("blocked_"):
        return "blocked_recurrent_risk" if run_count >= min_runs else "hold_monitor_blocked_risk"
    return "needs_operator_review_recurrent" if run_count >= min_runs else "hold_collect_more_rehearsals"


def build_memory_bank(
    run_paths: list[Path],
    *,
    min_runs: int = 2,
    min_safe: int = 2,
) -> dict[str, Any]:
    run_reports = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, path in enumerate(run_paths, start=1):
        report = load_json(path)
        summary = report.get("review_summary") if isinstance(report.get("review_summary"), dict) else {}
        rpg_by_candidate = rpg_annotation_by_candidate(report)
        reviews = [item for item in summary.get("reviews") or [] if isinstance(item, dict)]
        decision_counts = Counter(str(item.get("decision") or "unknown") for item in reviews)
        run_reports.append(
            {
                "schema": "memory_maintenance_rehearsal_review_memory_bank_run/v1",
                "run_index": index,
                "path": str(path),
                "source_schema": report.get("schema"),
                "overall_decision": summary.get("overall_decision"),
                "operation_review_count": len(reviews),
                "decision_counts": dict(sorted(decision_counts.items())),
                "rpg_annotation_count": len(rpg_by_candidate),
                "mutates_source_db": bool(report.get("mutates_source_db")),
                "report_only": True,
            }
        )
        for review in reviews:
            row = dict(review)
            row["run_index"] = index
            row["run_path"] = str(path)
            annotation = rpg_by_candidate.get(str(row.get("candidate_id") or ""))
            if annotation:
                row["rpg_annotation"] = annotation
            grouped[review_family(row)].append(row)

    clusters = []
    for key, rows in sorted(grouped.items()):
        decisions = Counter(str(row.get("decision") or "unknown") for row in rows)
        operations = Counter(str(row.get("operation_kind") or "unknown") for row in rows)
        run_ids = sorted({int(row["run_index"]) for row in rows})
        decision = key.split("|", 1)[1] if "|" in key else "unknown"
        blocked_count = sum(count for label, count in decisions.items() if label.startswith("blocked_"))
        clusters.append(
            {
                "schema": "memory_maintenance_rehearsal_review_memory_bank_cluster/v1",
                "key": key,
                "run_count": len(run_ids),
                "runs": run_ids,
                "support": len(rows),
                "operation_kinds": dict(sorted(operations.items())),
                "decisions": dict(sorted(decisions.items())),
                "blocked_count": blocked_count,
                "safe_count": int(decisions.get("safe_to_review") or 0),
                "rpg_summary": rpg_cluster_summary(rows),
                "readiness": readiness_for_cluster(
                    decision=decision,
                    run_count=len(run_ids),
                    support=len(rows),
                    blocked_count=blocked_count,
                    min_runs=max(1, int(min_runs)),
                    min_safe=max(1, int(min_safe)),
                ),
                "examples": rows[:5],
            }
        )
    readiness_counts = Counter(str(cluster.get("readiness") or "unknown") for cluster in clusters)
    safe_ready = [item for item in clusters if item.get("readiness") == "rehearsal_safe_evidence_ready"]
    recurrent_risk = [item for item in clusters if item.get("readiness") == "blocked_recurrent_risk"]
    return {
        "schema": "memory_maintenance_rehearsal_review_memory_bank/v1",
        "description": "Report-only aggregation of copied-DB rehearsal review decisions.",
        "run_count": len(run_reports),
        "min_runs": max(1, int(min_runs)),
        "min_safe": max(1, int(min_safe)),
        "runs": run_reports,
        "cluster_count": len(clusters),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "safe_evidence_ready_count": len(safe_ready),
        "recurrent_risk_count": len(recurrent_risk),
        "rpg_cluster_summary_count": sum(
            1 for item in clusters if (item.get("rpg_summary") or {}).get("annotation_count", 0) > 0
        ),
        "next_action": "prepare_operator_review_for_recurring_safe_duplicate_deprecation"
        if safe_ready and not recurrent_risk
        else "review_or_collect_more_copied_db_rehearsals",
        "clusters": clusters,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rehearsal Review Memory Bank",
        "",
        "Report-only multi-run aggregation of copied-DB rehearsal decisions.",
        "",
        f"Runs: `{report['run_count']}`",
        f"Clusters: `{report['cluster_count']}`",
        f"Safe evidence-ready clusters: `{report['safe_evidence_ready_count']}`",
        f"Recurrent risk clusters: `{report['recurrent_risk_count']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Readiness Counts",
        "",
        "```json",
        json.dumps(report.get("readiness_counts"), indent=2),
        "```",
        "",
        "## Clusters",
        "",
        "| key | runs | support | safe | blocked | RPG target relation | RPG annotations | readiness |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if not report.get("clusters"):
        lines.append("| none | 0 | 0 | 0 | 0 | hold_collect_more_rehearsals |")
    for cluster in report.get("clusters") or []:
        lines.append(
            f"| `{clean_cell(cluster.get('key'), 90)}` | {cluster.get('run_count')} | "
            f"{cluster.get('support')} | {cluster.get('safe_count')} | {cluster.get('blocked_count')} | "
            f"{(cluster.get('rpg_summary') or {}).get('target_mean_relation_mean')} | "
            f"{(cluster.get('rpg_summary') or {}).get('annotation_count')} | "
            f"`{cluster.get('readiness')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate copied-DB rehearsal review summaries across runs.")
    parser.add_argument("--run", action="append", help="Path to rehearsal JSON. Repeat or separate with ';'.")
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--min-safe", type=int, default=2)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_memory_bank(
        parse_runs(args.run),
        min_runs=max(1, int(args.min_runs)),
        min_safe=max(1, int(args.min_safe)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "run_count": report["run_count"],
                "cluster_count": report["cluster_count"],
                "safe_evidence_ready_count": report["safe_evidence_ready_count"],
                "recurrent_risk_count": report["recurrent_risk_count"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
