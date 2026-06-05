from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"
DEFAULT_BANK = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_label_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_quality_report_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_quality_report.md"

MIN_LABELS = 12
MIN_LABEL_CLASSES = 4
MIN_CANDIDATE_CLASSES = 4
MAX_DOMINANT_LABEL_RATIO = 0.55
MIN_FAMILY_ACCURACY = 0.60


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_json_object(path: Path, *, expected_schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")
    if value.get("schema") != expected_schema:
        raise ValueError(f"Unsupported schema at {path}: {value.get('schema')}")
    return value


def labeled_items_from_packet(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in packet.get("items") or []
        if isinstance(item, dict) and str(item.get("review_label") or "").strip()
    ]


def class_label_matrix(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        grouped[str(item.get("candidate_class") or "unknown")][str(item.get("review_label") or "unlabeled")] += 1
    return {klass: dict(sorted(labels.items())) for klass, labels in sorted(grouped.items())}


def contradiction_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    previews: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        left = str(item.get("left_memory_id") or "")
        right = str(item.get("right_memory_id") or "")
        pair_key = tuple(sorted((left, right)))
        label = str(item.get("review_label") or "")
        if left and right and label:
            by_pair[pair_key].add(label)
            previews.setdefault(
                pair_key,
                {
                    "left_memory_id": item.get("left_memory_id"),
                    "right_memory_id": item.get("right_memory_id"),
                    "left_preview": item.get("left_preview"),
                    "right_preview": item.get("right_preview"),
                },
            )
    contradictions = []
    for pair_key, labels in sorted(by_pair.items()):
        if len(labels) > 1:
            contradictions.append(
                {
                    "pair": list(pair_key),
                    "labels": sorted(labels),
                    **previews.get(pair_key, {}),
                }
            )
    return contradictions


def build_quality_report(packet: dict[str, Any], bank: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in packet.get("items") or [] if isinstance(item, dict)]
    labeled = labeled_items_from_packet(packet)
    label_counts = Counter(str(item.get("review_label") or "") for item in labeled)
    class_counts = Counter(str(item.get("candidate_class") or "unknown") for item in labeled)
    dominant_ratio = max(label_counts.values()) / len(labeled) if labeled and label_counts else 0.0
    invalid_labels = list(bank.get("invalid_label_ids") or [])
    prediction_probe = bank.get("prediction_probe") or {}
    family_accuracy = float(prediction_probe.get("family_accuracy") or 0.0)
    contradictions = contradiction_candidates(labeled)

    checks = {
        "enough_labeled_examples": len(labeled) >= MIN_LABELS,
        "enough_label_classes": len(label_counts) >= MIN_LABEL_CLASSES,
        "enough_candidate_classes": len(class_counts) >= MIN_CANDIDATE_CLASSES,
        "dominant_label_not_overweighted": dominant_ratio <= MAX_DOMINANT_LABEL_RATIO,
        "no_invalid_labels": not invalid_labels,
        "no_pair_label_contradictions": not contradictions,
        "prediction_probe_family_accuracy_floor": family_accuracy >= MIN_FAMILY_ACCURACY,
        "packet_report_only": packet.get("report_only") is True
        and packet.get("mutates_db") is False
        and packet.get("mutates_runtime") is False
        and packet.get("mutates_config") is False,
        "bank_report_only": bank.get("report_only") is True
        and bank.get("mutates_db") is False
        and bank.get("mutates_runtime") is False
        and bank.get("mutates_config") is False,
    }
    blockers = [key for key, passed in checks.items() if not passed]
    return {
        "schema": "memory_maintenance_rpg_label_quality_report/v1",
        "description": "Report-only quality and coverage audit for RPG natural-candidate review labels.",
        "source_packet_schema": packet.get("schema"),
        "source_label_bank_schema": bank.get("schema"),
        "packet_item_count": len(items),
        "labeled_count": len(labeled),
        "unlabeled_count": len(items) - len(labeled),
        "label_counts": dict(sorted(label_counts.items())),
        "candidate_class_counts": dict(sorted(class_counts.items())),
        "class_label_matrix": class_label_matrix(labeled),
        "dominant_label_ratio": round(dominant_ratio, 6),
        "family_prediction_accuracy": round(family_accuracy, 6),
        "invalid_label_ids": invalid_labels,
        "contradiction_candidates": contradictions,
        "checks": checks,
        "ready_for_shadow_scorer_training": not blockers,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            *blockers,
            "real_labeled_packet_validation_required",
            "real_maintenance_outcome_validation_required",
        ],
        "next_action": "collect_more_diverse_rpg_review_labels"
        if blockers
        else "train_report_only_rpg_label_scorer_on_real_labels",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Quality Report",
        "",
        "Report-only quality and coverage audit for RPG natural-candidate review labels.",
        "",
        f"Labeled examples: `{report['labeled_count']}`",
        f"Unlabeled examples: `{report['unlabeled_count']}`",
        f"Ready for shadow scorer training: `{report['ready_for_shadow_scorer_training']}`",
        f"Ready for policy use: `{report['ready_for_policy_use']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Label Counts",
            "",
            "```json",
            json.dumps(report.get("label_counts"), indent=2),
            "```",
            "",
            "## Class Label Matrix",
            "",
            "```json",
            json.dumps(report.get("class_label_matrix"), indent=2),
            "```",
            "",
            "## Promotion Blockers",
            "",
        ]
    )
    for blocker in report.get("promotion_blockers") or []:
        lines.append(f"- `{clean_cell(blocker, 120)}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RPG natural-candidate review label quality.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--label-bank", default=str(DEFAULT_BANK))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = load_json_object(
        Path(args.packet), expected_schema="memory_maintenance_rpg_natural_candidate_review_packet/v1"
    )
    bank = load_json_object(Path(args.label_bank), expected_schema="memory_maintenance_rpg_natural_label_bank/v1")
    report = build_quality_report(packet, bank)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "labeled_count": report["labeled_count"],
                "ready_for_shadow_scorer_training": report["ready_for_shadow_scorer_training"],
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
