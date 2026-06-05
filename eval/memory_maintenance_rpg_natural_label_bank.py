from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_label_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_label_bank_report.md"


MAINTENANCE_ACTION_LABELS = {
    "safe_duplicate",
    "stale_or_update_conflict",
    "bridge_contamination",
    "semantic_near_duplicate",
}


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


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def label_family(label: str) -> str:
    if label == "safe_duplicate":
        return "safe_duplicate"
    if label in {"stale_or_update_conflict", "bridge_contamination", "semantic_near_duplicate"}:
        return "maintenance_risk"
    if label == "harmless_related_memory":
        return "no_action_related"
    return "uncertain"


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    relations = [float(item.get("rpg_target_relation") or 0.0) for item in rows]
    islands = [float(item.get("rpg_target_island_ratio") or 0.0) for item in rows]
    candidate_classes = Counter(str(item.get("candidate_class") or "unknown") for item in rows)
    labels = Counter(str(item.get("review_label") or "unlabeled") for item in rows)
    return {
        "schema": "memory_maintenance_rpg_natural_label_group/v1",
        "count": len(rows),
        "candidate_classes": dict(sorted(candidate_classes.items())),
        "labels": dict(sorted(labels.items())),
        "rpg_relation_mean": round(mean(relations), 6),
        "rpg_relation_min": round(min(relations), 6) if relations else 0.0,
        "rpg_relation_max": round(max(relations), 6) if relations else 0.0,
        "rpg_island_mean": round(mean(islands), 6),
        "rpg_island_min": round(min(islands), 6) if islands else 0.0,
        "rpg_island_max": round(max(islands), 6) if islands else 0.0,
        "examples": rows[:5],
        "report_only": True,
    }


def simple_prediction(item: dict[str, Any], *, relation_safe_threshold: float, island_safe_threshold: float) -> str:
    klass = str(item.get("candidate_class") or "")
    relation = float(item.get("rpg_target_relation") or 0.0)
    island = float(item.get("rpg_target_island_ratio") or 0.0)
    if klass == "near_duplicate_like" and relation >= relation_safe_threshold and island >= island_safe_threshold:
        return "safe_duplicate"
    if klass == "stale_or_update_like":
        return "stale_or_update_conflict"
    if klass == "bridge_like":
        return "bridge_contamination"
    if klass == "cross_domain_related":
        return "harmless_related_memory"
    return "uncertain_needs_more_context"


