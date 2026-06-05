from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_operator_review_packet import build_packet  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
FIXTURE_DIR = OUT_DIR / "memory_maintenance_operator_review_packet_fixture"
READY_GUARD = FIXTURE_DIR / "ready_guard.json"
BLOCKED_GUARD = FIXTURE_DIR / "blocked_guard.json"
QUALITY = FIXTURE_DIR / "rpg_label_quality.json"
SCORER = FIXTURE_DIR / "rpg_label_scorer.json"
OUT_JSON = OUT_DIR / "memory_maintenance_operator_review_packet_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_operator_review_packet_regression_report.md"


def candidate(*, ready: bool) -> dict:
    return {
        "schema": "memory_maintenance_rehearsal_guarded_candidate/v1",
        "id": "rehearsal_guard:duplicate_deprecation:alpha",
        "source_cluster_key": "duplicate_deprecation|safe_to_review",
        "operation_kind": "duplicate_deprecation",
        "recommended_action": "operator_review_duplicate_deprecation_candidate",
        "support": 2,
        "run_count": 2,
        "runs": [1, 2],
        "safe_count": 2 if ready else 0,
        "blocked_count": 0 if ready else 2,
        "readiness": "rehearsal_safe_evidence_ready" if ready else "blocked_recurrent_risk",
        "rpg_summary": {
            "schema": "memory_maintenance_rehearsal_rpg_cluster_summary/v1",
            "annotation_count": 2,
            "target_mean_relation_mean": 0.82 if ready else 0.31,
            "target_island_ratio_mean": 1.35 if ready else 0.75,
            "risk_flags": {} if ready else {"stale_marker": 2},
            "report_only": True,
            "mutates_db": False,
        },
        "ready_for_operator_review": ready,
        "blocked_reasons": [] if ready else ["operation_family_has_recurrent_risk"],
        "examples": [
            {
                "candidate_id": "alpha",
                "target_ids": ["keep_alpha", "dup_alpha"],
                "target_text_preview": {
                    "keep_alpha": "alpha duplicate fact",
                    "dup_alpha": "alpha duplicate fact",
                },
            }
        ],
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }


