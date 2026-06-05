from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_filled_worksheet_import import build_packet  # noqa: E402
from eval.memory_maintenance_rpg_label_review_worksheet import build_worksheet  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_filled_worksheet_import_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_filled_worksheet_import_regression_report.md"


def fixture_plan() -> dict[str, object]:
    return {
        "schema": "memory_maintenance_rpg_label_collection_plan/v1",
        "ready_for_label_quality_eval": False,
        "deficits": {"labeled_examples": 2},
        "recommended_review_targets": [
            {
                "id": "target:a",
                "candidate_class": "near_duplicate_like",
                "review_hint": "looks_duplicate",
                "rpg_target_relation": 0.82,
                "rpg_target_island_ratio": 1.42,
                "left_preview": "Alpha plan is green.",
                "right_preview": "Alpha plan is green and current.",
            },
            {
                "id": "target:b",
                "candidate_class": "bridge_like",
                "review_hint": "cross_topic_bridge",
                "rpg_target_relation": 0.44,
                "rpg_target_island_ratio": 1.14,
                "left_preview": "Pizza preference is mushroom.",
                "right_preview": "Radar codename is ember.",
            },
        ],
    }


def main() -> int:
    worksheet = build_worksheet(fixture_plan())
    worksheet["items"][0]["review_label"] = "safe_duplicate"
    worksheet["items"][0]["reviewer"] = "regression"
    worksheet["items"][0]["review_notes"] = "Same current fact."
    worksheet["items"][1]["review_label"] = "bridge_contamination"
    worksheet["items"][1]["reviewer"] = "regression"
    worksheet["items"][1]["review_notes"] = "Cross-topic retrieval contamination risk."
    packet = build_packet(worksheet, min_labels=2)
    checks = {
        "packet_schema_ok": packet.get("schema") == "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "imports_only_labeled_rows": packet.get("packet_item_count") == 2,
        "label_counts_ok": packet.get("label_counts") == {
            "bridge_contamination": 1,
            "safe_duplicate": 1,
        },
        "source_ids_preserved": [item.get("source_review_item_id") for item in packet.get("items") or []]
        == ["target:a", "target:b"],
        "reviewer_required": not packet.get("missing_reviewer_source_ids"),
        "all_labels_allowed": not packet.get("invalid_label_source_ids"),
        "ready_for_label_quality": packet.get("ready_for_label_quality_eval") is True,
        "not_ready_for_policy": packet.get("ready_for_policy_use") is False
        and packet.get("promotion_ready") is False,
        "report_only": packet.get("report_only") is True
        and packet.get("mutates_db") is False
        and packet.get("mutates_runtime") is False
        and packet.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_filled_worksheet_import_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "packet_summary": {
            "packet_item_count": packet.get("packet_item_count"),
            "label_counts": packet.get("label_counts"),
            "promotion_blockers": packet.get("promotion_blockers"),
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Filled Worksheet Import Regression",
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
