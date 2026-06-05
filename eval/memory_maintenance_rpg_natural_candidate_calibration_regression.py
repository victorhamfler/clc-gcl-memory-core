from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_regression_report.md"


def parse_last_json(text: str) -> dict:
    text = str(text or "").strip()
    for index, char in reversed(list(enumerate(text))):
        if char != "{":
            continue
        try:
            value = json.loads(text[index:])
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else {}
    return {}


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "memory_maintenance_rpg_natural_candidate_calibration.py")],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=300,
    )
    parsed = parse_last_json(proc.stdout)
    report_path = Path(parsed.get("json") or REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_results.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    summary = report.get("candidate_class_summary") or {}
    checks = {
        "command_ok": proc.returncode == 0 and parsed.get("ok") is True,
        "schema_ok": report.get("schema") == "memory_maintenance_rpg_natural_candidate_calibration/v1",
        "natural_pairs_found": int(report.get("all_pair_count") or 0) > 0,
        "near_duplicate_like_found": int((summary.get("near_duplicate_like") or {}).get("count") or 0) > 0,
        "risk_or_bridge_class_found": any(
            int((summary.get(label) or {}).get("count") or 0) > 0
            for label in ("stale_or_update_like", "bridge_like", "cross_domain_related")
        ),
        "rpg_metrics_nonzero": any(
            float((item or {}).get("relation_mean") or 0.0) > 0.0
            and float((item or {}).get("island_mean") or 0.0) > 0.0
            for item in summary.values()
        ),
        "not_policy_ready": report.get("ready_for_policy_use") is False,
        "source_dbs_not_mutated": report.get("mutates_source_db") is False,
        "report_only": report.get("report_only") is True
        and report.get("mutates_db") is False
        and report.get("mutates_runtime") is False
        and report.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_natural_candidate_calibration_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "natural_candidate_report": report,
        "report_only": True,
        "mutates_source_db": False,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Natural Candidate Calibration Regression",
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
