from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_natural_candidate_review_packet import LABEL_OPTIONS  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_natural_label_bank_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_natural_label_bank_regression_report.md"


def item(index: int, klass: str, label: str, relation: float, island: float) -> dict:
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"fixture:{index}:{klass}",
        "candidate_class": klass,
        "source_db": "fixture.db",
        "left_memory_id": f"left_{index}",
        "right_memory_id": f"right_{index}",
        "left_domain": "a",
        "right_domain": "a" if klass != "cross_domain_related" else "b",
        "same_domain": klass != "cross_domain_related",
        "cosine": 0.9,
        "jaccard": 0.3,
        "rpg_target_relation": relation,
        "rpg_target_island_ratio": island,
        "left_preview": "left fixture",
        "right_preview": "right fixture",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": label,
        "reviewer": "regression",
        "review_notes": "synthetic",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def fixture_packet() -> dict:
    items = [
        item(1, "near_duplicate_like", "safe_duplicate", 0.82, 1.42),
        item(2, "near_duplicate_like", "safe_duplicate", 0.78, 1.36),
        item(3, "stale_or_update_like", "stale_or_update_conflict", 0.62, 1.2),
        item(4, "bridge_like", "bridge_contamination", 0.55, 1.18),
        item(5, "cross_domain_related", "harmless_related_memory", 0.31, 1.05),
        item(6, "bridge_like", "uncertain_needs_more_context", 0.44, 1.1),
    ]
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "allowed_labels": LABEL_OPTIONS,
        "items": items,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def main() -> int:
    bank = build_label_bank(fixture_packet(), min_labels=6)
    probe = bank.get("prediction_probe") or {}
    checks = {
        "schema_ok": bank.get("schema") == "memory_maintenance_rpg_natural_label_bank/v1",
        "all_labels_counted": bank.get("labeled_count") == 6
        and bank.get("unlabeled_count") == 0
        and bank.get("invalid_label_ids") == [],
        "label_groups_present": set(bank.get("label_groups") or {}) == {
            "bridge_contamination",
            "harmless_related_memory",
            "safe_duplicate",
            "stale_or_update_conflict",
            "uncertain_needs_more_context",
        },
        "safe_metrics_higher_than_non_safe": float(bank.get("safe_relation_mean") or 0.0)
        > float(bank.get("non_safe_relation_mean") or 0.0)
        and float(bank.get("safe_island_mean") or 0.0) > float(bank.get("non_safe_island_mean") or 0.0),
        "prediction_probe_present": probe.get("schema") == "memory_maintenance_rpg_natural_label_prediction_probe/v1"
        and float(probe.get("family_accuracy") or 0.0) >= 0.6,
        "ready_for_scorer_training_but_not_policy": bank.get("ready_for_scorer_training") is True
        and bank.get("ready_for_policy_use") is False,
        "report_only": bank.get("report_only") is True
        and bank.get("mutates_db") is False
        and bank.get("mutates_runtime") is False
        and bank.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_natural_label_bank_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "label_bank": bank,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Natural Label Bank Regression",
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
