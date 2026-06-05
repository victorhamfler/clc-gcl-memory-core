from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_label_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_scorer_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_scorer_report.md"

LABELS = (
    "safe_duplicate",
    "stale_or_update_conflict",
    "bridge_contamination",
    "semantic_near_duplicate",
    "harmless_related_memory",
    "uncertain_needs_more_context",
)
CANDIDATE_CLASSES = (
    "exact_duplicate",
    "near_duplicate_like",
    "stale_or_update_like",
    "bridge_like",
    "cross_domain_related",
    "unknown",
)


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_bank(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Label bank must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_natural_label_bank/v1":
        raise ValueError(f"Unsupported label bank schema: {value.get('schema')}")
    return value


def examples_from_bank(bank: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, group in (bank.get("label_groups") or {}).items():
        if not isinstance(group, dict):
            continue
        for item in group.get("examples") or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or f"{label}:{len(rows)}")
            if item_id in seen:
                continue
            seen.add(item_id)
            if item.get("review_label") in LABELS:
                rows.append(item)
    return rows


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def one_hot(value: str, choices: tuple[str, ...]) -> list[float]:
    return [1.0 if value == choice else 0.0 for choice in choices]


def vector_for(item: dict[str, Any]) -> list[float]:
    klass = str(item.get("candidate_class") or "unknown")
    if klass not in CANDIDATE_CLASSES:
        klass = "unknown"
    return [
        float_value(item.get("rpg_target_relation")),
        float_value(item.get("rpg_target_island_ratio")),
        float_value(item.get("cosine")),
        float_value(item.get("jaccard")),
        1.0 if item.get("same_domain") else 0.0,
        *one_hot(klass, CANDIDATE_CLASSES),
    ]


def mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dims = len(vectors[0])
    return [sum(row[idx] for row in vectors) / len(vectors) for idx in range(dims)]


def squared_distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def train_centroids(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = {label: [] for label in LABELS}
    for row in rows:
        label = str(row.get("review_label") or "")
        if label in grouped:
            grouped[label].append(vector_for(row))
    centroids = {
        label: mean_vector(vectors)
        for label, vectors in grouped.items()
        if vectors
    }
    return {
        "schema": "memory_maintenance_rpg_label_scorer_centroids/v1",
        "labels": list(centroids),
        "candidate_classes": list(CANDIDATE_CLASSES),
        "feature_names": [
            "rpg_target_relation",
            "rpg_target_island_ratio",
            "cosine",
            "jaccard",
            "same_domain",
            *[f"class:{klass}" for klass in CANDIDATE_CLASSES],
        ],
        "centroids": {label: [round(value, 6) for value in vector] for label, vector in centroids.items()},
        "label_counts": dict(Counter(str(row.get("review_label") or "") for row in rows)),
    }


def predict(model: dict[str, Any], item: dict[str, Any]) -> tuple[str, float]:
    vector = vector_for(item)
    centroids = model.get("centroids") or {}
    if not centroids:
        return "uncertain_needs_more_context", 0.0
    distances = {
        label: squared_distance(vector, [float_value(value) for value in centroid])
        for label, centroid in centroids.items()
    }
    best = min(distances, key=distances.get)
    sorted_distances = sorted(distances.values())
    margin = 0.0
    if len(sorted_distances) >= 2:
        margin = sorted_distances[1] - sorted_distances[0]
    confidence = 1.0 / (1.0 + math.exp(-margin))
    return best, round(confidence, 6)


def leave_one_out(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = []
    for index, row in enumerate(rows):
        train_rows = [item for idx, item in enumerate(rows) if idx != index]
        if len({item.get("review_label") for item in train_rows}) < 2:
            continue
        model = train_centroids(train_rows)
        predicted, confidence = predict(model, row)
        evaluated.append(
            {
                "id": row.get("id"),
                "candidate_class": row.get("candidate_class"),
                "expected_label": row.get("review_label"),
                "predicted_label": predicted,
                "confidence": confidence,
                "correct": predicted == row.get("review_label"),
            }
        )
    correct = sum(1 for item in evaluated if item["correct"])
    return {
        "schema": "memory_maintenance_rpg_label_scorer_leave_one_out/v1",
        "evaluated_count": len(evaluated),
        "accuracy": round(correct / max(len(evaluated), 1), 6),
        "rows": evaluated,
        "report_only": True,
    }


def build_report(bank: dict[str, Any]) -> dict[str, Any]:
    rows = examples_from_bank(bank)
    labels = Counter(str(row.get("review_label") or "") for row in rows)
    model = train_centroids(rows)
    loo = leave_one_out(rows)
    blockers = []
    if len(rows) < 6:
        blockers.append("too_few_labeled_examples")
    if len(labels) < 3:
        blockers.append("too_few_label_classes")
    if float(loo.get("accuracy") or 0.0) < 0.5:
        blockers.append("leave_one_out_accuracy_below_shadow_threshold")
    return {
        "schema": "memory_maintenance_rpg_label_scorer/v1",
        "description": "Report-only transparent RPG natural-candidate label scorer.",
        "source_label_bank_schema": bank.get("schema"),
        "labeled_count": len(rows),
        "label_counts": dict(sorted(labels.items())),
        "model": model,
        "leave_one_out": loo,
        "ready_for_shadow_scorer": not blockers,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            *blockers,
            "real_labeled_packet_validation_required",
            "real_maintenance_outcome_validation_required",
        ],
        "next_action": "validate_scorer_on_real_labeled_rpg_packets"
        if not blockers
        else "collect_more_rpg_review_labels",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    loo = report.get("leave_one_out") or {}
    lines = [
        "# Memory Maintenance RPG Label Scorer",
        "",
        "Report-only scorer for labeled natural RPG maintenance candidates.",
        "",
        f"Labeled examples: `{report['labeled_count']}`",
        f"Ready for shadow scorer: `{report['ready_for_shadow_scorer']}`",
        f"Ready for policy use: `{report['ready_for_policy_use']}`",
        f"Leave-one-out accuracy: `{loo.get('accuracy')}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(report.get("label_counts"), indent=2),
        "```",
        "",
        "## Promotion Blockers",
        "",
    ]
    for blocker in report.get("promotion_blockers") or []:
        lines.append(f"- `{clean_cell(blocker, 120)}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train/evaluate a report-only RPG natural candidate label scorer.")
    parser.add_argument("--label-bank", default=str(DEFAULT_BANK))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(load_bank(Path(args.label_bank)))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "labeled_count": report["labeled_count"],
                "ready_for_shadow_scorer": report["ready_for_shadow_scorer"],
                "ready_for_policy_use": report["ready_for_policy_use"],
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
