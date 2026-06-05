from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_filled_worksheet_learning_loop import build_learning_loop_report  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_filled_worksheet_learning_loop_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_filled_worksheet_learning_loop_regression_report.md"


def main() -> int:
    report = build_learning_loop_report(min_labels=12)
    checks = {
        "report_ok": report.get("ok") is True,
        "imports_enough_items": (report.get("import_summary") or {}).get("packet_item_count", 0) >= 12,
        "quality_shadow_ready": (report.get("quality_summary") or {}).get("ready_for_shadow_scorer_training") is True,
        "scorer_shadow_ready": (report.get("scorer_summary") or {}).get("ready_for_shadow_scorer") is True,
        "policy_blocked": report.get("ready_for_policy_use") is False
        and report.get("promotion_ready") is False,
        "synthetic_blocker_retained": "synthetic_fixture_not_real_reviewed_outcome"
        in (report.get("promotion_blockers") or []),
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_filled_worksheet_learning_loop_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "learning_loop_summary": {
            "import_summary": report.get("import_summary"),
            "label_bank_summary": report.get("label_bank_summary"),
            "quality_summary": report.get("quality_summary"),
            "scorer_summary": report.get("scorer_summary"),
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Filled Worksheet Learning Loop Regression",
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
