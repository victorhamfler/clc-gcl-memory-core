from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_label_scorer import build_report  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank_regression import fixture_packet  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_label_scorer_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_label_scorer_regression_report.md"


def main() -> int:
    label_bank = build_label_bank(fixture_packet(), min_labels=6)
    report = build_report(label_bank)
    loo = report.get("leave_one_out") or {}
    model = report.get("model") or {}
    checks = {
        "schema_ok": report.get("schema") == "memory_maintenance_rpg_label_scorer/v1",
        "model_schema_ok": model.get("schema") == "memory_maintenance_rpg_label_scorer_centroids/v1",
        "labeled_examples_used": report.get("labeled_count") == 6,
        "centroids_have_multiple_labels": len(model.get("centroids") or {}) >= 3,
        "leave_one_out_present": loo.get("schema") == "memory_maintenance_rpg_label_scorer_leave_one_out/v1"
        and int(loo.get("evaluated_count") or 0) > 0,
        "low_data_blocks_shadow_and_policy": report.get("ready_for_shadow_scorer") is False
        and report.get("ready_for_policy_use") is False
        and report.get("promotion_ready") is False
        and "leave_one_out_accuracy_below_shadow_threshold" in (report.get("promotion_blockers") or []),
        "real_validation_blockers_remain": "real_labeled_packet_validation_required" in (
            report.get("promotion_blockers") or []
        )
        and "real_maintenance_outcome_validation_required" in (report.get("promotion_blockers") or []),
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_label_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "scorer": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Scorer Regression",
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
