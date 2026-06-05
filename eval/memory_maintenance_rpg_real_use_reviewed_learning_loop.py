from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


try:
    from eval.memory_maintenance_rpg_filled_worksheet_import import build_packet as import_worksheet
    from eval.memory_maintenance_rpg_label_quality_report import build_quality_report
    from eval.memory_maintenance_rpg_label_review_worksheet import ALLOWED_LABELS
    from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report
    from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank
except ModuleNotFoundError:
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))
    from eval.memory_maintenance_rpg_filled_worksheet_import import build_packet as import_worksheet
    from eval.memory_maintenance_rpg_label_quality_report import build_quality_report
    from eval.memory_maintenance_rpg_label_review_worksheet import ALLOWED_LABELS
    from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report
    from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_real_use_reviewed_learning_loop_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_real_use_reviewed_learning_loop_report.md"


MEMORIES = {
    "helios_blue_a": {
        "domain": "project",
        "text": "Project Helios uses the blue retrieval plan for memory routing.",
    },
    "helios_blue_b": {
        "domain": "project",
        "text": "Project Helios uses the blue retrieval plan for memory routing.",
    },
    "helios_green": {
        "domain": "project",
        "text": "Correction: Project Helios now uses the green retrieval plan for memory routing.",
    },
    "helios_bridge": {
        "domain": "bridge",
        "text": "The Helios memory route should not be confused with robotics actuator current checks.",
    },
    "robotics_safety": {
        "domain": "robotics",
        "text": "Robotics actuator current checks use separate torque safety limits.",
    },
    "helios_session": {
        "domain": "session",
        "text": "Question: What retrieval plan does Project Helios use now? Answer: Project Helios now uses the green retrieval plan.",
    },
    "robotics_session": {
        "domain": "session",
        "text": "Question: Should Helios routing be mixed with robotics actuator current checks? Answer: Keep route memory and actuator-current safety separate.",
    },
    "helios_note": {
        "domain": "project",
        "text": "Remember that Helios routing is a memory-plan topic and not a robotics torque-control topic.",
    },
}


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def row(
    index: int,
    left_id: str,
    right_id: str,
    *,
    candidate_class: str,
    label: str,
    relation: float,
    island: float,
    cosine: float,
    jaccard: float,
    hint: str,
) -> dict[str, Any]:
    left = MEMORIES[left_id]
    right = MEMORIES[right_id]
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet_item/v1",
        "worksheet_id": f"real_use_reviewed:{index:03d}",
        "source_review_item_id": f"real_use_pair:{left_id}:{right_id}",
        "candidate_class": candidate_class,
        "source_db": "full_memory_brain_real_use_eval",
        "left_memory_id": left_id,
        "right_memory_id": right_id,
        "left_domain": left["domain"],
        "right_domain": right["domain"],
        "same_domain": left["domain"] == right["domain"],
        "cosine": round(cosine, 6),
        "jaccard": round(jaccard, 6),
        "review_hint": hint,
        "rpg_target_relation": round(relation, 6),
        "rpg_target_island_ratio": round(island, 6),
        "left_preview": left["text"],
        "right_preview": right["text"],
        "allowed_labels": ALLOWED_LABELS,
        "review_label": label,
        "reviewer": "local_real_use_eval_reviewer",
        "review_notes": "Reviewed from the full memory-brain real-use scenario; still requires external/Hermes confirmation before policy use.",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def build_real_use_worksheet() -> dict[str, Any]:
    specs = [
        ("helios_blue_a", "helios_blue_b", "exact_duplicate", "safe_duplicate", 0.88, 1.5, 0.99, 0.96, "identical_current_fact"),
        ("helios_blue_a", "helios_green", "stale_or_update_like", "stale_or_update_conflict", 0.72, 1.38, 0.9, 0.46, "green_correction_supersedes_blue"),
        ("helios_blue_b", "helios_green", "stale_or_update_like", "stale_or_update_conflict", 0.7, 1.36, 0.88, 0.43, "green_correction_supersedes_duplicate_blue"),
        ("helios_bridge", "robotics_safety", "bridge_like", "bridge_contamination", 0.48, 1.18, 0.62, 0.18, "bridge_warning_separates_topics"),
        ("helios_green", "helios_session", "near_duplicate_like", "semantic_near_duplicate", 0.58, 1.24, 0.86, 0.3, "session_answer_restates_current_fact"),
        ("robotics_safety", "robotics_session", "near_duplicate_like", "semantic_near_duplicate", 0.55, 1.22, 0.84, 0.28, "session_answer_restates_separation_rule"),
        ("helios_green", "helios_note", "cross_domain_related", "harmless_related_memory", 0.24, 1.08, 0.44, 0.09, "related_context_not_maintenance_action"),
        ("helios_bridge", "helios_note", "cross_domain_related", "harmless_related_memory", 0.22, 1.07, 0.42, 0.08, "related_warning_context"),
        ("helios_blue_a", "robotics_safety", "bridge_like", "bridge_contamination", 0.42, 1.14, 0.56, 0.12, "different_domains_should_not_merge"),
        ("helios_green", "robotics_safety", "bridge_like", "bridge_contamination", 0.4, 1.13, 0.54, 0.11, "current_plan_and_robotics_are_separate"),
        ("helios_session", "robotics_session", "unknown", "uncertain_needs_more_context", 0.34, 1.11, 0.5, 0.12, "session_summaries_need_more_provenance"),
        ("helios_blue_b", "helios_session", "unknown", "uncertain_needs_more_context", 0.36, 1.12, 0.52, 0.13, "old_fact_vs_session_context_needs_lineage"),
        ("helios_session", "helios_note", "near_duplicate_like", "semantic_near_duplicate", 0.56, 1.23, 0.85, 0.29, "session_and_note_restate_current_helios_scope"),
        ("helios_blue_a", "helios_note", "stale_or_update_like", "stale_or_update_conflict", 0.66, 1.31, 0.82, 0.34, "old_blue_plan_conflicts_with_current_scope_note"),
        ("robotics_safety", "helios_note", "cross_domain_related", "harmless_related_memory", 0.2, 1.06, 0.39, 0.07, "related_separation_context_only"),
    ]
    items = [
        row(
            index,
            left_id,
            right_id,
            candidate_class=candidate_class,
            label=label,
            relation=relation,
            island=island,
            cosine=cosine,
            jaccard=jaccard,
            hint=hint,
        )
        for index, (left_id, right_id, candidate_class, label, relation, island, cosine, jaccard, hint) in enumerate(
            specs, start=1
        )
    ]
    return {
        "schema": "memory_maintenance_rpg_label_review_worksheet/v1",
        "description": "Locally reviewed worksheet from the full memory-brain real-use correction/duplicate/bridge scenario.",
        "source_plan_schema": "full_memory_brain_real_use_eval/v1",
        "source_plan_ready_for_label_quality_eval": True,
        "source_plan_deficits": {},
        "worksheet_item_count": len(items),
        "allowed_labels": ALLOWED_LABELS,
        "review_instructions": [
            "Labels are derived from the real-use eval's known correction, duplicate, and bridge relations.",
            "Treat as local reviewed evidence until confirmed by Hermes or a human operator.",
        ],
        "items": items,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": ["external_reviewer_confirmation_required", "real_maintenance_outcome_validation_required"],
        "next_action": "import_and_validate_real_use_shadow_learning_loop",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_report(*, min_labels: int = 12) -> dict[str, Any]:
    worksheet = build_real_use_worksheet()
    imported_packet = import_worksheet(worksheet, min_labels=min_labels)
    label_bank = build_label_bank(imported_packet, min_labels=min_labels)
    quality = build_quality_report(imported_packet, label_bank)
    scorer = build_scorer_report(label_bank)
    loo = scorer.get("leave_one_out") or {}
    checks = {
        "real_use_labels_available": worksheet.get("worksheet_item_count") >= min_labels,
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
        "schema": "memory_maintenance_rpg_real_use_reviewed_learning_loop/v1",
        "ok": all(checks.values()),
        "description": "Report-only supervised RPG learning loop using locally reviewed labels from the full memory-brain real-use scenario.",
        "checks": checks,
        "worksheet_summary": {
            "worksheet_item_count": worksheet.get("worksheet_item_count"),
            "source_plan_schema": worksheet.get("source_plan_schema"),
        },
        "import_summary": {
            "packet_item_count": imported_packet.get("packet_item_count"),
            "label_counts": imported_packet.get("label_counts"),
            "class_counts": imported_packet.get("class_counts"),
            "ready_for_label_quality_eval": imported_packet.get("ready_for_label_quality_eval"),
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
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            "external_reviewer_confirmation_required",
            "real_maintenance_outcome_validation_required",
            "policy_ablation_required",
        ],
        "next_action": "confirm_real_use_labels_with_external_reviewer_or_hermes",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Real-Use Reviewed Learning Loop",
        "",
        "Report-only supervised RPG learning loop using locally reviewed labels from the full memory-brain real-use scenario.",
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
    parser = argparse.ArgumentParser(description="Validate real-use reviewed RPG worksheet learning loop.")
    parser.add_argument("--min-labels", type=int, default=12)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(min_labels=max(1, int(args.min_labels)))
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
