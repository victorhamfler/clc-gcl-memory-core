from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_reviewed_label_batch_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_reviewed_label_batch_report.md"

LABEL_OPTIONS = [
    "safe_duplicate",
    "stale_or_update_conflict",
    "bridge_contamination",
    "semantic_near_duplicate",
    "harmless_related_memory",
    "uncertain_needs_more_context",
]


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def item(
    index: int,
    *,
    candidate_class: str,
    review_label: str,
    relation: float,
    island: float,
    cosine: float,
    jaccard: float,
    same_domain: bool,
) -> dict[str, Any]:
    left_domain = "memory_core" if same_domain else f"domain_{index}_left"
    right_domain = "memory_core" if same_domain else f"domain_{index}_right"
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"reviewed_fixture:{index:03d}:{candidate_class}:{review_label}",
        "candidate_class": candidate_class,
        "source_db": "local_reviewed_fixture.db",
        "left_memory_id": f"fixture_left_{index:03d}",
        "right_memory_id": f"fixture_right_{index:03d}",
        "left_domain": left_domain,
        "right_domain": right_domain,
        "same_domain": same_domain,
        "cosine": round(cosine, 6),
        "jaccard": round(jaccard, 6),
        "rpg_target_relation": round(relation, 6),
        "rpg_target_island_ratio": round(island, 6),
        "left_preview": f"Reviewed fixture left memory {index} for {candidate_class}.",
        "right_preview": f"Reviewed fixture right memory {index} labeled {review_label}.",
        "review_hint": "local_balanced_review_fixture",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": review_label,
        "reviewer": "local_fixture",
        "review_notes": "Synthetic balanced label batch for report-only scorer pressure testing.",
        "mutation_allowed": False,
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_packet() -> dict[str, Any]:
    specs = [
        ("near_duplicate_like", "safe_duplicate", 0.82, 1.42, 0.96, 0.72, True),
        ("near_duplicate_like", "safe_duplicate", 0.79, 1.39, 0.94, 0.68, True),
        ("exact_duplicate", "safe_duplicate", 0.86, 1.47, 0.99, 0.9, True),
        ("stale_or_update_like", "stale_or_update_conflict", 0.7, 1.34, 0.88, 0.42, True),
        ("stale_or_update_like", "stale_or_update_conflict", 0.67, 1.31, 0.86, 0.39, True),
        ("stale_or_update_like", "stale_or_update_conflict", 0.64, 1.27, 0.83, 0.36, True),
        ("bridge_like", "bridge_contamination", 0.5, 1.18, 0.64, 0.18, False),
        ("bridge_like", "bridge_contamination", 0.47, 1.16, 0.61, 0.16, False),
        ("bridge_like", "bridge_contamination", 0.44, 1.14, 0.58, 0.14, False),
        ("near_duplicate_like", "semantic_near_duplicate", 0.58, 1.24, 0.9, 0.3, True),
        ("near_duplicate_like", "semantic_near_duplicate", 0.55, 1.22, 0.87, 0.27, True),
        ("near_duplicate_like", "semantic_near_duplicate", 0.52, 1.2, 0.84, 0.24, True),
        ("cross_domain_related", "harmless_related_memory", 0.22, 1.06, 0.42, 0.08, False),
        ("cross_domain_related", "harmless_related_memory", 0.2, 1.05, 0.4, 0.07, False),
        ("cross_domain_related", "harmless_related_memory", 0.18, 1.04, 0.38, 0.06, False),
        ("unknown", "uncertain_needs_more_context", 0.34, 1.11, 0.51, 0.12, True),
        ("bridge_like", "uncertain_needs_more_context", 0.36, 1.12, 0.54, 0.13, False),
        ("cross_domain_related", "uncertain_needs_more_context", 0.3, 1.09, 0.47, 0.1, False),
    ]
    items = [
        item(
            index,
            candidate_class=candidate_class,
            review_label=review_label,
            relation=relation,
            island=island,
            cosine=cosine,
            jaccard=jaccard,
            same_domain=same_domain,
        )
        for index, (candidate_class, review_label, relation, island, cosine, jaccard, same_domain) in enumerate(
            specs, start=1
        )
    ]
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "Balanced local reviewed RPG candidate-label batch for report-only scorer pressure testing.",
        "source_schema": "memory_maintenance_rpg_reviewed_label_batch/v1",
        "source_pair_count": len(items),
        "packet_item_count": len(items),
        "class_counts": dict(sorted(Counter(item["candidate_class"] for item in items).items())),
        "label_counts": dict(sorted(Counter(item["review_label"] for item in items).items())),
        "allowed_labels": LABEL_OPTIONS,
        "review_instructions": [
            "Synthetic reviewed fixture for development only.",
            "Use to test label-bank, label-quality, and scorer behavior before real/Hermes labels are available.",
        ],
        "items": items,
        "next_action": "run_label_quality_and_scorer_on_reviewed_batch",
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["synthetic_fixture_not_real_reviewed_outcome", "real_outcome_validation_required"],
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(packet: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Reviewed Label Batch",
        "",
        "Balanced local reviewed RPG candidate-label batch for report-only scorer pressure testing.",
        "",
        f"Items: `{packet['packet_item_count']}`",
        f"Ready for policy use: `{packet['ready_for_policy_use']}`",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(packet.get("label_counts"), indent=2),
        "```",
        "",
        "## Class Counts",
        "",
        "```json",
        json.dumps(packet.get("class_counts"), indent=2),
        "```",
        "",
        "## Items",
        "",
        "| id | class | label | relation | island |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for row in packet.get("items") or []:
        lines.append(
            f"| `{clean_cell(row.get('id'), 70)}` | `{row.get('candidate_class')}` | "
            f"`{row.get('review_label')}` | {row.get('rpg_target_relation')} | "
            f"{row.get('rpg_target_island_ratio')} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a balanced reviewed RPG label batch fixture.")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = build_packet()
    write_report(packet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": packet["schema"],
                "packet_item_count": packet["packet_item_count"],
                "label_counts": packet["label_counts"],
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
