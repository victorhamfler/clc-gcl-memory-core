from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_operator_outcome_capture import build_capture  # noqa: E402
from eval.memory_maintenance_operator_outcome_capture_regression import outcomes_fixture, packet_fixture  # noqa: E402
from eval.memory_maintenance_operator_outcome_rpg_feedback import build_feedback_packet  # noqa: E402
from eval.memory_maintenance_rpg_feedback_merge_evaluation import build_evaluation  # noqa: E402
from eval.memory_maintenance_rpg_natural_candidate_review_packet import LABEL_OPTIONS  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_feedback_merge_evaluation_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_feedback_merge_evaluation_regression_report.md"


def item(index: int, klass: str, label: str, relation: float, island: float) -> dict:
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"natural_merge_fixture:{index}:{klass}",
        "candidate_class": klass,
        "source_db": "natural_fixture",
        "left_memory_id": f"natural_left_{index}",
        "right_memory_id": f"natural_right_{index}",
        "left_domain": "natural",
        "right_domain": "natural",
        "same_domain": True,
        "cosine": 0.84,
        "jaccard": 0.32,
        "rpg_target_relation": relation,
        "rpg_target_island_ratio": island,
        "left_preview": "natural left",
        "right_preview": "natural right",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": label,
        "reviewer": "regression",
        "review_notes": "natural label fixture",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def natural_packet_fixture() -> dict:
    rows = [
        item(1, "near_duplicate_like", "safe_duplicate", 0.90, 1.45),
        item(2, "near_duplicate_like", "safe_duplicate", 0.86, 1.40),
        item(3, "stale_or_update_like", "stale_or_update_conflict", 0.62, 1.18),
        item(4, "bridge_like", "bridge_contamination", 0.55, 1.12),
        item(5, "cross_domain_related", "harmless_related_memory", 0.33, 1.02),
        item(6, "bridge_like", "uncertain_needs_more_context", 0.42, 1.08),
    ]
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "description": "Natural RPG labels fixture.",
        "source_schema": "regression_fixture/v1",
        "source_pair_count": len(rows),
        "packet_item_count": len(rows),
        "allowed_labels": LABEL_OPTIONS,
        "items": rows,
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def operator_feedback_fixture() -> dict:
    packet = packet_fixture()
    capture = build_capture(packet, outcomes_fixture(packet))
    return build_feedback_packet(capture)


def main() -> int:
    natural = natural_packet_fixture()
    operator_feedback = operator_feedback_fixture()
    report = build_evaluation(natural, operator_feedback, min_labels=6)
    natural_summary = (report.get("natural") or {}).get("summary") or {}
    operator_summary = (report.get("operator_feedback") or {}).get("summary") or {}
    combined_summary = (report.get("combined") or {}).get("summary") or {}
    comparison = report.get("comparison") or {}
    checks = {
        "schema_ok": report.get("schema") == "memory_maintenance_rpg_feedback_merge_evaluation/v1",
        "operator_feedback_consumed": operator_summary.get("labeled_count") == 2
        and (operator_summary.get("label_counts") or {}).get("safe_duplicate") == 1,
        "combined_label_count_grows": int(combined_summary.get("labeled_count") or 0)
        == int(natural_summary.get("labeled_count") or 0) + int(operator_summary.get("labeled_count") or 0),
        "comparison_reports_label_gain": comparison.get("label_gain_from_operator_feedback") == 2,
        "combined_variant_preserves_quality_contract": (report.get("combined") or {}).get("quality", {}).get("schema")
        == "memory_maintenance_rpg_label_quality_report/v1"
        and (report.get("combined") or {}).get("label_bank", {}).get("schema")
        == "memory_maintenance_rpg_natural_label_bank/v1",
        "scorer_contract_present": (report.get("combined") or {}).get("scorer", {}).get("schema")
        == "memory_maintenance_rpg_label_scorer/v1",
        "non_policy": report.get("ready_for_policy_use") is False and report.get("promotion_ready") is False,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_feedback_merge_evaluation_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "evaluation": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Feedback Merge Evaluation Regression",
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
