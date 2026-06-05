from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_label_quality_report import build_quality_report  # noqa: E402
from eval.memory_maintenance_rpg_natural_candidate_review_packet import LABEL_OPTIONS  # noqa: E402
from eval.memory_maintenance_rpg_natural_label_bank import build_label_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_label_quality_report_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_label_quality_report_regression_report.md"


def item(index: int, klass: str, label: str, relation: float, island: float) -> dict:
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"quality_fixture:{index}:{klass}",
        "candidate_class": klass,
        "source_db": "fixture.db",
        "left_memory_id": f"left_{index}",
        "right_memory_id": f"right_{index}",
        "left_domain": "a" if klass != "cross_domain_related" else "b",
        "right_domain": "a",
        "same_domain": klass != "cross_domain_related",
        "cosine": 0.88 if label == "safe_duplicate" else 0.54,
        "jaccard": 0.42 if label == "safe_duplicate" else 0.18,
        "rpg_target_relation": relation,
        "rpg_target_island_ratio": island,
        "left_preview": "left fixture",
        "right_preview": "right fixture",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": label,
        "reviewer": "regression",
        "review_notes": "synthetic quality fixture",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def fixture_packet() -> dict:
    rows = [
        item(1, "near_duplicate_like", "safe_duplicate", 0.90, 1.50),
        item(2, "near_duplicate_like", "safe_duplicate", 0.86, 1.45),
        item(3, "near_duplicate_like", "semantic_near_duplicate", 0.75, 1.32),
        item(4, "stale_or_update_like", "stale_or_update_conflict", 0.66, 1.22),
        item(5, "stale_or_update_like", "stale_or_update_conflict", 0.63, 1.18),
        item(6, "bridge_like", "bridge_contamination", 0.58, 1.16),
        item(7, "bridge_like", "bridge_contamination", 0.56, 1.15),
        item(8, "cross_domain_related", "harmless_related_memory", 0.36, 1.02),
        item(9, "cross_domain_related", "harmless_related_memory", 0.34, 1.01),
        item(10, "exact_duplicate", "safe_duplicate", 0.95, 1.55),
        item(11, "bridge_like", "uncertain_needs_more_context", 0.43, 1.08),
        item(12, "stale_or_update_like", "uncertain_needs_more_context", 0.45, 1.07),
    ]
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "allowed_labels": LABEL_OPTIONS,
        "items": rows,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def sparse_packet() -> dict:
    packet = fixture_packet()
    packet["items"] = packet["items"][:4]
    return packet


def main() -> int:
    good_packet = fixture_packet()
    good_bank = build_label_bank(good_packet, min_labels=6)
    good_report = build_quality_report(good_packet, good_bank)
    sparse = sparse_packet()
    sparse_bank = build_label_bank(sparse, min_labels=6)
    sparse_report = build_quality_report(sparse, sparse_bank)
    checks = {
        "schema_ok": good_report.get("schema") == "memory_maintenance_rpg_label_quality_report/v1",
        "good_fixture_ready_for_shadow_not_policy": good_report.get("ready_for_shadow_scorer_training") is True
        and good_report.get("ready_for_policy_use") is False
        and good_report.get("promotion_ready") is False,
        "good_fixture_has_coverage": good_report.get("labeled_count") == 12
        and len(good_report.get("label_counts") or {}) >= 5
        and len(good_report.get("candidate_class_counts") or {}) >= 5,
        "class_label_matrix_present": bool(good_report.get("class_label_matrix")),
        "sparse_fixture_blocks_shadow": sparse_report.get("ready_for_shadow_scorer_training") is False
        and "enough_labeled_examples" in (sparse_report.get("promotion_blockers") or []),
        "report_only": good_report.get("report_only") is True
        and good_report.get("mutates_db") is False
        and good_report.get("mutates_runtime") is False
        and good_report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_label_quality_report_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "good_report": good_report,
        "sparse_report": sparse_report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Quality Report Regression",
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
