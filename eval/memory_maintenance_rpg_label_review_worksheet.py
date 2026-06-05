from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_review_worksheet_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_review_worksheet.md"

ALLOWED_LABELS = [
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


def load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Collection plan must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_label_collection_plan/v1":
        raise ValueError(f"Unsupported collection plan schema: {value.get('schema')}")
    return value


def worksheet_item(target: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet_item/v1",
        "worksheet_id": f"rpg_label_review:{index:03d}",
        "source_review_item_id": target.get("id"),
        "candidate_class": target.get("candidate_class"),
        "review_hint": target.get("review_hint"),
        "rpg_target_relation": target.get("rpg_target_relation"),
        "rpg_target_island_ratio": target.get("rpg_target_island_ratio"),
        "left_preview": target.get("left_preview"),
        "right_preview": target.get("right_preview"),
        "allowed_labels": ALLOWED_LABELS,
        "review_label": "",
        "reviewer": "",
        "review_notes": "",
        "operator_questions": [
            "Do the memories express the same current fact?",
            "Does one memory supersede or correct the other?",
            "Could this pair contaminate retrieval across topics/domains?",
            "Is this relation harmless context with no maintenance action?",
            "Is more provenance or recency evidence needed?",
        ],
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_worksheet(plan: dict[str, Any]) -> dict[str, Any]:
    targets = [item for item in plan.get("recommended_review_targets") or [] if isinstance(item, dict)]
    items = [worksheet_item(target, index=index) for index, target in enumerate(targets, start=1)]
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet/v1",
        "description": "Operator-facing worksheet for reviewing RPG label collection targets.",
        "source_plan_schema": plan.get("schema"),
        "source_plan_ready_for_label_quality_eval": plan.get("ready_for_label_quality_eval"),
        "source_plan_deficits": plan.get("deficits") or {},
        "worksheet_item_count": len(items),
        "allowed_labels": ALLOWED_LABELS,
        "review_instructions": [
            "Fill review_label only with one of the allowed labels.",
            "Use review_notes to explain ambiguous, stale, bridge, or provenance-sensitive cases.",
            "Do not mutate memory rows from this worksheet.",
            "After filling labels, convert the worksheet back into a review packet and run label quality plus scorer checks.",
        ],
        "items": items,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["review_labels_required", "real_maintenance_outcome_validation_required"],
        "next_action": "fill_review_labels_and_run_label_quality",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(worksheet: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(worksheet, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Review Worksheet",
        "",
        "Operator-facing worksheet for reviewing RPG label collection targets.",
        "",
        f"Worksheet items: `{worksheet['worksheet_item_count']}`",
        f"Ready for policy use: `{worksheet['ready_for_policy_use']}`",
        "",
        "## Allowed Labels",
        "",
    ]
    for label in worksheet.get("allowed_labels") or []:
        lines.append(f"- `{label}`")
    lines.extend(
        [
            "",
            "## Review Items",
            "",
            "| worksheet id | source id | class | relation | island | label | notes |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for item in worksheet.get("items") or []:
        lines.append(
            f"| `{clean_cell(item.get('worksheet_id'), 60)}` | `{clean_cell(item.get('source_review_item_id'), 80)}` | "
            f"`{clean_cell(item.get('candidate_class'), 40)}` | {item.get('rpg_target_relation')} | "
            f"{item.get('rpg_target_island_ratio')} |  |  |"
        )
        lines.append(
            f"|  | left |  |  |  |  | {clean_cell(item.get('left_preview'), 180)} |"
        )
        lines.append(
            f"|  | right |  |  |  |  | {clean_cell(item.get('right_preview'), 180)} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an operator-facing RPG label review worksheet.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    worksheet = build_worksheet(load_plan(Path(args.plan)))
    write_report(worksheet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": worksheet["schema"],
                "worksheet_item_count": worksheet["worksheet_item_count"],
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
