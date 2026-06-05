from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration_regression_report.md"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "memory_maintenance_rpg_copied_real_calibration.py")],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=300,
    )
    parsed = json.loads(proc.stdout[proc.stdout.rfind("{") :]) if proc.stdout.strip() else {}
    report_path = Path(parsed.get("json") or REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration_results.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    calibration = report.get("calibration") or {}
    checks = {
        "command_ok": proc.returncode == 0 and parsed.get("ok") is True,
        "schema_ok": report.get("schema") == "memory_maintenance_rpg_copied_real_calibration/v1",
        "at_least_two_runs": (report.get("checks") or {}).get("at_least_two_runs") is True,
        "rpg_annotations_available": (report.get("checks") or {}).get("rpg_annotations_available") is True,
        "safe_relation_exceeds_blocked": (report.get("checks") or {}).get("safe_relation_exceeds_blocked") is True
        and float(calibration.get("safe_relation_mean") or 0.0) > float(calibration.get("blocked_relation_mean") or 0.0),
        "calibration_not_policy_ready": calibration.get("ready_for_policy_use") is False,
        "source_dbs_not_mutated": report.get("mutates_source_db") is False,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_copied_real_calibration_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "copied_real_report": report,
        "report_only": True,
        "mutates_source_db": False,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Copied-Real Calibration Regression",
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
