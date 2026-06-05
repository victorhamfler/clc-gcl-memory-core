from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.architecture_preflight import build_consistency_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "architecture_preflight_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "architecture_preflight_regression_report.md"


def steps_fixture(ok: bool = True) -> list[dict]:
    return [
        {"name": "architecture_valuation_report_regression", "ok": ok, "timed_out": False},
        {"name": "selector_architecture_gate", "ok": ok, "timed_out": False},
        {"name": "architecture_valuation_report", "ok": ok, "timed_out": False},
        {"name": "architecture_transition_map", "ok": ok, "timed_out": False},
        {"name": "architecture_readiness_dashboard", "ok": ok, "timed_out": False},
    ]


def artifacts_fixture(*, transition_ok: bool = True, dashboard_transition_ok: bool = True) -> dict:
    return {
        "gate": {
            "schema": "selector_architecture_gate/v1",
            "ok": True,
            "required_summary": {
                "architecture_transition_map_ok": True,
                "memory_maintenance_rpg_reviewed_label_batch_ok": True,
            },
        },
        "valuation": {"schema": "architecture_valuation_report/v1", "ok": True},
        "transition": {
            "schema": "architecture_transition_map/v1",
            "ok": transition_ok,
            "transition_state": "stable_report_only_learning_loop",
        },
        "dashboard": {
            "schema": "architecture_readiness_dashboard/v1",
            "handover_ready": True,
            "github_upload_ready": True,
            "transition_map_ok": dashboard_transition_ok,
            "policy_boundary": {
                "runtime_policy_mutation_allowed": False,
                "real_db_mutation_allowed_by_default": False,
                "rpg_policy_use_allowed": False,
            },
        },
    }


def main() -> int:
    good = build_consistency_report(steps_fixture(), artifacts_fixture())
    transition_bad = build_consistency_report(steps_fixture(), artifacts_fixture(transition_ok=False))
    dashboard_bad = build_consistency_report(steps_fixture(), artifacts_fixture(dashboard_transition_ok=False))
    step_bad = build_consistency_report(steps_fixture(ok=False), artifacts_fixture())
    checks = {
        "good_preflight_passes": good.get("ok") is True,
        "transition_false_blocks": transition_bad.get("ok") is False
        and "transition_ok" in (transition_bad.get("blockers") or []),
        "dashboard_transition_false_blocks": dashboard_bad.get("ok") is False
        and "dashboard_transition_consistent" in (dashboard_bad.get("blockers") or []),
        "step_failure_blocks": step_bad.get("ok") is False and "steps_ok" in (step_bad.get("blockers") or []),
        "report_only": good.get("report_only") is True
        and good.get("mutates_db") is False
        and good.get("mutates_runtime") is False
        and good.get("mutates_config") is False,
    }
    result = {
        "schema": "architecture_preflight_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "good_preflight": good,
        "transition_bad_preflight": transition_bad,
        "dashboard_bad_preflight": dashboard_bad,
        "step_bad_preflight": step_bad,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Preflight Regression",
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
