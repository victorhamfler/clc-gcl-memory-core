from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_report.md"

MIN_LABELS = 12
MIN_LABEL_CLASSES = 4
MIN_CANDIDATE_CLASSES = 4
MAX_DOMINANT_LABEL_RATIO = 0.55


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_packet(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Review packet must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_natural_candidate_review_packet/v1":
        raise ValueError(f"Unsupported review packet schema: {value.get('schema')}")
    return value


def count_rows(items: list[dict[str, Any]], key: str) -> Counter[str]:
    return Counter(str(item.get(key) or "unknown") for item in items)


def dominant_ratio(counter: Counter[str]) -> float:
    total = sum(counter.values())
    return max(counter.values()) / total if total and counter else 0.0


def sorted_unlabeled(unlabeled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        unlabeled,
        key=lambda item: (
            str(item.get("candidate_class") or "unknown"),
            -float(item.get("rpg_target_relation") or 0.0),
            -float(item.get("rpg_target_island_ratio") or 0.0),
            str(item.get("id") or ""),
        ),
    )


def choose_review_targets(
    unlabeled: list[dict[str, Any]],
    labeled_class_counts: Counter[str],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in sorted_unlabeled(unlabeled):
        by_class[str(item.get("candidate_class") or "unknown")].append(item)
    selected: list[dict[str, Any]] = []
    class_order = sorted(
        by_class,
        key=lambda klass: (labeled_class_counts.get(klass, 0), klass),
    )
    while len(selected) < max_items and any(by_class.values()):
        progressed = False
        for klass in class_order:
            if len(selected) >= max_items:
                break
            rows = by_class.get(klass) or []
            if not rows:
                continue
            selected.append(rows.pop(0))
            progressed = True
        if not progressed:
            break
    return selected


def build_plan(packet: dict[str, Any], *, target_labels: int = MIN_LABELS, max_review_items: int = 12) -> dict[str, Any]:
    items = [item for item in packet.get("items") or [] if isinstance(item, dict)]
    labeled = [item for item in items if str(item.get("review_label") or "").strip()]
    unlabeled = [item for item in items if item not in labeled]
    label_counts = count_rows(labeled, "review_label")
    class_counts = count_rows(labeled, "candidate_class")
    available_class_counts = count_rows(items, "candidate_class")
    label_deficit = max(0, int(target_labels) - len(labeled))
    label_class_deficit = max(0, MIN_LABEL_CLASSES - len(label_counts))
    candidate_class_deficit = max(0, MIN_CANDIDATE_CLASSES - len(class_counts))
    dominant = dominant_ratio(label_counts)
    dominant_label = label_counts.most_common(1)[0][0] if label_counts else None
    review_budget = max(label_deficit, int(max_review_items))
    targets = choose_review_targets(unlabeled, class_counts, max_items=min(review_budget, len(unlabeled)))
    target_summaries = [
        {
            "id": item.get("id"),
            "candidate_class": item.get("candidate_class"),
            "review_hint": item.get("review_hint"),
            "rpg_target_relation": item.get("rpg_target_relation"),
            "rpg_target_island_ratio": item.get("rpg_target_island_ratio"),
            "left_preview": item.get("left_preview"),
            "right_preview": item.get("right_preview"),
        }
        for item in targets
    ]
    checks = {
        "enough_labeled_examples": len(labeled) >= int(target_labels),
        "enough_label_classes": len(label_counts) >= MIN_LABEL_CLASSES,
        "enough_candidate_classes": len(class_counts) >= MIN_CANDIDATE_CLASSES,
        "dominant_label_not_overweighted": not label_counts or dominant <= MAX_DOMINANT_LABEL_RATIO,
        "unlabeled_targets_available": bool(targets) or label_deficit == 0,
        "packet_report_only": packet.get("report_only") is True
        and packet.get("mutates_db") is False
        and packet.get("mutates_runtime") is False
        and packet.get("mutates_config") is False,
    }
    blockers = [key for key, value in checks.items() if not value]
    return {
        "schema": "memory_maintenance_rpg_label_collection_plan/v1",
        "description": "Report-only plan for collecting enough reviewed RPG labels to satisfy label-quality gates.",
        "source_packet_schema": packet.get("schema"),
        "packet_item_count": len(items),
        "labeled_count": len(labeled),
        "unlabeled_count": len(unlabeled),
        "target_labeled_count": int(target_labels),
        "label_counts": dict(sorted(label_counts.items())),
        "candidate_class_counts": dict(sorted(class_counts.items())),
        "available_candidate_class_counts": dict(sorted(available_class_counts.items())),
        "dominant_label": dominant_label,
        "dominant_label_ratio": round(dominant, 6),
        "deficits": {
            "labeled_examples": label_deficit,
            "label_classes": label_class_deficit,
            "candidate_classes": candidate_class_deficit,
            "dominant_label_ratio_limit": MAX_DOMINANT_LABEL_RATIO,
        },
        "recommended_review_targets": target_summaries,
        "recommended_review_target_count": len(target_summaries),
        "checks": checks,
        "ready_for_label_quality_eval": not blockers,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            *blockers,
            "real_labeled_packet_validation_required",
            "real_maintenance_outcome_validation_required",
        ],
        "next_action": "run_label_quality_and_scorer"
        if not blockers
        else "collect_recommended_review_targets",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(plan: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Collection Plan",
        "",
        "Report-only plan for collecting enough reviewed RPG labels to satisfy label-quality gates.",
        "",
        f"Labeled: `{plan['labeled_count']}`",
        f"Unlabeled: `{plan['unlabeled_count']}`",
        f"Ready for label quality eval: `{plan['ready_for_label_quality_eval']}`",
        f"Next action: `{plan['next_action']}`",
        "",
        "## Deficits",
        "",
        "```json",
        json.dumps(plan.get("deficits"), indent=2),
        "```",
        "",
        "## Recommended Review Targets",
        "",
        "| id | class | relation | island | hint |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in plan.get("recommended_review_targets") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 80)}` | `{clean_cell(item.get('candidate_class'), 50)}` | "
            f"{item.get('rpg_target_relation')} | {item.get('rpg_target_island_ratio')} | "
            f"`{clean_cell(item.get('review_hint'), 80)}` |"
        )
    lines.extend(["", "## Promotion Blockers", ""])
    for blocker in plan.get("promotion_blockers") or []:
        lines.append(f"- `{clean_cell(blocker, 120)}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan RPG natural-candidate label collection.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--target-labels", type=int, default=MIN_LABELS)
    parser.add_argument("--max-review-items", type=int, default=12)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    plan = build_plan(
        load_packet(Path(args.packet)),
        target_labels=max(1, int(args.target_labels)),
        max_review_items=max(1, int(args.max_review_items)),
    )
    write_report(plan, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": plan["schema"],
                "labeled_count": plan["labeled_count"],
                "recommended_review_target_count": plan["recommended_review_target_count"],
                "ready_for_label_quality_eval": plan["ready_for_label_quality_eval"],
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
