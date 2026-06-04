from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ogcf_maintenance_review_label_eval import build_eval, load_json_or_jsonl


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_results.json"
DEFAULT_LABELS = REPO_ROOT / "experiments" / "ogcf_maintenance_review_labels_template.json"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_review_memory_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_review_memory_bank_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def parse_pair(value: str) -> tuple[Path, Path]:
    if "::" in value:
        left, right = value.split("::", 1)
    elif "," in value:
        left, right = value.split(",", 1)
    else:
        raise ValueError(f"Review run must be '<candidates.json>::<labels.json>': {value}")
    return Path(left.strip()), Path(right.strip())


def parse_runs(values: list[str] | None) -> list[tuple[Path, Path]]:
    if not values:
        return [(DEFAULT_CANDIDATES, DEFAULT_LABELS)]
    runs: list[tuple[Path, Path]] = []
    for value in values:
        for part in str(value).split(";"):
            if part.strip():
                runs.append(parse_pair(part.strip()))
    return runs


def row_family(row: dict[str, Any]) -> str:
    action = str(row.get("action") or "unknown")
    label_class = str(row.get("label_class") or "unknown")
    return f"{action}|{label_class}"


def readiness_for_cluster(
    *,
    run_count: int,
    useful_count: int,
    negative_count: int,
    high_priority_negative_count: int,
    min_runs: int,
    min_useful: int,
) -> str:
    if high_priority_negative_count:
        return "blocked_high_priority_negative"
    if useful_count and negative_count:
        return "review_mixed_outcomes"
    if negative_count:
        return "review_negative_outcomes"
    if run_count >= min_runs and useful_count >= min_useful:
        return "maintenance_candidate_evidence_ready"
    if useful_count:
        return "hold_collect_more_useful_reviews"
    return "hold_collect_more_labels"


def build_memory_bank(
    runs: list[tuple[Path, Path]],
    *,
    top_k: int = 5,
    min_runs: int = 2,
    min_useful: int = 2,
) -> dict[str, Any]:
    run_reports: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for idx, (candidates_path, labels_path) in enumerate(runs, start=1):
        candidates_report = json.loads(candidates_path.read_text(encoding="utf-8"))
        labels_raw = load_json_or_jsonl(labels_path)
        evaluation = build_eval(candidates_report, labels_raw, top_k=top_k)
        run_report = {
            "run_index": idx,
            "candidates_path": str(candidates_path),
            "labels_path": str(labels_path),
            "schema": "ogcf_maintenance_review_memory_bank_run/v1",
            "labeled_count": evaluation.get("labeled_count"),
            "useful_count": evaluation.get("useful_count"),
            "negative_count": evaluation.get("negative_count"),
            "neutral_count": evaluation.get("neutral_count"),
            "precision_at_k": evaluation.get("precision_at_k"),
            "negative_at_k": evaluation.get("negative_at_k"),
            "high_priority_negative_ids": evaluation.get("high_priority_negative_ids") or [],
            "priority_separates_useful": evaluation.get("priority_separates_useful"),
        }
        run_reports.append(run_report)
        for row in evaluation.get("ranked") or []:
            item = dict(row)
            item["run_index"] = idx
            item["candidates_path"] = str(candidates_path)
            item["labels_path"] = str(labels_path)
            grouped[row_family(item)].append(item)

    clusters: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        labels = Counter(str(row.get("label_class") or "unknown") for row in rows)
        actions = Counter(str(row.get("action") or "unknown") for row in rows)
        run_ids = sorted({int(row["run_index"]) for row in rows})
        useful_count = int(labels.get("useful") or 0)
        negative_count = int(labels.get("negative") or 0)
        high_priority_negative_ids = [
            str(row.get("candidate_id") or "")
            for row in rows
            if row.get("label_class") == "negative" and float(row.get("priority_score") or 0.0) >= 0.85
        ]
        scores = [float(row.get("priority_score") or 0.0) for row in rows]
        clusters.append(
            {
                "schema": "ogcf_maintenance_review_memory_bank_cluster/v1",
                "key": key,
                "run_count": len(run_ids),
                "runs": run_ids,
                "support": len(rows),
                "actions": dict(sorted(actions.items())),
                "label_classes": dict(sorted(labels.items())),
                "mean_priority": round(sum(scores) / max(1, len(scores)), 6),
                "max_priority": round(max(scores), 6) if scores else 0.0,
                "high_priority_negative_ids": high_priority_negative_ids,
                "readiness": readiness_for_cluster(
                    run_count=len(run_ids),
                    useful_count=useful_count,
                    negative_count=negative_count,
                    high_priority_negative_count=len(high_priority_negative_ids),
                    min_runs=max(1, int(min_runs)),
                    min_useful=max(1, int(min_useful)),
                ),
                "examples": rows[:5],
            }
        )

    readiness_counts = Counter(cluster["readiness"] for cluster in clusters)
    high_priority_negative_ids = [
        candidate_id
        for report in run_reports
        for candidate_id in report.get("high_priority_negative_ids") or []
    ]
    evidence_ready = [cluster for cluster in clusters if cluster["readiness"] == "maintenance_candidate_evidence_ready"]
    return {
        "schema": "ogcf_maintenance_review_memory_bank/v1",
        "description": "Report-only multi-run aggregation of reviewed OGCF maintenance labels.",
        "run_count": len(run_reports),
        "min_runs": max(1, int(min_runs)),
        "min_useful": max(1, int(min_useful)),
        "runs": run_reports,
        "cluster_count": len(clusters),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "evidence_ready_count": len(evidence_ready),
        "high_priority_negative_ids": high_priority_negative_ids,
        "next_action": "prepare_guarded_maintenance_candidate_review"
        if evidence_ready and not high_priority_negative_ids
        else "collect_more_reviewed_maintenance_runs",
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
        "# OGCF Maintenance Review Memory Bank",
        "",
        "Report-only multi-run aggregation. This does not mutate memory rows, selector policy, runtime config, or learned artifacts.",
        "",
        f"Runs: `{report['run_count']}`",
        f"Clusters: `{report['cluster_count']}`",
        f"Evidence-ready clusters: `{report['evidence_ready_count']}`",
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
        "| key | runs | support | mean priority | readiness |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    if not report.get("clusters"):
        lines.append("| none | 0 | 0 | 0 | hold_collect_more_labels |")
    for cluster in report.get("clusters") or []:
        lines.append(
            f"| `{clean_cell(cluster.get('key'), 80)}` | {cluster.get('run_count')} | "
            f"{cluster.get('support')} | {float(cluster.get('mean_priority') or 0.0):.3f} | "
            f"`{cluster.get('readiness')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate reviewed OGCF maintenance labels across runs.")
    parser.add_argument(
        "--run",
        action="append",
        help="Pair as '<candidates.json>::<labels.json>'. Repeat or separate multiple pairs with ';'.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--min-useful", type=int, default=2)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_memory_bank(
        parse_runs(args.run),
        top_k=max(1, int(args.top_k)),
        min_runs=max(1, int(args.min_runs)),
        min_useful=max(1, int(args.min_useful)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "run_count": report["run_count"],
                "cluster_count": report["cluster_count"],
                "evidence_ready_count": report["evidence_ready_count"],
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
