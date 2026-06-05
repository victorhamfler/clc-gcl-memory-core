from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.architecture_transition_map import SUBSYSTEMS, build_transition_map  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "architecture_transition_map_regression_results.json"
OUT_MD = OUT_DIR / "architecture_transition_map_regression_report.md"


def gate_fixture() -> dict:
    summary = {}
    for subsystem in SUBSYSTEMS:
        for key in subsystem["gate_keys"]:
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


def dashboard_fixture() -> dict:
    return {
        "schema": "architecture_readiness_dashboard/v1",
        "handover_ready": True,
        "github_upload_ready": True,
        "report_only": True,
    }


def merge_fixture(*, policy_ready: bool = False) -> dict:
    return {
        "schema": "memory_maintenance_rpg_feedback_merge_evaluation_regression/v1",
        "ok": True,
        "evaluation": {
            "schema": "memory_maintenance_rpg_feedback_merge_evaluation/v1",
            "comparison": {
                "label_gain_from_operator_feedback": 2,
                "operator_feedback_materially_improves_training_evidence": True,
            },
            "combined": {
                "summary": {
                    "labeled_count": 8,
                    "quality_ready_for_shadow": False,
                    "scorer_ready_for_shadow": True,
                    "scorer_ready_for_policy": policy_ready,
                }
            },
        },
    }


def main() -> int:
    good = build_transition_map(gate_fixture(), valuation_fixture(), dashboard_fixture(), merge_fixture())
    blocked_gate = gate_fixture()
    blocked_gate["required_summary"]["memory_maintenance_operator_outcome_capture_ok"] = False
    blocked = build_transition_map(blocked_gate, valuation_fixture(), dashboard_fixture(), merge_fixture())
    policy_ready = build_transition_map(gate_fixture(), valuation_fixture(), dashboard_fixture(), merge_fixture(policy_ready=True))
    checks = {
        "schema_ok": good.get("schema") == "architecture_transition_map/v1",
        "stable_loop_ok": good.get("ok") is True
        and good.get("transition_state") == "stable_report_only_learning_loop",
        "policy_boundary_blocks_mutation": (good.get("policy_readiness") or {}).get("runtime_policy_mutation_allowed")
        is False
        and (good.get("policy_readiness") or {}).get("real_db_mutation_allowed_by_default") is False
        and (good.get("policy_readiness") or {}).get("rpg_policy_use_allowed") is False,
        "operator_blocker_detected": blocked.get("ok") is False
        and "operator_feedback_loop" in (blocked.get("blocked_subsystems") or []),
        "unexpected_policy_ready_blocks": policy_ready.get("ok") is False
        and "unexpected_rpg_policy_ready_signal" in (policy_ready.get("hard_blockers") or []),
        "merge_evidence_present": (good.get("merge_evidence") or {}).get("combined_labeled_count") == 8,
        "report_only": good.get("report_only") is True
        and good.get("mutates_db") is False
        and good.get("mutates_runtime") is False
        and good.get("mutates_config") is False,
    }
    result = {
        "schema": "architecture_transition_map_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "good_transition_map": good,
        "blocked_transition_map": blocked,
        "policy_ready_transition_map": policy_ready,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Transition Map Regression",
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
