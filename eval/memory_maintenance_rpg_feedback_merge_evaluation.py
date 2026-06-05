from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NATURAL_PACKET = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"
DEFAULT_OPERATOR_FEEDBACK = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_rpg_feedback_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_feedback_merge_evaluation_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_feedback_merge_evaluation_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_packet(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"RPG review packet must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rpg_natural_candidate_review_packet/v1":
        raise ValueError(f"Unsupported RPG review packet schema: {value.get('schema')}")
    return value


def prefixed_item(item: dict[str, Any], *, source: str, index: int) -> dict[str, Any]:
    row = dict(item)
    original_id = str(item.get("id") or f"{source}:{index}")
    row["id"] = f"{source}:{original_id}"
    row["source_review_packet"] = source
    row["source_review_item_id"] = original_id
    row["report_only"] = True
    row["mutates_db"] = False
    return row


def merge_packets(natural: dict[str, Any], operator: dict[str, Any]) -> dict[str, Any]:
    natural_items = [
        prefixed_item(item, source="natural", index=index)
        for index, item in enumerate(natural.get("items") or [], start=1)
        if isinstance(item, dict)
    ]
    operator_items = [
        prefixed_item(item, source="operator_feedback", index=index)
        for index, item in enumerate(operator.get("items") or [], start=1)
        if isinstance(item, dict)
    ]
    allowed = sorted(set((natural.get("allowed_labels") or []) + (operator.get("allowed_labels") or [])))
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "Merged natural and operator-derived RPG review labels for report-only evaluation.",
        "source_schema": "memory_maintenance_rpg_feedback_merge_evaluation_input/v1",
        "source_pair_count": len(natural_items) + len(operator_items),
        "packet_item_count": len(natural_items) + len(operator_items),
        "source_item_counts": {
            "natural": len(natural_items),
            "operator_feedback": len(operator_items),
        },
        "allowed_labels": allowed,
        "review_instructions": [
            "Merged packet for evaluation only.",
            "Do not use merged feedback for policy until label quality and real outcome validation pass.",
        ],
        "items": [*natural_items, *operator_items],
        "next_action": "evaluate_combined_rpg_label_bank_quality_and_scorer",
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["label_quality_recheck_required", "real_outcome_validation_required"],
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def metric_delta(combined: dict[str, Any], natural: dict[str, Any], key: str) -> float:
    return round(float(combined.get(key) or 0.0) - float(natural.get(key) or 0.0), 6)


def build_variant(packet: dict[str, Any], *, min_labels: int) -> dict[str, Any]:
    from eval.memory_maintenance_rpg_label_quality_report import build_quality_report
    from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report
    from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank

    bank = build_label_bank(packet, min_labels=min_labels)
    quality = build_quality_report(packet, bank)
    scorer = build_scorer_report(bank)
    return {
        "schema": "memory_maintenance_rpg_feedback_merge_variant/v1",
        "packet_item_count": packet.get("packet_item_count"),
        "source_item_counts": packet.get("source_item_counts") or {},
        "label_bank": bank,
        "quality": quality,
        "scorer": scorer,
        "summary": {
            "labeled_count": bank.get("labeled_count"),
            "label_counts": bank.get("label_counts") or {},
            "candidate_class_counts": quality.get("candidate_class_counts") or {},
            "quality_ready_for_shadow": quality.get("ready_for_shadow_scorer_training"),
            "quality_blockers": quality.get("promotion_blockers") or [],
            "scorer_ready_for_shadow": scorer.get("ready_for_shadow_scorer"),
            "scorer_ready_for_policy": scorer.get("ready_for_policy_use"),
            "scorer_blockers": scorer.get("promotion_blockers") or [],
            "family_prediction_accuracy": quality.get("family_prediction_accuracy"),
            "scorer_leave_one_out_accuracy": (scorer.get("leave_one_out") or {}).get("accuracy"),
        },
        "report_only": True,
        "mutates_db": False,
    }


def build_evaluation(natural: dict[str, Any], operator: dict[str, Any], *, min_labels: int = 6) -> dict[str, Any]:
    natural_variant = build_variant(natural, min_labels=min_labels)
    operator_variant = build_variant(operator, min_labels=max(1, min_labels // 2))
    merged_packet = merge_packets(natural, operator)
    combined_variant = build_variant(merged_packet, min_labels=min_labels)
    natural_summary = natural_variant["summary"]
    combined_summary = combined_variant["summary"]
    label_gain = int(combined_summary.get("labeled_count") or 0) - int(natural_summary.get("labeled_count") or 0)
    new_labels = sorted(
        set((combined_summary.get("label_counts") or {})) - set((natural_summary.get("label_counts") or {}))
    )
    new_classes = sorted(
        set((combined_summary.get("candidate_class_counts") or {}))
        - set((natural_summary.get("candidate_class_counts") or {}))
    )
    quality_improved = (
        label_gain > 0
        or bool(new_labels)
        or bool(new_classes)
        or bool(combined_summary.get("quality_ready_for_shadow"))
        and not bool(natural_summary.get("quality_ready_for_shadow"))
    )
    return {
        "schema": "memory_maintenance_rpg_feedback_merge_evaluation/v1",
        "description": "Report-only evaluation comparing natural RPG labels, operator-derived feedback, and the merged label bank.",
        "natural": natural_variant,
        "operator_feedback": operator_variant,
        "combined": combined_variant,
        "comparison": {
            "label_gain_from_operator_feedback": label_gain,
            "new_label_classes_from_operator_feedback": new_labels,
            "new_candidate_classes_from_operator_feedback": new_classes,
            "family_prediction_accuracy_delta": metric_delta(
                combined_summary, natural_summary, "family_prediction_accuracy"
            ),
            "scorer_leave_one_out_accuracy_delta": metric_delta(
                combined_summary, natural_summary, "scorer_leave_one_out_accuracy"
            ),
            "operator_feedback_materially_improves_training_evidence": quality_improved,
        },
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            "real_labeled_packet_validation_required",
            "real_maintenance_outcome_validation_required",
            "database_mutation_not_allowed",
        ],
        "next_action": "collect_more_operator_feedback_or_validate_combined_shadow_scorer"
        if quality_improved
        else "collect_more_diverse_operator_feedback",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    comparison = report.get("comparison") or {}
    lines = [
        "# Memory Maintenance RPG Feedback Merge Evaluation",
        "",
        "Report-only comparison of natural RPG labels, operator feedback labels, and the combined label bank.",
        "",
        f"Label gain: `{comparison.get('label_gain_from_operator_feedback')}`",
        f"Material improvement: `{comparison.get('operator_feedback_materially_improves_training_evidence')}`",
        f"Ready for policy use: `{report['ready_for_policy_use']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Variant Summary",
        "",
        "| variant | labeled | quality shadow ready | scorer shadow ready | family accuracy | scorer LOO |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    for key in ("natural", "operator_feedback", "combined"):
        summary = (report.get(key) or {}).get("summary") or {}
        lines.append(
            f"| `{key}` | {summary.get('labeled_count')} | `{summary.get('quality_ready_for_shadow')}` | "
            f"`{summary.get('scorer_ready_for_shadow')}` | {summary.get('family_prediction_accuracy')} | "
            f"{summary.get('scorer_leave_one_out_accuracy')} |"
        )
    lines.extend(
        [
            "",
            "## Comparison",
            "",
            "```json",
            json.dumps(comparison, indent=2),
            "```",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate natural RPG labels plus operator-derived feedback labels.")
    parser.add_argument("--natural-packet", default=str(DEFAULT_NATURAL_PACKET))
    parser.add_argument("--operator-feedback", default=str(DEFAULT_OPERATOR_FEEDBACK))
    parser.add_argument("--min-labels", type=int, default=6)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_evaluation(
        load_packet(Path(args.natural_packet)),
        load_packet(Path(args.operator_feedback)),
        min_labels=max(1, int(args.min_labels)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "label_gain": report["comparison"]["label_gain_from_operator_feedback"],
                "material_improvement": report["comparison"][
                    "operator_feedback_materially_improves_training_evidence"
                ],
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
