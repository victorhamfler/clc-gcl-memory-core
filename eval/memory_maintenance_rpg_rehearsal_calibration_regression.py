from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_rehearsal_calibration import calibrate_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_rehearsal_calibration_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_rehearsal_calibration_regression_report.md"


def cluster(
    key: str,
    readiness: str,
    *,
    relation: float,
    island: float,
    active_deprecated: float,
    duplicate_contradiction: float,
    risk_flags: dict[str, int] | None = None,
) -> dict:
    decision = key.split("|", 1)[1]
    safe = decision == "safe_to_review"
    return {
        "schema": "memory_maintenance_rehearsal_review_memory_bank_cluster/v1",
        "key": key,
        "run_count": 3,
        "runs": [1, 2, 3],
        "support": 3,
        "operation_kinds": {"duplicate_deprecation": 3},
        "decisions": {decision: 3},
        "blocked_count": 0 if safe else 3,
        "safe_count": 3 if safe else 0,
        "rpg_summary": {
            "schema": "memory_maintenance_rehearsal_rpg_cluster_summary/v1",
            "annotation_count": 3,
            "target_mean_relation_mean": relation,
            "target_mean_relation_min": relation - 0.02,
            "target_mean_relation_max": relation + 0.02,
            "target_island_ratio_mean": island,
            "sector_island_ratio_mean": island + 0.05,
            "omega_norm_mean": 0.002 if safe else 0.009,
            "target_sector_overlap_ratio_mean": 1.0,
            "duplicate_contradiction_overlap_mean": duplicate_contradiction,
            "active_deprecated_overlap_mean": active_deprecated,
            "risk_flags": risk_flags or {},
            "report_only": True,
            "mutates_db": False,
        },
        "readiness": readiness,
        "examples": [],
    }


def fixture_bank() -> dict:
    clusters = [
        cluster(
            "duplicate_deprecation|safe_to_review",
            "rehearsal_safe_evidence_ready",
            relation=0.86,
            island=1.42,
            active_deprecated=0.0,
            duplicate_contradiction=0.1,
        ),
        cluster(
            "duplicate_deprecation|blocked_stale_risk",
            "blocked_recurrent_risk",
            relation=0.34,
            island=0.72,
            active_deprecated=2.0,
            duplicate_contradiction=2.0,
            risk_flags={"stale_marker": 3, "duplicate_text_mismatch": 3},
        ),
        cluster(
            "duplicate_deprecation|blocked_bridge_risk",
            "blocked_recurrent_risk",
            relation=0.42,
            island=0.83,
            active_deprecated=1.4,
            duplicate_contradiction=1.7,
            risk_flags={"bridge_marker": 3},
        ),
        cluster(
            "duplicate_deprecation|blocked_semantic_risk",
            "blocked_recurrent_risk",
            relation=0.48,
            island=0.91,
            active_deprecated=0.5,
            duplicate_contradiction=1.2,
            risk_flags={"semantic_marker": 3},
        ),
    ]
    return {
        "schema": "memory_maintenance_rehearsal_review_memory_bank/v1",
        "run_count": 3,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def main() -> int:
    report = calibrate_bank(fixture_bank())
    safe = next(item for item in report["clusters"] if item["label"] == "safe")
    risks = [item for item in report["clusters"] if item["label"] != "safe"]
    checks = {
        "schema_ok": report.get("schema") == "memory_maintenance_rpg_rehearsal_calibration/v1",
        "mixed_clusters_present": report.get("cluster_count") == 4
        and report.get("label_counts") == {
            "bridge_risk": 1,
            "safe": 1,
            "semantic_risk": 1,
            "stale_risk": 1,
        },
        "safe_relation_higher": safe["target_mean_relation"] > max(item["target_mean_relation"] for item in risks),
        "safe_island_higher": safe["target_island_ratio"] > max(item["target_island_ratio"] for item in risks),
        "stale_bridge_overlap_higher_than_safe": report.get("stale_bridge_active_deprecated_overlap_mean", 0.0)
        > report.get("safe_active_deprecated_overlap_mean", 99.0),
        "probe_accuracy_perfect_on_fixture": report.get("prediction_accuracy") == 1.0,
        "not_ready_for_policy_use": report.get("ready_for_policy_use") is False
        and report.get("next_action") == "collect_more_real_rehearsal_runs_before_using_rpg_policy",
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_rehearsal_calibration_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "calibration": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Rehearsal Calibration Regression",
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
