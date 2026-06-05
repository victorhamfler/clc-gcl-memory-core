from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_operator_outcome_capture import (  # noqa: E402
    CAPTURE_SCHEMA,
    OUTCOME_SCHEMA,
    build_capture,
    build_outcome_template,
)
from eval.memory_maintenance_operator_review_packet_regression import (  # noqa: E402
    BLOCKED_GUARD,
    QUALITY,
    READY_GUARD,
    SCORER,
    write_guard,
    write_rpg_learning_artifacts,
)
from eval.memory_maintenance_operator_review_packet import build_packet  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_operator_outcome_capture_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_operator_outcome_capture_regression_report.md"


def packet_fixture() -> dict:
    READY_GUARD.parent.mkdir(parents=True, exist_ok=True)
    write_guard(READY_GUARD, ready=True)
    write_guard(BLOCKED_GUARD, ready=False)
    write_rpg_learning_artifacts()
    ready = build_packet(
        READY_GUARD,
        source_db="source.db",
        apply_plan="plan.json",
        operator_id="outcome_capture_regression",
        rpg_label_quality=QUALITY,
        rpg_label_scorer=SCORER,
    )
    blocked = build_packet(
        BLOCKED_GUARD,
        source_db="source.db",
        apply_plan="plan.json",
        operator_id="outcome_capture_regression",
        rpg_label_quality=QUALITY,
        rpg_label_scorer=SCORER,
    )
    return {
        **ready,
        "ready_items": ready.get("ready_items") or [],
        "blocked_items": blocked.get("blocked_items") or [],
        "ready_count": len(ready.get("ready_items") or []),
        "blocked_count": len(blocked.get("blocked_items") or []),
    }


def outcomes_fixture(packet: dict) -> dict:
    ready_id = (packet.get("ready_items") or [{}])[0].get("id")
    blocked_id = (packet.get("blocked_items") or [{}])[0].get("id")
    return {
        "schema": OUTCOME_SCHEMA,
        "source_packet_schema": packet.get("schema"),
        "outcomes": [
            {
                "packet_item_id": ready_id,
                "outcome": "accept",
                "reviewer": "regression",
                "reason": "duplicate deprecation candidate is safe in copied DB rehearsal",
                "rpg_training_label": "safe_duplicate",
                "rpg_training_note": "operator confirms duplicate relation",
                "operator_apply_note": "still requires explicit apply command",
            },
            {
                "packet_item_id": blocked_id,
                "outcome": "needs_more_evidence",
                "reviewer": "regression",
                "reason": "blocked recurrent risk should not be promoted",
                "rpg_training_label": "",
                "rpg_training_note": "derived uncertain label is acceptable",
                "operator_apply_note": "",
            },
        ],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def main() -> int:
    packet = packet_fixture()
    template = build_outcome_template(packet)
    capture = build_capture(packet, outcomes_fixture(packet))
    invalid = build_capture(
        packet,
        {
            "schema": OUTCOME_SCHEMA,
            "outcomes": [
                {
                    "packet_item_id": "missing_packet_item",
                    "outcome": "invented",
                    "reviewer": "regression",
                    "rpg_training_label": "not_a_label",
                }
            ],
            "report_only": True,
            "mutates_db": False,
        },
    )
    first = (capture.get("outcomes") or [{}])[0]
    second = (capture.get("outcomes") or [{}, {}])[1]
    checks = {
        "template_schema_ok": template.get("schema") == OUTCOME_SCHEMA,
        "capture_schema_ok": capture.get("schema") == CAPTURE_SCHEMA,
        "captures_ready_and_blocked_items": capture.get("outcome_count") == 2
        and capture.get("known_outcome_count") == 2,
        "accepted_outcome_maps_to_safe_duplicate": first.get("outcome") == "accept"
        and first.get("rpg_training_label") == "safe_duplicate",
        "needs_more_evidence_derives_uncertain_label": second.get("outcome") == "needs_more_evidence"
        and second.get("rpg_training_label") == "uncertain_needs_more_context",
        "preserves_rpg_context": bool(first.get("rpg_summary"))
        and (first.get("rpg_learning_context") or {}).get("operator_use") == "explanation_only_do_not_auto_apply",
        "valid_capture_ready_for_feedback_not_policy": capture.get("readiness") == "capture_valid_for_rpg_label_feedback"
        and capture.get("ready_for_policy_use") is False
        and capture.get("promotion_ready") is False,
        "invalid_capture_blocks_feedback": invalid.get("readiness") == "capture_needs_review"
        and invalid.get("unknown_packet_item_ids") == ["missing_packet_item"]
        and bool(invalid.get("invalid_outcomes"))
        and bool(invalid.get("invalid_rpg_training_labels")),
        "report_only": capture.get("report_only") is True
        and capture.get("mutates_db") is False
        and capture.get("mutates_runtime") is False
        and capture.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_operator_outcome_capture_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "template": template,
        "capture": capture,
        "invalid_capture": invalid,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Operator Outcome Capture Regression",
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