def write_guard(path: Path, *, ready: bool) -> None:
    report = {
        "schema": "memory_maintenance_rehearsal_candidate_guard/v1",
        "operator_review_candidate_count": 1 if ready else 0,
        "blocked_count": 0 if ready else 1,
        "risky_operation_kinds": [] if ready else ["duplicate_deprecation"],
        "guarded_candidates": [candidate(ready=True)] if ready else [],
        "blocked_candidates": [] if ready else [candidate(ready=False)],
        "report_only": True,
        "mutates_db": False,
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_rpg_learning_artifacts() -> None:
    QUALITY.write_text(
        json.dumps(
            {
                "schema": "memory_maintenance_rpg_label_quality_report/v1",
                "ready_for_shadow_scorer_training": True,
                "ready_for_policy_use": False,
                "labeled_count": 12,
                "label_counts": {
                    "safe_duplicate": 3,
                    "stale_or_update_conflict": 2,
                    "bridge_contamination": 2,
                    "harmless_related_memory": 2,
                    "uncertain_needs_more_context": 2,
                    "semantic_near_duplicate": 1,
                },
                "promotion_blockers": [
                    "real_labeled_packet_validation_required",
                    "real_maintenance_outcome_validation_required",
                ],
                "report_only": True,
                "mutates_db": False,
                "mutates_runtime": False,
                "mutates_config": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    SCORER.write_text(
        json.dumps(
            {
                "schema": "memory_maintenance_rpg_label_scorer/v1",
                "ready_for_shadow_scorer": False,
                "ready_for_policy_use": False,
                "label_counts": {
                    "safe_duplicate": 2,
                    "stale_or_update_conflict": 1,
                    "bridge_contamination": 1,
                },
                "promotion_blockers": [
                    "leave_one_out_accuracy_below_shadow_threshold",
                    "real_labeled_packet_validation_required",
                    "real_maintenance_outcome_validation_required",
                ],
                "report_only": True,
                "mutates_db": False,
                "mutates_runtime": False,
                "mutates_config": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def command_is_safe(command: str) -> bool:
    return (
        "memory_maintenance_copied_db_rehearsal.py" in command
        and "--enable-mutation" not in command
        and "--no-dry-run" not in command
        and "memory_maintenance_apply_operator_command.py" not in command
    )


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    write_guard(READY_GUARD, ready=True)
    write_guard(BLOCKED_GUARD, ready=False)
    write_rpg_learning_artifacts()
    ready_packet = build_packet(
        READY_GUARD,
        source_db="source.db",
        apply_plan="plan.json",
        work_dir="E:\\projcod2_artifacts_archive\\current_rehearsals\\operator_review",
        operator_id="packet_regression",
        rpg_label_quality=QUALITY,
        rpg_label_scorer=SCORER,
    )
    blocked_packet = build_packet(
        BLOCKED_GUARD,
        source_db="source.db",
        apply_plan="plan.json",
        work_dir="E:\\projcod2_artifacts_archive\\current_rehearsals\\operator_review",
        operator_id="packet_regression",
        rpg_label_quality=QUALITY,
        rpg_label_scorer=SCORER,
    )
    ready_item = (ready_packet.get("ready_items") or [{}])[0]
    blocked_item = (blocked_packet.get("blocked_items") or [{}])[0]
    learning_context = ready_packet.get("rpg_learning_context") or {}
    checks = {
        "ready_packet_schema": ready_packet.get("schema") == "memory_maintenance_operator_review_packet/v1",
        "ready_packet_has_ready_item": ready_packet.get("ready_count") == 1
        and ready_item.get("status") == "ready_for_operator_review",
        "ready_item_has_targets_and_previews": ready_item.get("target_ids") == ["keep_alpha", "dup_alpha"]
        and bool(ready_item.get("target_text_preview")),
        "ready_item_preserves_rpg_summary": (ready_item.get("rpg_summary") or {}).get("annotation_count") == 2
        and float((ready_item.get("rpg_summary") or {}).get("target_mean_relation_mean") or 0.0) > 0.8,
        "blocked_packet_has_blocked_item": blocked_packet.get("blocked_count") == 1
        and blocked_item.get("status") == "blocked_before_operator_review",
        "blocked_item_preserves_blockers": "operation_family_has_recurrent_risk"
        in (blocked_item.get("blocked_reasons") or []),
        "blocked_item_preserves_rpg_risk_summary": ((blocked_item.get("rpg_summary") or {}).get("risk_flags") or {}).get(
            "stale_marker"
        )
        == 2,
        "rpg_learning_context_is_explanation_only": learning_context.get("schema")
        == "memory_maintenance_operator_rpg_learning_context/v1"
        and learning_context.get("label_quality_ready_for_shadow_scorer_training") is True
        and learning_context.get("scorer_ready_for_policy") is False
        and learning_context.get("operator_use") == "explanation_only_do_not_auto_apply"
        and learning_context.get("mutation_allowed") is False,
        "items_preserve_rpg_learning_context": (ready_item.get("rpg_learning_context") or {}).get("schema")
        == "memory_maintenance_operator_rpg_learning_context/v1"
        and (blocked_item.get("rpg_learning_context") or {}).get("schema")
        == "memory_maintenance_operator_rpg_learning_context/v1",
        "commands_are_safe_rehearsal_only": command_is_safe(ready_packet.get("safe_copied_db_rehearsal_command") or "")
        and command_is_safe(blocked_packet.get("safe_copied_db_rehearsal_command") or ""),
        "mutation_never_allowed": ready_packet.get("mutation_allowed") is False
        and blocked_packet.get("mutation_allowed") is False
        and ready_item.get("mutation_allowed") is False
        and blocked_item.get("mutation_allowed") is False,
        "reports_non_mutating": ready_packet.get("mutates_db") is False
        and blocked_packet.get("mutates_db") is False
        and ready_packet.get("report_only") is True
        and blocked_packet.get("report_only") is True,
    }
    result = {
        "schema": "memory_maintenance_operator_review_packet_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "ready_packet": ready_packet,
        "blocked_packet": blocked_packet,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Operator Review Packet Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
