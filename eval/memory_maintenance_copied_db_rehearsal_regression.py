from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_DIR = REPO_ROOT / "experiments"
WORK_DIR = Path("E:/projcod2_artifacts_archive/current_rehearsals/regression")
if not Path("E:/").exists():
    WORK_DIR = OUT_DIR / "memory_maintenance_copied_db_rehearsal_regression"
OUT_JSON = OUT_DIR / "memory_maintenance_copied_db_rehearsal_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_copied_db_rehearsal_regression_report.md"


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "eval" / "memory_maintenance_copied_db_rehearsal.py"),
            "--work-dir",
            str(WORK_DIR),
            "--operator-id",
            "copied_db_rehearsal_regression",
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    parsed = None
    if proc.stdout.strip():
        parsed = json.loads(proc.stdout[proc.stdout.rfind("{") :])
    report_path = Path((parsed or {}).get("json") or WORK_DIR / "memory_maintenance_copied_db_rehearsal_results.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    checks = {
        "command_exits_ok": proc.returncode == 0,
        "rehearsal_ok": report.get("ok") is True,
        "source_db_not_mutated": report.get("mutates_source_db") is False,
        "rows_unchanged": bool((report.get("checks") or {}).get("rows_unchanged")),
        "audit_written": bool((report.get("checks") or {}).get("audit_written")),
        "targets_present": bool((report.get("target_quality") or {}).get("all_targets_present")),
        "work_dir_preferably_off_c": str(WORK_DIR).lower().startswith("e:") if Path("E:/").exists() else True,
    }
    result = {
        "schema": "memory_maintenance_copied_db_rehearsal_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "rehearsal_report": report,
        "report_only": True,
        "mutates_source_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Copied DB Rehearsal Regression",
        "",
        f"Passed: **{result['ok']}**",
        f"Work dir: `{WORK_DIR}`",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD), "work_dir": str(WORK_DIR)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
