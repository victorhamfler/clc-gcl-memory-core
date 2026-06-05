from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_real_use_reviewed_learning_loop import build_report  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_real_use_reviewed_learning_loop_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_real_use_reviewed_learning_loop_regression_report.md"


def main() -> int:
    report = build_report(min_labels=12)
    checks = {
        "report_ok": report.get("ok") is True,
        "uses_real_use_source": (report.get("worksheet_summary") or {}).get("source_plan_schema")
        == "full_memory_brain_real_use_eval/v1",
        "imports_enough_items": (report.get("import_summary") or {}).get("packet_item_count", 0) >= 12,
        "has_multiple_label_classes": len((report.get("import_summary") or {}).get("label_counts") or {}) >= 4,
        "has_multiple_candidate_classes": len((report.get("import_summary") or {}).get("class_counts") or {}) >= 4,
        "quality_shadow_ready": (report.get("quality_summary") or {}).get("ready_for_shadow_scorer_training") is True,
        "scorer_shadow_ready": (report.get("scorer_summary") or {}).get("ready_for_shadow_scorer") is True,
        "policy_blocked": report.get("ready_for_policy_use") is False
        and report.get("promotion_ready") is False,
        "external_review_blocker_retained": "external_reviewer_confirmation_required"
        in (report.get("promotion_blockers") or []),
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_real_use_reviewed_learning_loop_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "real_use_summary": {
            "import_summary": report.get("import_summary"),
            "quality_summary": report.get("quality_summary"),
            "scorer_summary": report.get("scorer_summary"),
            "promotion_blockers": report.get("promotion_blockers"),
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Real-Use Reviewed Learning Loop Regression",
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
