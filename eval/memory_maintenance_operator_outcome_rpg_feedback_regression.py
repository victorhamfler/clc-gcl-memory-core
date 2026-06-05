from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_operator_outcome_capture_regression import outcomes_fixture, packet_fixture  # noqa: E402
from eval.memory_maintenance_operator_outcome_capture import build_capture  # noqa: E402
from eval.memory_maintenance_operator_outcome_rpg_feedback import build_feedback_packet  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_operator_outcome_rpg_feedback_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_operator_outcome_rpg_feedback_regression_report.md"


def main() -> int:
    packet = packet_fixture()
    capture = build_capture(packet, outcomes_fixture(packet))
    feedback = build_feedback_packet(capture)
    label_bank = build_label_bank(feedback, min_labels=2)
    invalid_capture = {
        **capture,
        "readiness": "capture_needs_review",
        "outcomes": [],
        "outcome_count": 0,
    }
    blocked_feedback = build_feedback_packet(invalid_capture)
    first = (feedback.get("items") or [{}])[0]
    checks = {
        "feedback_schema_compatible": feedback.get("schema")
        == "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "feedback_ready_for_label_bank_not_policy": feedback.get("ready_for_label_bank") is True
        and feedback.get("ready_for_policy_use") is False
        and feedback.get("promotion_ready") is False,
        "operator_labels_preserved": feedback.get("packet_item_count") == 2
        and (feedback.get("label_counts") or {}).get("safe_duplicate") == 1
        and (feedback.get("label_counts") or {}).get("uncertain_needs_more_context") == 1,
        "source_metadata_preserved": first.get("source_packet_item_id")
        and first.get("source_operator_outcome") == "accept"
        and first.get("source_label") == "operator_explicit",
        "label_bank_can_consume_feedback": label_bank.get("schema") == "memory_maintenance_rpg_natural_label_bank/v1"
        and label_bank.get("labeled_count") == 2
        and not label_bank.get("invalid_label_ids"),
        "invalid_capture_blocks_label_bank_readiness": blocked_feedback.get("ready_for_label_bank") is False
        and "operator_outcome_capture_not_valid_for_feedback" in (blocked_feedback.get("promotion_blockers") or []),
        "report_only": feedback.get("report_only") is True
        and feedback.get("mutates_db") is False
        and feedback.get("mutates_runtime") is False
        and feedback.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_operator_outcome_rpg_feedback_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "feedback_packet": feedback,
        "label_bank_probe": label_bank,
        "blocked_feedback_packet": blocked_feedback,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Operator Outcome RPG Feedback Regression",
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
