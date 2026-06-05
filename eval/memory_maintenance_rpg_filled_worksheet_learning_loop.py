from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


try:
    from eval.memory_maintenance_rpg_filled_worksheet_import import build_packet as import_worksheet
    from eval.memory_maintenance_rpg_label_quality_report import build_quality_report
    from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report
    from eval.memory_maintenance_rpg_label_review_worksheet import ALLOWED_LABELS
    from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank
    from eval.memory_maintenance_rpg_reviewed_label_batch import build_packet as build_reviewed_packet
except ModuleNotFoundError:
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))
    from eval.memory_maintenance_rpg_filled_worksheet_import import build_packet as import_worksheet
    from eval.memory_maintenance_rpg_label_quality_report import build_quality_report
    from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report
    from eval.memory_maintenance_rpg_label_review_worksheet import ALLOWED_LABELS
    from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank
    from eval.memory_maintenance_rpg_reviewed_label_batch import build_packet as build_reviewed_packet


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_filled_worksheet_learning_loop_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_filled_worksheet_learning_loop_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def worksheet_item_from_reviewed(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet_item/v1",
        "worksheet_id": f"filled_fixture:{index:03d}",
        "source_review_item_id": row.get("id"),
        "candidate_class": row.get("candidate_class"),
        "source_db": row.get("source_db"),
        "left_memory_id": row.get("left_memory_id"),
        "right_memory_id": row.get("right_memory_id"),
        "left_domain": row.get("left_domain"),
        "right_domain": row.get("right_domain"),
        "same_domain": row.get("same_domain"),
        "cosine": row.get("cosine"),
        "jaccard": row.get("jaccard"),
        "review_hint": row.get("review_hint"),
        "rpg_target_relation": row.get("rpg_target_relation"),
        "rpg_target_island_ratio": row.get("rpg_target_island_ratio"),
        "left_preview": row.get("left_preview"),
        "right_preview": row.get("right_preview"),
        "allowed_labels": ALLOWED_LABELS,
        "review_label": row.get("review_label"),
        "reviewer": "local_filled_worksheet_fixture",
        "review_notes": "Synthetic filled worksheet row used to validate the supervised RPG learning loop.",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_filled_worksheet() -> dict[str, Any]:
    reviewed_packet = build_reviewed_packet()
    items = [
        worksheet_item_from_reviewed(row, index=index)
        for index, row in enumerate(reviewed_packet.get("items") or [], start=1)
        if isinstance(row, dict)
    ]
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet/v1",
        "description": "Synthetic filled RPG label worksheet for validating the import-to-scorer learning loop.",
        "source_plan_schema": "memory_maintenance_rpg_reviewed_label_batch/v1",
        "source_plan_ready_for_label_quality_eval": True,
        "source_plan_deficits": {},
        "worksheet_item_count": len(items),
        "allowed_labels": ALLOWED_LABELS,
        "review_instructions": ["Synthetic fixture; do not use for policy promotion."],
        "items": items,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["synthetic_fixture_not_real_reviewed_outcome"],
        "next_action": "import_and_validate_shadow_learning_loop",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_learning_loop_report(*, min_labels: int = 12) -> dict[str, Any]:
    worksheet = build_filled_worksheet()
    imported_packet = import_worksheet(worksheet, min_labels=min_labels)
    label_bank = build_label_bank(imported_packet, min_labels=min_labels)
    quality = build_quality_report(imported_packet, label_bank)
    scorer = build_scorer_report(label_bank)
    loo = scorer.get("leave_one_out") or {}
    checks = {
        "worksheet_filled": worksheet.get("worksheet_item_count") >= min_labels,
        "import_ready_for_label_quality": imported_packet.get("ready_for_label_quality_eval") is True,
        "label_bank_ready": label_bank.get("ready_for_scorer_training") is True,
        "quality_ready_for_shadow": quality.get("ready_for_shadow_scorer_training") is True,
        "scorer_ready_for_shadow": scorer.get("ready_for_shadow_scorer") is True,
        "scorer_accuracy_floor": float(loo.get("accuracy") or 0.0) >= 0.5,
        "policy_blocked": imported_packet.get("ready_for_policy_use") is False
        and label_bank.get("ready_for_policy_use") is False
        and quality.get("ready_for_policy_use") is False
        and scorer.get("ready_for_policy_use") is False,
        "report_only": worksheet.get("report_only") is True
        and imported_packet.get("report_only") is True
        and label_bank.get("report_only") is True
        and quality.get("report_only") is True
        and scorer.get("report_only") is True
        and imported_packet.get("mutates_db") is False
        and label_bank.get("mutates_db") is False
        and quality.get("mutates_db") is False
        and scorer.get("mutates_db") is False,
    }
    return {
        "schema": "memory_maintenance_rpg_filled_worksheet_learning_loop/v1",
        "ok": all(checks.values()),
        "description": "Report-only end-to-end validation of filled worksheet import into RPG label bank, quality report, and scorer.",
        "checks": checks,
        "worksheet_summary": {
            "worksheet_item_count": worksheet.get("worksheet_item_count"),
            "allowed_labels": worksheet.get("allowed_labels"),
        },
        "import_summary": {
            "packet_item_count": imported_packet.get("packet_item_count"),
            "label_counts": imported_packet.get("label_counts"),
            "ready_for_label_quality_eval": imported_packet.get("ready_for_label_quality_eval"),
            "promotion_blockers": imported_packet.get("promotion_blockers"),
        },
        "label_bank_summary": {
            "labeled_count": label_bank.get("labeled_count"),
            "ready_for_scorer_training": label_bank.get("ready_for_scorer_training"),
            "family_accuracy": (label_bank.get("prediction_probe") or {}).get("family_accuracy"),
        },
        "quality_summary": {
            "ready_for_shadow_scorer_training": quality.get("ready_for_shadow_scorer_training"),
            "dominant_label_ratio": quality.get("dominant_label_ratio"),
            "promotion_blockers": quality.get("promotion_blockers"),
        },
        "scorer_summary": {
            "ready_for_shadow_scorer": scorer.get("ready_for_shadow_scorer"),
            "leave_one_out_accuracy": loo.get("accuracy"),
            "promotion_blockers": scorer.get("promotion_blockers"),
        },
        "next_action": "replace_synthetic_fixture_with_real_filled_worksheet_labels",
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            "synthetic_fixture_not_real_reviewed_outcome",
            "real_labeled_packet_validation_required",
            "real_maintenance_outcome_validation_required",
        ],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Filled Worksheet Learning Loop",
        "",
        "Report-only end-to-end validation of filled worksheet import into RPG label bank, quality report, and scorer.",
        "",
        f"Passed: `{report['ok']}`",
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
            "## Import Summary",
            "",
            "```json",
            json.dumps(report.get("import_summary"), indent=2),
            "```",
            "",
            "## Scorer Summary",
            "",
            "```json",
            json.dumps(report.get("scorer_summary"), indent=2),
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
    parser = argparse.ArgumentParser(description="Validate filled RPG worksheet import through label bank/scorer.")
    parser.add_argument("--min-labels", type=int, default=12)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_learning_loop_report(min_labels=max(1, int(args.min_labels)))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "imported_items": (report.get("import_summary") or {}).get("packet_item_count"),
                "scorer_ready_for_shadow": (report.get("scorer_summary") or {}).get("ready_for_shadow_scorer"),
                "ready_for_policy_use": report["ready_for_policy_use"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
