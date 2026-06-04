from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_CANDIDATES_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_review_queue.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_review_queue.md"
OUT_LABELS = REPO_ROOT / "experiments" / "ogcf_maintenance_review_labels_template.json"

ALLOWED_LABELS = (
    "useful_review",
    "noisy_review",
    "needs_more_evidence",
    "clean_memory",
    "unsafe_to_act",
    "already_resolved",
)


def clean_cell(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def priority_score(candidate: dict[str, Any]) -> float:
    priority = candidate.get("maintenance_priority") if isinstance(candidate.get("maintenance_priority"), dict) else {}
    return float(priority.get("priority_score") or candidate.get("confidence") or 0.0)


def priority_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def candidate_memory_ids(candidate: dict[str, Any]) -> list[str]:
    ids = []
    keeper = str(candidate.get("keeper_memory_id") or "").strip()
    if keeper:
        ids.append(keeper)
    for item in candidate.get("candidate_memory_ids") or []:
        value = str(item or "").strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def review_prompt(candidate: dict[str, Any]) -> str:
    action = str(candidate.get("action") or "")
    if action == "exact_duplicate_group":
        return "Check whether the candidate memories are exact duplicates and whether deprecating non-keepers would preserve all useful information."
    if action == "semantic_duplicate_group":
        return "Check whether these memories are paraphrases that can be merged without losing useful distinctions."
    if action == "semantic_conflict_or_update_group":
        return "Check whether this is a real correction/update conflict and which memory should remain authoritative."
    if action == "stale_version_candidate":
        return "Check whether the stale candidate is superseded by the keeper/current memory."
    if action == "bridge_cluster_review":
        return "Check whether the bridge cluster mixes domains that should be split, canonicalized, or left alone."
    return "Review whether this maintenance candidate is useful, noisy, or needs more evidence."


def build_review_queue(
    report: dict[str, Any],
    *,
    source_path: str | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    candidates = [item for item in report.get("candidates") or [] if isinstance(item, dict)]
    ranked = sorted(candidates, key=priority_score, reverse=True)
    if top_k is not None:
        ranked = ranked[: max(0, int(top_k))]
    items = []
    for rank, candidate in enumerate(ranked, start=1):
        score = priority_score(candidate)
        items.append(
            {
                "schema": "ogcf_maintenance_review_queue_item/v1",
                "rank": rank,
                "candidate_id": str(candidate.get("id") or ""),
                "action": candidate.get("action"),
                "recommendation": candidate.get("recommendation"),
                "priority_score": round(score, 6),
                "priority_band": priority_band(score),
                "support": candidate.get("support"),
                "confidence": candidate.get("confidence"),
                "keeper_memory_id": candidate.get("keeper_memory_id"),
                "candidate_memory_ids": candidate_memory_ids(candidate),
                "sample_text": candidate.get("sample_text"),
                "projector_graph": candidate.get("projector_graph") if isinstance(candidate.get("projector_graph"), dict) else {},
                "maintenance_priority": candidate.get("maintenance_priority")
                if isinstance(candidate.get("maintenance_priority"), dict)
                else {},
                "review_prompt": review_prompt(candidate),
                "allowed_labels": list(ALLOWED_LABELS),
                "report_only": True,
                "mutates_db": False,
            }
        )
    return {
        "schema": "ogcf_maintenance_review_queue/v1",
        "source_report_path": source_path,
        "source_report_schema": report.get("schema"),
        "candidate_count": len(candidates),
        "queue_count": len(items),
        "priority_summary": report.get("maintenance_priority_summary") or {},
        "items": items,
        "label_schema": "ogcf_maintenance_review_labels/v1",
        "allowed_labels": list(ALLOWED_LABELS),
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_label_template(queue: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "ogcf_maintenance_review_labels/v1",
        "source_queue_schema": queue.get("schema"),
        "source_report_path": queue.get("source_report_path"),
        "allowed_labels": list(ALLOWED_LABELS),
        "labels": [
            {
                "candidate_id": item.get("candidate_id"),
                "label": "",
                "reviewer": "",
                "reason": "",
                "recommended_action": "",
            }
            for item in queue.get("items") or []
        ],
        "report_only": True,
        "mutates_db": False,
    }


def write_queue(queue: dict[str, Any], label_template: dict[str, Any], out_json: Path, out_md: Path, labels_out: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    labels_out.write_text(json.dumps(label_template, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Review Queue",
        "",
        "Report-only review queue. This file does not mutate memory rows, selector policy, runtime config, or learned artifacts.",
        "",
        f"Source report: `{queue.get('source_report_path')}`",
        f"Queue count: **{queue.get('queue_count')}**",
        "",
        "## Items",
        "",
        "| rank | candidate | action | priority | band | prompt |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    if not queue.get("items"):
        lines.append("| 0 | none | none | 0 | low | no review candidates |")
    for item in queue.get("items") or []:
        lines.append(
            f"| {item.get('rank')} | `{clean_cell(item.get('candidate_id'), 80)}` | "
            f"`{clean_cell(item.get('action'), 60)}` | {float(item.get('priority_score') or 0.0):.3f} | "
            f"`{item.get('priority_band')}` | {clean_cell(item.get('review_prompt'))} |"
        )
    lines.extend(
        [
            "",
            "## Label Template",
            "",
            f"Write reviewed labels to `{labels_out}` or another JSON/JSONL file with schema `ogcf_maintenance_review_labels/v1`.",
            "",
            "Allowed labels: `" + "`, `".join(ALLOWED_LABELS) + "`.",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report-only OGCF maintenance review queue.")
    parser.add_argument("--candidates-json", default=str(DEFAULT_CANDIDATES_JSON))
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--labels-template", default=str(OUT_LABELS))
    args = parser.parse_args()

    candidates_path = Path(args.candidates_json)
    report = json.loads(candidates_path.read_text(encoding="utf-8"))
    queue = build_review_queue(report, source_path=str(candidates_path), top_k=args.top_k)
    label_template = build_label_template(queue)
    write_queue(queue, label_template, Path(args.out_json), Path(args.out_md), Path(args.labels_template))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": queue["schema"],
                "queue_count": queue["queue_count"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "labels_template": str(Path(args.labels_template)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
