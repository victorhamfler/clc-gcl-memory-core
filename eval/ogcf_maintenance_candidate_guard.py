from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = REPO_ROOT / "experiments" / "ogcf_maintenance_review_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidate_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_candidate_guard_report.md"


ACTION_RECOMMENDATIONS = {
    "exact_duplicate_group": "prepare_duplicate_deprecation_candidate_for_manual_review",
    "semantic_duplicate_group": "prepare_semantic_merge_candidate_for_manual_review",
    "semantic_conflict_or_update_group": "prepare_conflict_update_candidate_for_manual_review",
    "stale_version_candidate": "prepare_stale_deprecation_candidate_for_manual_review",
    "bridge_cluster_review": "prepare_bridge_split_or_canonicalization_review",
}


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def read_bank(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read OGCF maintenance review memory bank {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Memory bank must be a JSON object: {path}")
    if value.get("schema") != "ogcf_maintenance_review_memory_bank/v1":
        raise ValueError(f"Unsupported memory bank schema: {value.get('schema')}")
    return value


def cluster_action(cluster: dict[str, Any]) -> str:
    actions = cluster.get("actions") if isinstance(cluster.get("actions"), dict) else {}
    if not actions:
        return str(cluster.get("key") or "unknown").split("|", 1)[0]
    return max(actions, key=lambda key: int(actions.get(key) or 0))


def cluster_ready(
    cluster: dict[str, Any],
    *,
    min_runs: int,
    min_support: int,
    min_mean_priority: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if cluster.get("readiness") != "maintenance_candidate_evidence_ready":
        reasons.append("not_evidence_ready")
    if int(cluster.get("run_count") or 0) < min_runs:
        reasons.append("insufficient_runs")
    if int(cluster.get("support") or 0) < min_support:
        reasons.append("insufficient_support")
    if float(cluster.get("mean_priority") or 0.0) < min_mean_priority:
        reasons.append("mean_priority_below_threshold")
    if cluster.get("high_priority_negative_ids"):
        reasons.append("high_priority_negative_reviews_present")
    labels = cluster.get("label_classes") if isinstance(cluster.get("label_classes"), dict) else {}
    if int(labels.get("negative") or 0) > 0:
        reasons.append("negative_reviews_present")
    if int(labels.get("useful") or 0) <= 0:
        reasons.append("no_useful_reviews")
    return not reasons, reasons


def proposal_for_cluster(cluster: dict[str, Any], *, ready: bool, reasons: list[str]) -> dict[str, Any]:
    action = cluster_action(cluster)
    key_slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(cluster.get("key") or "unknown")).strip("_")
    candidate_id = f"maintenance_guard:{action}:{key_slug[:80]}"
    return {
        "schema": "ogcf_guarded_maintenance_candidate/v1",
        "id": candidate_id,
        "source_cluster_key": cluster.get("key"),
        "action": action,
        "recommended_action": ACTION_RECOMMENDATIONS.get(action, "manual_maintenance_review_required"),
        "support": cluster.get("support"),
        "run_count": cluster.get("run_count"),
        "runs": cluster.get("runs") or [],
        "mean_priority": cluster.get("mean_priority"),
        "max_priority": cluster.get("max_priority"),
        "label_classes": cluster.get("label_classes") or {},
        "ready_for_manual_review": ready,
        "blocked_reasons": reasons,
        "promotion_ready": False,
        "promotion_blockers": ["manual_review_required", "runtime_mutation_not_allowed"],
        "examples": cluster.get("examples") or [],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_report(
    bank_path: Path,
    *,
    min_runs: int = 2,
    min_support: int = 2,
    min_mean_priority: float = 0.65,
) -> dict[str, Any]:
    bank = read_bank(bank_path)
    proposals = []
    blocked = []
    for cluster in bank.get("clusters") or []:
        if not isinstance(cluster, dict):
            continue
        ready, reasons = cluster_ready(
            cluster,
            min_runs=max(1, int(min_runs)),
            min_support=max(1, int(min_support)),
            min_mean_priority=max(0.0, min(1.0, float(min_mean_priority))),
        )
        row = proposal_for_cluster(cluster, ready=ready, reasons=reasons)
        if ready:
            proposals.append(row)
        else:
            blocked.append(row)
    readiness_counts = Counter(
        "manual_review_candidate" if item.get("ready_for_manual_review") else "blocked"
        for item in [*proposals, *blocked]
    )
    return {
        "schema": "ogcf_maintenance_candidate_guard/v1",
        "description": "Report-only guard for recurring reviewed OGCF maintenance evidence.",
        "source_bank": str(bank_path),
        "bank_schema": bank.get("schema"),
        "cluster_count": len(bank.get("clusters") or []),
        "manual_review_candidate_count": len(proposals),
        "blocked_count": len(blocked),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "thresholds": {
            "min_runs": max(1, int(min_runs)),
            "min_support": max(1, int(min_support)),
            "min_mean_priority": max(0.0, min(1.0, float(min_mean_priority))),
        },
        "guarded_candidates": proposals,
        "blocked_candidates": blocked,
        "next_action": "manual_review_guarded_maintenance_candidates" if proposals else "collect_more_reviewed_maintenance_runs",
        "promotion_ready": False,
        "promotion_blockers": ["manual_review_required", "database_mutation_path_not_implemented"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Candidate Guard",
        "",
        "Report-only guarded candidate review. This does not mutate memory rows, retrieval, selector policy, runtime config, or learned artifacts.",
        "",
        f"Source bank: `{report['source_bank']}`",
        f"Manual-review candidates: `{report['manual_review_candidate_count']}`",
        f"Blocked candidates: `{report['blocked_count']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Guarded Candidates",
        "",
        "| id | action | runs | support | mean priority | ready |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    if not report.get("guarded_candidates"):
        lines.append("| none | none | 0 | 0 | 0 | false |")
    for item in report.get("guarded_candidates") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 80)}` | `{clean_cell(item.get('action'), 60)}` | "
            f"{item.get('run_count')} | {item.get('support')} | {float(item.get('mean_priority') or 0.0):.3f} | "
            f"`{item.get('ready_for_manual_review')}` |"
        )
    lines.extend(["", "## Blocked Summary", "", "```json", json.dumps(report.get("readiness_counts"), indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard reviewed OGCF maintenance evidence into report-only candidates.")
    parser.add_argument("--memory-bank", default=str(DEFAULT_BANK))
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--min-support", type=int, default=2)
    parser.add_argument("--min-mean-priority", type=float, default=0.65)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(
        Path(args.memory_bank),
        min_runs=max(1, int(args.min_runs)),
        min_support=max(1, int(args.min_support)),
        min_mean_priority=max(0.0, min(1.0, float(args.min_mean_priority))),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "manual_review_candidate_count": report["manual_review_candidate_count"],
                "blocked_count": report["blocked_count"],
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
