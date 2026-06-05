from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXPERIMENTS = REPO_ROOT / "experiments"
OUT_JSON = EXPERIMENTS / "architecture_preflight_results.json"
OUT_MD = EXPERIMENTS / "architecture_preflight_report.md"


def run_step(name: str, command: list[str], *, timeout_seconds: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return {
            "schema": "architecture_preflight_step/v1",
            "name": name,
            "ok": False,
            "returncode": None,
            "command": command,
            "stdout": stdout.strip(),
            "stderr": (stderr.strip() + f"\nTimed out after {timeout_seconds} seconds.").strip(),
            "timed_out": True,
        }
    return {
        "schema": "architecture_preflight_step/v1",
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "timed_out": False,
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_consistency_report(steps: list[dict[str, Any]], artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gate = artifacts.get("gate") or {}
    valuation = artifacts.get("valuation") or {}
    transition = artifacts.get("transition") or {}
    dashboard = artifacts.get("dashboard") or {}
    gate_summary = gate.get("required_summary") if isinstance(gate.get("required_summary"), dict) else {}
    checks = {
        "steps_ok": all(step.get("ok") is True for step in steps),
        "gate_ok": gate.get("ok") is True,
        "valuation_ok": valuation.get("ok") is True,
        "transition_ok": transition.get("ok") is True,
        "transition_state_stable": transition.get("transition_state") == "stable_report_only_learning_loop",
        "dashboard_handover_ready": dashboard.get("handover_ready") is True,
        "dashboard_upload_ready": dashboard.get("github_upload_ready") is True,
        "dashboard_transition_consistent": dashboard.get("transition_map_ok") is True,
        "gate_transition_key_ok": gate_summary.get("architecture_transition_map_ok") is True,
        "gate_reviewed_label_key_ok": gate_summary.get("memory_maintenance_rpg_reviewed_label_batch_ok") is True,
        "policy_not_promoted": (dashboard.get("policy_boundary") or {}).get("runtime_policy_mutation_allowed") is False
        and (dashboard.get("policy_boundary") or {}).get("real_db_mutation_allowed_by_default") is False
        and (dashboard.get("policy_boundary") or {}).get("rpg_policy_use_allowed") is False,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "schema": "architecture_preflight/v1",
        "description": "Ordered architecture preflight for valuation, gate, transition map, and readiness dashboard consistency.",
        "ok": not blockers,
        "checks": checks,
        "blockers": blockers,
        "step_count": len(steps),
        "steps": steps,
        "artifact_summary": {
            "gate_ok": gate.get("ok"),
            "valuation_ok": valuation.get("ok"),
            "transition_ok": transition.get("ok"),
            "transition_state": transition.get("transition_state"),
            "dashboard_handover_ready": dashboard.get("handover_ready"),
            "dashboard_upload_ready": dashboard.get("github_upload_ready"),
            "dashboard_transition_map_ok": dashboard.get("transition_map_ok"),
        },
        "recommended_next_development": "collect_reviewed_rpg_labels_and_recheck_label_quality"
        if not blockers
        else "fix_preflight_readiness_blockers",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Preflight",
        "",
        "Ordered preflight for architecture valuation, selector gate, transition map, and readiness dashboard consistency.",
        "",
        f"Passed: `{report['ok']}`",
        f"Recommended next development: `{report['recommended_next_development']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Steps", "", "| step | ok | timed out |", "| --- | --- | --- |"])
    for step in report.get("steps") or []:
        lines.append(f"| `{clean_cell(step.get('name'), 80)}` | `{step.get('ok')}` | `{step.get('timed_out')}` |")
    if report.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for blocker in report.get("blockers") or []:
            lines.append(f"- `{blocker}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    python = sys.executable
    steps = [
        run_step(
            "architecture_valuation_report_regression",
            [python, str(ROOT / "eval" / "architecture_valuation_report_regression.py")],
            timeout_seconds=120,
        ),
        run_step(
            "selector_architecture_gate",
            [
                python,
                str(ROOT / "eval" / "selector_architecture_gate.py"),
                "--allow-missing-runtime-artifacts",
                "--random-cases",
                str(args.random_cases),
            ],
            timeout_seconds=int(args.gate_timeout),
        ),
        run_step(
            "architecture_valuation_report",
            [python, str(ROOT / "eval" / "architecture_valuation_report.py")],
            timeout_seconds=120,
        ),
        run_step(
            "architecture_transition_map",
            [python, str(ROOT / "eval" / "architecture_transition_map.py")],
            timeout_seconds=120,
        ),
        run_step(
            "architecture_readiness_dashboard",
            [python, str(ROOT / "eval" / "architecture_readiness_dashboard.py")],
            timeout_seconds=120,
        ),
    ]
    artifacts = {
        "gate": read_json(EXPERIMENTS / "selector_architecture_gate_results.json"),
        "valuation": read_json(EXPERIMENTS / "architecture_valuation_report_results.json"),
        "transition": read_json(EXPERIMENTS / "architecture_transition_map_results.json"),
        "dashboard": read_json(EXPERIMENTS / "architecture_readiness_dashboard_results.json"),
    }
    return build_consistency_report(steps, artifacts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ordered architecture preflight and readiness consistency checks.")
    parser.add_argument("--random-cases", type=int, default=8)
    parser.add_argument("--gate-timeout", type=int, default=600)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = run_preflight(args)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "transition_state": report["artifact_summary"]["transition_state"],
                "dashboard_handover_ready": report["artifact_summary"]["dashboard_handover_ready"],
                "dashboard_transition_map_ok": report["artifact_summary"]["dashboard_transition_map_ok"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
