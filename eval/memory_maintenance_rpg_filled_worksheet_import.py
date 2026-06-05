from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSHEET = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_review_worksheet_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_filled_worksheet_import_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_filled_worksheet_import_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_worksheet(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Worksheet must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_label_review_worksheet/v1":
        raise ValueError(f"Unsupported worksheet schema: {value.get('schema')}")
    return value


def packet_item(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"worksheet_import:{index:03d}:{item.get('source_review_item_id')}",
        "source_worksheet_id": item.get("worksheet_id"),
        "source_review_item_id": item.get("source_review_item_id"),
        "candidate_class": item.get("candidate_class") or "unknown",
        "source_db": item.get("source_db") or "worksheet_import",
        "left_memory_id": item.get("left_memory_id") or f"{item.get('source_review_item_id')}:left",
        "right_memory_id": item.get("right_memory_id") or f"{item.get('source_review_item_id')}:right",
        "left_domain": item.get("left_domain"),
        "right_domain": item.get("right_domain"),
        "same_domain": item.get("same_domain"),
        "cosine": item.get("cosine"),
        "jaccard": item.get("jaccard"),
        "rpg_target_relation": item.get("rpg_target_relation"),
        "rpg_target_island_ratio": item.get("rpg_target_island_ratio"),
        "left_preview": item.get("left_preview"),
        "right_preview": item.get("right_preview"),
        "review_hint": item.get("review_hint"),
        "allowed_labels": item.get("allowed_labels") or [],
        "review_label": str(item.get("review_label") or "").strip(),
        "reviewer": str(item.get("reviewer") or "").strip(),
        "review_notes": str(item.get("review_notes") or "").strip(),
        "mutation_allowed": False,
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_packet(worksheet: dict[str, Any], *, min_labels: int = 12) -> dict[str, Any]:
    allowed_labels = list(worksheet.get("allowed_labels") or [])
    items = [item for item in worksheet.get("items") or [] if isinstance(item, dict)]
    labeled_source_items = [item for item in items if str(item.get("review_label") or "").strip()]
    imported_items = [packet_item(item, index=index) for index, item in enumerate(labeled_source_items, start=1)]
    invalid_ids = [
        item.get("source_worksheet_id")
        for item in imported_items
        if item.get("review_label") not in allowed_labels
    ]
    missing_reviewer_ids = [
        item.get("source_worksheet_id")
        for item in imported_items
        if not item.get("reviewer")
    ]
    label_counts = Counter(str(item.get("review_label") or "") for item in imported_items)
    class_counts = Counter(str(item.get("candidate_class") or "unknown") for item in imported_items)
    checks = {
        "has_labeled_rows": bool(imported_items),
        "enough_labeled_rows": len(imported_items) >= int(min_labels),
        "all_labels_allowed": not invalid_ids,
        "reviewer_present_for_labeled_rows": not missing_reviewer_ids,
        "source_worksheet_report_only": worksheet.get("report_only") is True
        and worksheet.get("mutates_db") is False
        and worksheet.get("mutates_runtime") is False
        and worksheet.get("mutates_config") is False,
    }
    blockers = [key for key, value in checks.items() if not value]
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "Report-only review packet imported from filled RPG label review worksheet rows.",
        "source_schema": "memory_maintenance_rpg_filled_worksheet_import/v1",
        "source_worksheet_schema": worksheet.get("schema"),
        "source_worksheet_item_count": len(items),
        "source_pair_count": len(imported_items),
        "packet_item_count": len(imported_items),
        "class_counts": dict(sorted(class_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "allowed_labels": allowed_labels,
        "invalid_label_source_ids": invalid_ids,
        "missing_reviewer_source_ids": missing_reviewer_ids,
        "checks": checks,
        "items": imported_items,
        "next_action": "run_label_bank_quality_and_scorer"
        if not blockers
        else "complete_more_worksheet_labels",
        "ready_for_label_quality_eval": not invalid_ids and len(imported_items) > 0,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            *blockers,
            "real_maintenance_outcome_validation_required",
            "shadow_scorer_validation_required",
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
        "# Memory Maintenance RPG Filled Worksheet Import",
        "",
        "Report-only review packet imported from filled RPG label review worksheet rows.",
        "",
        f"Imported labeled rows: `{packet['packet_item_count']}`",
        f"Ready for label quality eval: `{packet['ready_for_label_quality_eval']}`",
        f"Ready for policy use: `{packet['ready_for_policy_use']}`",
        f"Next action: `{packet['next_action']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (packet.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Label Counts",
            "",
            "```json",
            json.dumps(packet.get("label_counts"), indent=2),
            "```",
            "",
            "## Imported Items",
            "",
            "| id | class | label | reviewer |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in packet.get("items") or []:
        lines.append(
            f"| `{clean_cell(item.get('source_worksheet_id'), 80)}` | "
            f"`{clean_cell(item.get('candidate_class'), 60)}` | "
            f"`{clean_cell(item.get('review_label'), 60)}` | "
            f"`{clean_cell(item.get('reviewer'), 60)}` |"
        )
    lines.extend(["", "## Promotion Blockers", ""])
    for blocker in packet.get("promotion_blockers") or []:
        lines.append(f"- `{clean_cell(blocker, 120)}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import filled RPG label review worksheet rows.")
    parser.add_argument("--worksheet", default=str(DEFAULT_WORKSHEET))
    parser.add_argument("--min-labels", type=int, default=12)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = build_packet(load_worksheet(Path(args.worksheet)), min_labels=max(1, int(args.min_labels)))
    write_report(packet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": packet["schema"],
                "packet_item_count": packet["packet_item_count"],
                "ready_for_label_quality_eval": packet["ready_for_label_quality_eval"],
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
