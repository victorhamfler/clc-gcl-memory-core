from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NATURAL = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_report.md"


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


def load_natural(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Natural RPG calibration must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_natural_candidate_calibration/v1":
        raise ValueError(f"Unsupported natural RPG calibration schema: {value.get('schema')}")
    return value


def review_hint(candidate_class: str) -> str:
    if candidate_class == "near_duplicate_like":
        return "check_if_safe_duplicate_or_semantic_near_duplicate"
    if candidate_class == "stale_or_update_like":
        return "check_if_newer_memory_supersedes_or_corrects_older_memory"
    if candidate_class == "bridge_like":
        return "check_if_pair_links_domains_that_should_stay_separate"
    if candidate_class == "cross_domain_related":
        return "check_if_cross_domain_relation_is_useful_or_contaminating"
    if candidate_class == "exact_duplicate":
        return "check_if_exact_duplicate_can_be_canonicalized"
    return "check_memory_relation_manually"


def rank_pairs(pairs: list[dict[str, Any]], *, per_class: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        grouped[str(pair.get("candidate_class") or "unknown")].append(pair)
    selected: list[dict[str, Any]] = []
    for klass in sorted(grouped):
        rows = sorted(
            grouped[klass],
            key=lambda item: (
                -float(item.get("rpg_target_relation") or 0.0),
                -float(item.get("rpg_target_island_ratio") or 0.0),
                str(item.get("left_id") or ""),
            ),
        )
        selected.extend(rows[: max(1, int(per_class))])
    return selected


def packet_item(pair: dict[str, Any], *, index: int) -> dict[str, Any]:
    klass = str(pair.get("candidate_class") or "unknown")
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"rpg_natural_review:{index:04d}:{klass}:{pair.get('left_id')}:{pair.get('right_id')}",
        "candidate_class": klass,
        "source_db": pair.get("source_db"),
        "left_memory_id": pair.get("left_id"),
        "right_memory_id": pair.get("right_id"),
        "left_domain": pair.get("left_domain"),
        "right_domain": pair.get("right_domain"),
        "same_domain": pair.get("same_domain"),
        "cosine": pair.get("cosine"),
        "jaccard": pair.get("jaccard"),
        "rpg_target_relation": pair.get("rpg_target_relation"),
        "rpg_target_island_ratio": pair.get("rpg_target_island_ratio"),
        "left_preview": pair.get("left_preview"),
        "right_preview": pair.get("right_preview"),
        "review_hint": review_hint(klass),
        "allowed_labels": LABEL_OPTIONS,
        "review_label": "",
        "reviewer": "",
        "review_notes": "",
        "mutation_allowed": False,
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_packet(natural: dict[str, Any], *, per_class: int = 8) -> dict[str, Any]:
    pairs = [item for item in natural.get("sample_pairs") or [] if isinstance(item, dict)]
    selected = rank_pairs(pairs, per_class=per_class)
    items = [packet_item(pair, index=index) for index, pair in enumerate(selected, start=1)]
    class_counts = Counter(str(item.get("candidate_class") or "unknown") for item in items)
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "Human/Hermes labeling packet for naturally mined RPG memory-maintenance candidate pairs.",
        "source_schema": natural.get("schema"),
        "source_pair_count": natural.get("all_pair_count"),
        "packet_item_count": len(items),
        "class_counts": dict(sorted(class_counts.items())),
        "allowed_labels": LABEL_OPTIONS,
        "review_instructions": [
            "Label each pair by semantic maintenance meaning, not by RPG score alone.",
            "Use safe_duplicate only when the two memories express the same current fact and one could be canonicalized without losing useful provenance.",
            "Use stale_or_update_conflict when one memory appears older, superseded, or temporally incompatible with the other.",
            "Use bridge_contamination when a cross-domain relation could pollute retrieval or merge topics that should stay separate.",
            "Use harmless_related_memory when the relation is useful context but no maintenance action should be proposed.",
            "Leave uncertain_needs_more_context when provenance, recency, or meaning is insufficient.",
        ],
        "items": items,
        "next_action": "collect_review_labels_for_rpg_natural_candidates",
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["review_labels_required", "real_outcome_validation_required"],
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
        "# Memory Maintenance RPG Natural Candidate Review Packet",
        "",
        "Human/Hermes labeling packet for naturally mined RPG candidate pairs.",
        "",
        f"Items: `{packet['packet_item_count']}`",
        f"Ready for policy use: `{packet['ready_for_policy_use']}`",
        f"Next action: `{packet['next_action']}`",
        "",
        "## Class Counts",
        "",
        "```json",
        json.dumps(packet.get("class_counts"), indent=2),
        "```",
        "",
        "## Items",
        "",
        "| id | class | relation | island | hint | left | right |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for item in packet.get("items") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 70)}` | `{item.get('candidate_class')}` | "
            f"{item.get('rpg_target_relation')} | {item.get('rpg_target_island_ratio')} | "
            f"`{item.get('review_hint')}` | {clean_cell(item.get('left_preview'), 70)} | "
            f"{clean_cell(item.get('right_preview'), 70)} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an RPG natural-candidate review packet.")
    parser.add_argument("--natural", default=str(DEFAULT_NATURAL))
    parser.add_argument("--per-class", type=int, default=8)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = build_packet(load_natural(Path(args.natural)), per_class=max(1, int(args.per_class)))
    write_report(packet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": packet["schema"],
                "packet_item_count": packet["packet_item_count"],
                "class_counts": packet["class_counts"],
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