def build_label_bank(packet: dict[str, Any], *, min_labels: int = 6) -> dict[str, Any]:
    items = [item for item in packet.get("items") or [] if isinstance(item, dict)]
    labeled = [item for item in items if str(item.get("review_label") or "").strip()]
    unlabeled = [item for item in items if item not in labeled]
    invalid = [
        item.get("id")
        for item in labeled
        if item.get("review_label") not in (packet.get("allowed_labels") or [])
    ]
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in labeled:
        label = str(item.get("review_label") or "")
        by_label[label].append(item)
        by_family[label_family(label)].append(item)
    safe_rows = by_label.get("safe_duplicate", [])
    non_safe_rows = [item for item in labeled if item.get("review_label") != "safe_duplicate"]
    safe_relation_mean = mean([float(item.get("rpg_target_relation") or 0.0) for item in safe_rows])
    non_safe_relation_mean = mean([float(item.get("rpg_target_relation") or 0.0) for item in non_safe_rows])
    safe_island_mean = mean([float(item.get("rpg_target_island_ratio") or 0.0) for item in safe_rows])
    non_safe_island_mean = mean([float(item.get("rpg_target_island_ratio") or 0.0) for item in non_safe_rows])
    relation_threshold = (safe_relation_mean + non_safe_relation_mean) / 2.0 if safe_rows and non_safe_rows else 0.0
    island_threshold = (safe_island_mean + non_safe_island_mean) / 2.0 if safe_rows and non_safe_rows else 0.0
    predictions = [
        {
            "id": item.get("id"),
            "candidate_class": item.get("candidate_class"),
            "review_label": item.get("review_label"),
            "predicted_label": simple_prediction(
                item,
                relation_safe_threshold=relation_threshold,
                island_safe_threshold=island_threshold,
            ),
        }
        for item in labeled
    ]
    exact_correct = sum(1 for item in predictions if item["review_label"] == item["predicted_label"])
    family_correct = sum(
        1 for item in predictions if label_family(str(item["review_label"])) == label_family(str(item["predicted_label"]))
    )
    label_counts = Counter(str(item.get("review_label") or "") for item in labeled)
    return {
        "schema": "memory_maintenance_rpg_natural_label_bank/v1",
        "description": "Report-only evidence bank for labeled natural RPG memory-maintenance candidate pairs.",
        "source_packet_schema": packet.get("schema"),
        "source_item_count": len(items),
        "labeled_count": len(labeled),
        "unlabeled_count": len(unlabeled),
        "invalid_label_ids": invalid,
        "label_counts": dict(sorted(label_counts.items())),
        "label_groups": {label: summarize_group(rows) for label, rows in sorted(by_label.items())},
        "family_groups": {family: summarize_group(rows) for family, rows in sorted(by_family.items())},
        "safe_relation_mean": round(safe_relation_mean, 6),
        "non_safe_relation_mean": round(non_safe_relation_mean, 6),
        "safe_island_mean": round(safe_island_mean, 6),
        "non_safe_island_mean": round(non_safe_island_mean, 6),
        "relation_threshold_probe": round(relation_threshold, 6),
        "island_threshold_probe": round(island_threshold, 6),
        "prediction_probe": {
            "schema": "memory_maintenance_rpg_natural_label_prediction_probe/v1",
            "exact_accuracy": round(exact_correct / max(len(predictions), 1), 6),
            "family_accuracy": round(family_correct / max(len(predictions), 1), 6),
            "predictions": predictions,
            "report_only": True,
        },
        "ready_for_scorer_training": len(labeled) >= int(min_labels)
        and not invalid
        and len(label_counts) >= 3,
        "ready_for_policy_use": False,
        "next_action": "collect_more_review_labels"
        if len(labeled) < int(min_labels)
        else "train_report_only_rpg_label_scorer",
        "promotion_ready": False,
        "promotion_blockers": ["report_only_scorer_required", "real_outcome_validation_required"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(bank: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    probe = bank.get("prediction_probe") or {}
    lines = [
        "# Memory Maintenance RPG Natural Label Bank",
        "",
        "Report-only evidence bank for labeled natural RPG maintenance candidate pairs.",
        "",
        f"Labeled: `{bank['labeled_count']}`",
        f"Unlabeled: `{bank['unlabeled_count']}`",
        f"Ready for scorer training: `{bank['ready_for_scorer_training']}`",
        f"Ready for policy use: `{bank['ready_for_policy_use']}`",
        f"Exact prediction probe: `{probe.get('exact_accuracy')}`",
        f"Family prediction probe: `{probe.get('family_accuracy')}`",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(bank.get("label_counts"), indent=2),
        "```",
        "",
        "## Label Groups",
        "",
        "| label | count | relation mean | island mean |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, group in (bank.get("label_groups") or {}).items():
        lines.append(
            f"| `{clean_cell(label, 60)}` | {group.get('count')} | "
            f"{group.get('rpg_relation_mean')} | {group.get('rpg_island_mean')} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize labeled RPG natural-candidate review packets.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--min-labels", type=int, default=6)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    bank = build_label_bank(load_packet(Path(args.packet)), min_labels=max(1, int(args.min_labels)))
    write_report(bank, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": not bool(bank.get("invalid_label_ids")),
                "schema": bank["schema"],
                "labeled_count": bank["labeled_count"],
                "ready_for_scorer_training": bank["ready_for_scorer_training"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if not bank.get("invalid_label_ids") else 1


if __name__ == "__main__":
    raise SystemExit(main())
