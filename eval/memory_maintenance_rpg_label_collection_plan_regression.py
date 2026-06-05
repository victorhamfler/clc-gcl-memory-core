from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_label_collection_plan import build_plan  # noqa: E402
from eval.memory_maintenance_rpg_natural_candidate_review_packet import LABEL_OPTIONS  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_regression_report.md"


def item(index: int, klass: str, label: str = "") -> dict:
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_review_item/v1",
        "id": f"collection_fixture:{index}:{klass}",
        "candidate_class": klass,
        "source_db": "fixture.db",
        "left_memory_id": f"left_{index}",
        "right_memory_id": f"right_{index}",
        "left_domain": "a",
        "right_domain": "b" if klass == "cross_domain_related" else "a",
        "same_domain": klass != "cross_domain_related",
        "cosine": 0.8,
        "jaccard": 0.2,
        "rpg_target_relation": round(0.2 + index * 0.01, 6),
        "rpg_target_island_ratio": round(1.0 + index * 0.01, 6),
        "left_preview": "left fixture",
        "right_preview": "right fixture",
        "review_hint": f"review_{klass}",
        "allowed_labels": LABEL_OPTIONS,
        "review_label": label,
        "reviewer": "regression" if label else "",
        "review_notes": "fixture" if label else "",
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
    }


def sparse_packet() -> dict:
    rows = [
        item(1, "near_duplicate_like", "safe_duplicate"),
        item(2, "near_duplicate_like", "safe_duplicate"),
        item(3, "stale_or_update_like", "stale_or_update_conflict"),
        item(4, "bridge_like", "bridge_contamination"),
        item(5, "cross_domain_related"),
        item(6, "cross_domain_related"),
        item(7, "bridge_like"),
        item(8, "stale_or_update_like"),
        item(9, "near_duplicate_like"),
        item(10, "exact_duplicate"),
        item(11, "unknown"),
        item(12, "bridge_like"),
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


def ready_packet() -> dict:
    labels = [
        "safe_duplicate",
        "safe_duplicate",
        "safe_duplicate",
        "stale_or_update_conflict",
        "stale_or_update_conflict",
        "bridge_contamination",
        "bridge_contamination",
        "harmless_related_memory",
        "harmless_related_memory",
        "semantic_near_duplicate",
        "uncertain_needs_more_context",
        "uncertain_needs_more_context",
    ]
    classes = [
        "near_duplicate_like",
        "exact_duplicate",
        "near_duplicate_like",
        "stale_or_update_like",
        "stale_or_update_like",
        "bridge_like",
        "bridge_like",
        "cross_domain_related",
        "cross_domain_related",
        "near_duplicate_like",
        "unknown",
        "bridge_like",
    ]
    packet = sparse_packet()
    packet["items"] = [item(index, klass, label) for index, (klass, label) in enumerate(zip(classes, labels), start=1)]
    return packet


def main() -> int:
    sparse = build_plan(sparse_packet(), target_labels=12, max_review_items=8)
    ready = build_plan(ready_packet(), target_labels=12, max_review_items=8)
    target_classes = {item.get("candidate_class") for item in sparse.get("recommended_review_targets") or []}
    checks = {
        "schema_ok": sparse.get("schema") == "memory_maintenance_rpg_label_collection_plan/v1",
        "sparse_blocks_quality_eval": sparse.get("ready_for_label_quality_eval") is False
        and sparse.get("deficits", {}).get("labeled_examples") == 8,
        "sparse_recommends_unlabeled_targets": sparse.get("recommended_review_target_count") > 0
        and "cross_domain_related" in target_classes,
        "ready_packet_passes_collection_plan": ready.get("ready_for_label_quality_eval") is True
        and ready.get("recommended_review_target_count") == 0,
        "policy_still_blocked": ready.get("ready_for_policy_use") is False
        and ready.get("promotion_ready") is False,
        "report_only": sparse.get("report_only") is True
        and sparse.get("mutates_db") is False
        and sparse.get("mutates_runtime") is False
        and sparse.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_label_collection_plan_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "sparse_plan": sparse,
        "ready_plan": ready,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Label Collection Plan Regression",
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
