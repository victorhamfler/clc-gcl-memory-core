from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_review_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_candidate_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_candidate_guard_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def read_bank(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Memory bank must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rehearsal_review_memory_bank/v1":
        raise ValueError(f"Unsupported rehearsal memory bank schema: {value.get('schema')}")
    return value


def operation_kind(cluster: dict[str, Any]) -> str:
    kinds = cluster.get("operation_kinds") if isinstance(cluster.get("operation_kinds"), dict) else {}
    if kinds:
        return max(kinds, key=lambda key: int(kinds.get(key) or 0))
    return str(cluster.get("key") or "unknown").split("|", 1)[0]


def cluster_ready(cluster: dict[str, Any], risky_operation_kinds: set[str]) -> tuple[bool, list[str]]:
    reasons = []
    kind = operation_kind(cluster)
    if cluster.get("readiness") != "rehearsal_safe_evidence_ready":
        reasons.append("not_safe_evidence_ready")
    if kind in risky_operation_kinds:
        reasons.append("operation_family_has_recurrent_risk")
    if int(cluster.get("safe_count") or 0) <= 0:
        reasons.append("no_safe_reviews")
    if int(cluster.get("blocked_count") or 0) > 0:
        reasons.append("cluster_contains_blocked_reviews")
    return not reasons, reasons


def candidate_for_cluster(cluster: dict[str, Any], *, ready: bool, reasons: list[str]) -> dict[str, Any]:
    kind = operation_kind(cluster)
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(cluster.get("key") or "unknown")).strip("_")
    return {
        "schema": "memory_maintenance_rehearsal_guarded_candidate/v1",
        "id": f"rehearsal_guard:{kind}:{slug[:80]}",
        "source_cluster_key": cluster.get("key"),
        "operation_kind": kind,
        "recommended_action": "operator_review_duplicate_deprecation_candidate"
        if kind == "duplicate_deprecation"
        else "operator_review_maintenance_candidate",
        "support": cluster.get("support"),
        "run_count": cluster.get("run_count"),
        "runs": cluster.get("runs") or [],
        "safe_count": cluster.get("safe_count"),
        "blocked_count": cluster.get("blocked_count"),
        "readiness": cluster.get("readiness"),
        "rpg_summary": cluster.get("rpg_summary") or {},
        "ready_for_operator_review": ready,
        "blocked_reasons": reasons,
        "promotion_ready": False,
        "promotion_blockers": ["operator_review_required", "database_mutation_disabled_by_default"],
        "examples": cluster.get("examples") or [],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_report(bank_path: Path) -> dict[str, Any]:
    bank = read_bank(bank_path)
    clusters = [item for item in bank.get("clusters") or [] if isinstance(item, dict)]
    risky_operation_kinds = {
        operation_kind(cluster)
        for cluster in clusters
        if cluster.get("readiness") == "blocked_recurrent_risk"
    }
    guarded = []
    blocked = []
    for cluster in clusters:
        ready, reasons = cluster_ready(cluster, risky_operation_kinds)
        row = candidate_for_cluster(cluster, ready=ready, reasons=reasons)
        if ready:
            guarded.append(row)
        else:
            blocked.append(row)
    readiness_counts = Counter(
        "operator_review_candidate" if item.get("ready_for_operator_review") else "blocked"
        for item in [*guarded, *blocked]
    )
    return {
        "schema": "memory_maintenance_rehearsal_candidate_guard/v1",
        "description": "Report-only guard for copied-DB rehearsal evidence before operator review.",
        "source_bank": str(bank_path),
        "bank_schema": bank.get("schema"),
        "cluster_count": len(clusters),
        "operator_review_candidate_count": len(guarded),
        "blocked_count": len(blocked),
        "risky_operation_kinds": sorted(risky_operation_kinds),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "guarded_candidates": guarded,
        "blocked_candidates": blocked,
        "next_action": "operator_review_guarded_rehearsal_candidates"
        if guarded
        else "resolve_recurrent_risk_or_collect_more_rehearsals",
        "promotion_ready": False,
        "promotion_blockers": ["operator_review_required", "database_mutation_disabled_by_default"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rehearsal Candidate Guard",
        "",
        "Report-only guard for copied-DB rehearsal evidence.",
        "",
        f"Operator-review candidates: `{report['operator_review_candidate_count']}`",
        f"Blocked candidates: `{report['blocked_count']}`",
        f"Risky operation kinds: `{', '.join(report['risky_operation_kinds']) or 'none'}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Guarded Candidates",
        "",
        "| id | operation | runs | support | ready |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    if not report.get("guarded_candidates"):
        lines.append("| none | none | 0 | 0 | false |")
    for item in report.get("guarded_candidates") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 80)}` | `{clean_cell(item.get('operation_kind'), 60)}` | "
            f"{item.get('run_count')} | {item.get('support')} | `{item.get('ready_for_operator_review')}` |"
        )
    lines.extend(["", "## Blocked Candidates", "", "| id | operation | reasons |", "| --- | --- | --- |"])
    if not report.get("blocked_candidates"):
        lines.append("| none | none | none |")
    for item in report.get("blocked_candidates") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 80)}` | `{clean_cell(item.get('operation_kind'), 60)}` | "
            f"`{clean_cell(', '.join(item.get('blocked_reasons') or []), 120)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard rehearsal review memory-bank clusters into operator-review candidates.")
    parser.add_argument("--memory-bank", default=str(DEFAULT_BANK))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.memory_bank))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "operator_review_candidate_count": report["operator_review_candidate_count"],
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
