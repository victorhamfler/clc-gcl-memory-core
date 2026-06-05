from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_JSON = REPO_ROOT / "experiments" / "architecture_valuation_report_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "architecture_valuation_report_regression_report.md"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "architecture_valuation_report.py")],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    report_path = REPO_ROOT / "experiments" / "architecture_valuation_report_results.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    phase_names = {item.get("phase") for item in report.get("phases") or []}
    checks = {
        "command_ok": proc.returncode == 0,
        "schema_ok": report.get("schema") == "architecture_valuation_report/v1",
        "phase_coverage": {
            "retrieval_and_controller_context",
            "maintenance_apply_lifecycle",
            "rpg_relational_substrate",
            "rpg_supervised_learning_path",
        }.issubset(phase_names),
        "policy_boundaries_block_mutation": (report.get("policy_boundary") or {}).get("runtime_policy_mutation_allowed")
        is False
        and (report.get("policy_boundary") or {}).get("real_db_mutation_allowed_by_default") is False
        and (report.get("policy_boundary") or {}).get("rpg_policy_use_allowed") is False,
        "rpg_scorer_not_policy_ready": (report.get("readiness") or {}).get("rpg_scorer_ready_for_policy") is False,
        "next_steps_present": len(report.get("recommended_next_steps") or []) >= 3,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "architecture_valuation_report_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "valuation": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Valuation Report Regression",
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
