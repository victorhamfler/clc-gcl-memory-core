from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_label_review_worksheet import ALLOWED_LABELS, build_worksheet  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_review_worksheet_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_review_worksheet_regression_report.md"


def fixture_plan() -> dict:
    return {
        "schema": "memory_maintenance_rpg_label_collection_plan/v1",
        "ready_for_label_quality_eval": False,
        "deficits": {"labeled_examples": 2, "label_classes": 1, "candidate_classes": 1},
        "recommended_review_targets": [
            {
                "id": "target:a",
                "candidate_class": "bridge_like",
                "review_hint": "check_if_pair_links_domains_that_should_stay_separate",
                "rpg_target_relation": 0.12,
                "rpg_target_island_ratio": 1.2,
                "left_preview": "left bridge preview",
                "right_preview": "right bridge preview",
            },
            {
                "id": "target:b",
                "candidate_class": "stale_or_update_like",
                "review_hint": "check_if_newer_memory_supersedes_or_corrects_older_memory",
                "rpg_target_relation": 0.18,
                "rpg_target_island_ratio": 1.4,
                "left_preview": "left stale preview",
                "right_preview": "right stale preview",
            },
        ],
        "report_only": True,
        "mutates_db": False,
    }


def main() -> int:
    worksheet = build_worksheet(fixture_plan())
    items = worksheet.get("items") or []
    checks = {
        "schema_ok": worksheet.get("schema") == "memory_maintenance_rpg_label_review_worksheet/v1",
        "item_count_matches_targets": worksheet.get("worksheet_item_count") == 2 and len(items) == 2,
        "labels_blank_for_operator": all(item.get("review_label") == "" for item in items),
        "allowed_labels_present": worksheet.get("allowed_labels") == ALLOWED_LABELS
        and all(item.get("allowed_labels") == ALLOWED_LABELS for item in items),
        "source_ids_preserved": {item.get("source_review_item_id") for item in items} == {"target:a", "target:b"},
        "operator_questions_present": all(item.get("operator_questions") for item in items),
        "policy_blocked": worksheet.get("ready_for_policy_use") is False
        and worksheet.get("promotion_ready") is False,
        "report_only": worksheet.get("report_only") is True
        and worksheet.get("mutates_db") is False
        and worksheet.get("mutates_runtime") is False
        and worksheet.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_label_review_worksheet_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "worksheet": worksheet,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Review Worksheet Regression",
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
