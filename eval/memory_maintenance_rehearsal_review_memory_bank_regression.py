from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rehearsal_review_memory_bank import build_memory_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
FIXTURE_DIR = OUT_DIR / "memory_maintenance_rehearsal_review_memory_bank_fixture"
OUT_JSON = OUT_DIR / "memory_maintenance_rehearsal_review_memory_bank_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rehearsal_review_memory_bank_regression_report.md"


def review(candidate_id: str, decision: str, operation_kind: str = "duplicate_deprecation") -> dict:
    return {
        "schema": "memory_maintenance_rehearsal_operation_review/v1",
        "candidate_id": candidate_id,
        "operation_kind": operation_kind,
        "decision": decision,
        "reasons": ["fixture"],
        "risk_flags": ["stale_marker"] if decision == "blocked_stale_risk" else [],
        "target_ids": ["keep", "target"],
        "missing_ids": [],
        "operator_next_action": "operator_must_resolve_blockers_before_apply"
        if decision.startswith("blocked_")
        else "operator_may_review_duplicate_deprecation",
        "mutation_allowed": False,
    }


def write_fixture_run(path: Path, *, run_name: str) -> None:
    report = {
        "schema": "memory_maintenance_copied_db_rehearsal/v1",
        "source_db": f"{run_name}.db",
        "review_summary": {
            "schema": "memory_maintenance_rehearsal_review_summary/v1",
            "operation_review_count": 2,
            "decision_counts": {
                "blocked_stale_risk": 1,
                "safe_to_review": 1,
            },
            "safe_to_review_count": 1,
            "blocked_count": 1,
            "needs_operator_review_count": 0,
            "overall_decision": "blocked_or_needs_review",
            "reviews": [
                review("family:exact_duplicate:alpha", "safe_to_review"),
                review("family:stale_risk:beta", "blocked_stale_risk"),
            ],
            "mutation_allowed": False,
            "report_only": True,
        },
        "rpg_rehearsal_annotations": {
            "schema": "memory_maintenance_rpg_rehearsal_annotations/v1",
            "available": True,
            "record_count": 6,
            "max_island_ratio": 1.4,
            "max_omega_norm": 0.01,
            "operation_annotations": [
                {
                    "schema": "memory_maintenance_rpg_operation_annotation/v1",
                    "candidate_id": "family:exact_duplicate:alpha",
                    "operation_kind": "duplicate_deprecation",
                    "target_ids": ["keep", "target"],
                    "target_island_ratio": 1.35,
                    "target_mean_relation": 0.82,
                    "target_sector_overlap": 2,
                    "target_count": 2,
                    "island_ratio": 1.4,
                    "omega_norm": 0.002,
                    "duplicate_contradiction_sector_overlap": 2,
                    "active_deprecated_sector_overlap": 0,
                    "risk_flags": [],
                    "exact_duplicate_target": True,
                    "report_only": True,
                    "mutates_db": False,
                },
                {
                    "schema": "memory_maintenance_rpg_operation_annotation/v1",
                    "candidate_id": "family:stale_risk:beta",
                    "operation_kind": "duplicate_deprecation",
                    "target_ids": ["keep", "target"],
                    "target_island_ratio": 0.75,
                    "target_mean_relation": 0.31,
                    "target_sector_overlap": 2,
                    "target_count": 2,
                    "island_ratio": 0.9,
                    "omega_norm": 0.004,
                    "duplicate_contradiction_sector_overlap": 2,
                    "active_deprecated_sector_overlap": 2,
                    "risk_flags": ["stale_marker", "duplicate_text_mismatch"],
                    "exact_duplicate_target": False,
                    "report_only": True,
                    "mutates_db": False,
                },
            ],
            "report_only": True,
            "mutates_db": False,
            "mutates_runtime": False,
            "mutates_config": False,
        },
        "mutates_source_db": False,
        "report_only": True,
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    run1 = FIXTURE_DIR / "run1.json"
    run2 = FIXTURE_DIR / "run2.json"
    write_fixture_run(run1, run_name="run1")
    write_fixture_run(run2, run_name="run2")
    bank = build_memory_bank([run1, run2], min_runs=2, min_safe=2)
    clusters = {item.get("key"): item for item in bank.get("clusters") or []}
    safe = clusters.get("duplicate_deprecation|safe_to_review") or {}
    stale = clusters.get("duplicate_deprecation|blocked_stale_risk") or {}
    safe_rpg = safe.get("rpg_summary") or {}
    stale_rpg = stale.get("rpg_summary") or {}
    checks = {
        "schema_ok": bank.get("schema") == "memory_maintenance_rehearsal_review_memory_bank/v1",
        "two_runs": bank.get("run_count") == 2,
        "safe_cluster_ready": safe.get("readiness") == "rehearsal_safe_evidence_ready"
        and safe.get("support") == 2
        and safe.get("safe_count") == 2,
        "stale_cluster_recurrent_risk": stale.get("readiness") == "blocked_recurrent_risk"
        and stale.get("support") == 2
        and stale.get("blocked_count") == 2,
        "rpg_summaries_present": bank.get("rpg_cluster_summary_count") == 2
        and safe_rpg.get("annotation_count") == 2
        and stale_rpg.get("annotation_count") == 2,
        "rpg_safe_relation_stronger_than_stale": float(safe_rpg.get("target_mean_relation_mean") or 0.0)
        > float(stale_rpg.get("target_mean_relation_mean") or 0.0),
        "rpg_stale_risk_flags_preserved": (stale_rpg.get("risk_flags") or {}).get("stale_marker") == 2
        and (stale_rpg.get("risk_flags") or {}).get("duplicate_text_mismatch") == 2,
        "counts_ok": bank.get("safe_evidence_ready_count") == 1 and bank.get("recurrent_risk_count") == 1,
        "next_action_blocks_due_to_risk": bank.get("next_action") == "review_or_collect_more_copied_db_rehearsals",
        "report_only": bank.get("report_only") is True
        and bank.get("mutates_db") is False
        and bank.get("mutates_runtime") is False
        and bank.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rehearsal_review_memory_bank_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "memory_bank": bank,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rehearsal Review Memory Bank Regression",
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
