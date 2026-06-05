from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_capture_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_rpg_feedback_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_rpg_feedback_report.md"

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


def load_capture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Operator outcome capture must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_operator_outcome_capture/v1":
        raise ValueError(f"Unsupported operator outcome capture schema: {value.get('schema')}")
    return value


def candidate_class_for(item: dict[str, Any]) -> str:
    operation = str(item.get("operation_kind") or "")
    status = str(item.get("status") or "")
    label = str(item.get("rpg_training_label") or "")
    if operation == "duplicate_deprecation" and label == "safe_duplicate":
        return "near_duplicate_like"
    if label == "stale_or_update_conflict":
        return "stale_or_update_like"
    if label == "bridge_contamination":
        return "bridge_like"
    if status == "blocked_before_operator_review":
        return "bridge_like" if label == "uncertain_needs_more_context" else "unknown"
    return "unknown"


def preview_pair(item: dict[str, Any]) -> tuple[str, str, str, str]:
    ids = [str(value) for value in item.get("target_ids") or [] if str(value)]
    left_id = ids[0] if ids else str(item.get("packet_item_id") or "")
    right_id = ids[1] if len(ids) > 1 else left_id
    return left_id, right_id, left_id, right_id


def feedback_item(item: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    label = str(item.get("rpg_training_label") or "").strip()
    if label not in LABEL_OPTIONS:
        return None
    left_id, right_id, left_preview, right_preview = preview_pair(item)
    rpg_summary = item.get("rpg_summary") if isinstance(item.get("rpg_summary"), dict) else {}
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"operator_rpg_feedback:{index:04d}:{item.get('packet_item_id')}",
        "candidate_class": candidate_class_for(item),
        "source_db": "operator_outcome_capture",
        "left_memory_id": left_id,
        "right_memory_id": right_id,
        "left_domain": "operator_packet",
        "right_domain": "operator_packet",
        "same_domain": True,
        "cosine": None,
        "jaccard": None,
        "rpg_target_relation": rpg_summary.get("target_mean_relation_mean"),
        "rpg_target_island_ratio": rpg_summary.get("target_island_ratio_mean"),
        "left_preview": left_preview,
        "right_preview": right_preview,
        "review_hint": "operator_outcome_feedback_label",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": label,
        "reviewer": item.get("reviewer") or "operator_outcome_capture",
        "review_notes": item.get("rpg_training_note") or item.get("reason") or "",
        "source_packet_item_id": item.get("packet_item_id"),
        "source_operator_outcome": item.get("outcome"),
        "source_operator_status": item.get("status"),
        "source_label": item.get("rpg_training_label_source"),
        "rpg_summary": rpg_summary,
        "rpg_learning_context": item.get("rpg_learning_context") or {},
        "mutation_allowed": False,
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_feedback_packet(capture: dict[str, Any]) -> dict[str, Any]:
    valid_capture = capture.get("readiness") == "capture_valid_for_rpg_label_feedback"
    source_items = [
        item
        for item in capture.get("outcomes") or []
        if isinstance(item, dict)
        and item.get("known_packet_item") is True
        and item.get("valid_outcome") is True
        and item.get("valid_rpg_training_label") is True
    ]
    items = []
    for source_item in source_items:
        row = feedback_item(source_item, index=len(items) + 1)
        if row is not None:
            items.append(row)
    class_counts = Counter(str(item.get("candidate_class") or "unknown") for item in items)
    label_counts = Counter(str(item.get("review_label") or "") for item in items)
    blockers = []
    if not valid_capture:
        blockers.append("operator_outcome_capture_not_valid_for_feedback")
    if not items:
        blockers.append("no_valid_rpg_feedback_items")
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "RPG label-bank-compatible review packet derived from operator outcome capture.",
        "source_schema": capture.get("schema"),
        "source_capture_readiness": capture.get("readiness"),
        "source_pair_count": capture.get("outcome_count"),
        "packet_item_count": len(items),
        "class_counts": dict(sorted(class_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "allowed_labels": LABEL_OPTIONS,
        "review_instructions": [
            "These labels were derived from operator packet outcomes.",
            "Use them as report-only RPG feedback until label quality and copied-real outcome validation pass.",
            "Do not apply memory mutations from this packet.",
        ],
        "items": items,
        "next_action": "merge_operator_feedback_with_rpg_label_bank"
        if not blockers
        else "review_operator_feedback_capture_before_label_bank_merge",
        "ready_for_label_bank": not blockers,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            *blockers,
            "label_quality_recheck_required",
            "real_maintenance_outcome_validation_required",
            "database_mutation_not_allowed",
        ],
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
        "# Memory Maintenance Operator Outcome RPG Feedback",
        "",
        "RPG label-bank-compatible packet derived from operator outcome capture.",
        "",
        f"Items: `{packet['packet_item_count']}`",
        f"Ready for label bank: `{packet['ready_for_label_bank']}`",
        f"Ready for policy use: `{packet['ready_for_policy_use']}`",
        f"Next action: `{packet['next_action']}`",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(packet.get("label_counts"), indent=2),
        "```",
        "",
        "## Items",
        "",
        "| item | class | label | outcome | source |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not packet.get("items"):
        lines.append("| none | none | none | none | none |")
    for item in packet.get("items") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 80)}` | `{clean_cell(item.get('candidate_class'), 50)}` | "
            f"`{clean_cell(item.get('review_label'), 50)}` | `{clean_cell(item.get('source_operator_outcome'), 50)}` | "
            f"`{clean_cell(item.get('source_label'), 50)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert operator outcome capture into RPG label-bank feedback packet.")
    parser.add_argument("--capture", default=str(DEFAULT_CAPTURE))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = build_feedback_packet(load_capture(Path(args.capture)))
    write_report(packet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": packet["schema"],
                "packet_item_count": packet["packet_item_count"],
                "ready_for_label_bank": packet["ready_for_label_bank"],
                "ready_for_policy_use": packet["ready_for_policy_use"],
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
