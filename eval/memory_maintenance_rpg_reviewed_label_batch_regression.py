from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_label_quality_report import build_quality_report  # noqa: E402
from eval.memory_maintenance_rpg_label_scorer import build_report as build_scorer_report  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank  # noqa: E402
from eval.memory_maintenance_rpg_reviewed_label_batch import build_packet  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_reviewed_label_batch_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_reviewed_label_batch_regression_report.md"


def main() -> int:
    packet = build_packet()
    bank = build_label_bank(packet, min_labels=12)
    quality = build_quality_report(packet, bank)
    scorer = build_scorer_report(bank)
    loo = scorer.get("leave_one_out") or {}
    checks = {
        "packet_schema_ok": packet.get("schema") == "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "balanced_label_batch": packet.get("packet_item_count") == 18
        and len(packet.get("label_counts") or {}) == 6
        and max((packet.get("label_counts") or {}).values()) == 3,
        "label_bank_ready": bank.get("ready_for_scorer_training") is True
        and bank.get("ready_for_policy_use") is False,
        "quality_ready_for_shadow": quality.get("ready_for_shadow_scorer_training") is True
        and quality.get("ready_for_policy_use") is False,
        "scorer_ready_for_shadow": scorer.get("ready_for_shadow_scorer") is True
        and scorer.get("ready_for_policy_use") is False,
        "scorer_accuracy_floor": float(loo.get("accuracy") or 0.0) >= 0.5,
        "report_only": packet.get("report_only") is True
        and bank.get("report_only") is True
        and quality.get("report_only") is True
        and scorer.get("report_only") is True
        and packet.get("mutates_db") is False
        and bank.get("mutates_db") is False
        and quality.get("mutates_db") is False
        and scorer.get("mutates_db") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_reviewed_label_batch_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "packet_summary": {
            "packet_item_count": packet.get("packet_item_count"),
            "label_counts": packet.get("label_counts"),
            "class_counts": packet.get("class_counts"),
        },
        "label_bank_summary": {
            "labeled_count": bank.get("labeled_count"),
            "ready_for_scorer_training": bank.get("ready_for_scorer_training"),
            "family_accuracy": (bank.get("prediction_probe") or {}).get("family_accuracy"),
        },
        "quality_summary": {
            "ready_for_shadow_scorer_training": quality.get("ready_for_shadow_scorer_training"),
            "promotion_blockers": quality.get("promotion_blockers"),
        },
        "scorer_summary": {
            "ready_for_shadow_scorer": scorer.get("ready_for_shadow_scorer"),
            "leave_one_out_accuracy": loo.get("accuracy"),
            "promotion_blockers": scorer.get("promotion_blockers"),
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Reviewed Label Batch Regression",
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
