from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.architecture_readiness_dashboard import CHAINS, build_dashboard  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "architecture_readiness_dashboard_regression_results.json"
OUT_MD = OUT_DIR / "architecture_readiness_dashboard_regression_report.md"


def gate_fixture() -> dict:
    summary = {}
    for chain in CHAINS:
        for key in chain["keys"]:
            summary[key] = True
    return {
        "schema": "selector_architecture_gate/v1",
        "ok": True,
        "required_summary": summary,
    }


def valuation_fixture() -> dict:
    return {
        "schema": "architecture_valuation_report/v1",
        "ok": True,
        "policy_boundary": {
            "runtime_policy_mutation_allowed": False,
            "real_db_mutation_allowed_by_default": False,
            "rpg_policy_use_allowed": False,
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def merge_fixture() -> dict:
    return {
        "schema": "memory_maintenance_rpg_feedback_merge_evaluation_regression/v1",
        "ok": True,
        "evaluation": {
            "schema": "memory_maintenance_rpg_feedback_merge_evaluation/v1",
            "comparison": {
                "label_gain_from_operator_feedback": 2,
                "operator_feedback_materially_improves_training_evidence": True,
                "family_prediction_accuracy_delta": 0.1,
                "scorer_leave_one_out_accuracy_delta": 0.0,
            },
            "combined": {
                "summary": {
                    "labeled_count": 8,
                    "quality_ready_for_shadow": False,
                    "scorer_ready_for_shadow": False,
                    "scorer_ready_for_policy": False,
                }
            },
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def transition_fixture() -> dict:
    return {
        "schema": "architecture_transition_map/v1",
        "ok": True,
        "transition_state": "stable_report_only_learning_loop",
        "blocked_subsystems": [],
        "recommended_next_development": "collect_reviewed_rpg_labels_and_recheck_label_quality",
        "report_only": True,
    }


def main() -> int:
    good = build_dashboard(gate_fixture(), valuation_fixture(), merge_fixture(), transition_fixture())
    bad_gate = gate_fixture()
    bad_gate["required_summary"]["memory_maintenance_operator_outcome_capture_ok"] = False
    blocked = build_dashboard(bad_gate, valuation_fixture(), merge_fixture(), transition_fixture())
    checks = {
        "schema_ok": good.get("schema") == "architecture_readiness_dashboard/v1",
        "all_chains_ready": good.get("chains_ok") is True
        and good.get("handover_ready") is True
        and good.get("github_upload_ready") is True,
        "policy_boundary_blocks_mutation": (good.get("policy_boundary") or {}).get("runtime_policy_mutation_allowed")
        is False
        and (good.get("policy_boundary") or {}).get("real_db_mutation_allowed_by_default") is False
        and (good.get("policy_boundary") or {}).get("rpg_policy_use_allowed") is False,
        "merge_summary_present": (good.get("merge_evaluation") or {}).get("label_gain_from_operator_feedback") == 2
        and (good.get("merge_evaluation") or {}).get("combined_scorer_ready_for_policy") is False,
        "transition_summary_present": (good.get("transition_map") or {}).get("transition_state")
        == "stable_report_only_learning_loop"
        and good.get("recommended_next_development") == "collect_reviewed_rpg_labels_and_recheck_label_quality",
        "blocked_fixture_not_handover_ready": blocked.get("handover_ready") is False
        and blocked.get("chains_ok") is False,
        "blocked_chain_names_failure": any(
            chain.get("name") == "operator_feedback" and not chain.get("ok")
            for chain in blocked.get("chains") or []
        ),
        "report_only": good.get("report_only") is True
        and good.get("mutates_db") is False
        and good.get("mutates_runtime") is False
        and good.get("mutates_config") is False,
    }
    result = {
        "schema": "architecture_readiness_dashboard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "good_dashboard": good,
        "blocked_dashboard": blocked,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Readiness Dashboard Regression",
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
