from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidate_gate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_candidate_gate_report.md"


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "parsed_stdout": parse_last_json(proc.stdout),
    }


def parse_last_json(text: str) -> Any:
    text = str(text or "").strip()
    if not text:
        return None
    starts = [idx for idx, char in enumerate(text) if char in "[{"]
    for idx in reversed(starts):
        try:
            return json.loads(text[idx:])
        except json.JSONDecodeError:
            continue
    return None


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def clean_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_report(steps: list[dict[str, Any]], dry_run_path: Path | None) -> dict[str, Any]:
    dry_run = read_json(dry_run_path) if dry_run_path else None
    required_summary = {
        "py_compile_ok": bool(steps and steps[0]["ok"]),
        "regression_ok": any(step["name"] == "ogcf_maintenance_candidates_regression" and step["ok"] for step in steps),
        "dry_run_schema_ok": bool(not dry_run_path or (dry_run and dry_run.get("schema") == "ogcf_maintenance_candidates/v1")),
        "dry_run_no_mutation_contract": bool(not dry_run_path or (dry_run and dry_run.get("mutates_db") is False)),
    }
    return {
        "ok": all(step["ok"] for step in steps) and all(required_summary.values()),
        "required_summary": required_summary,
        "dry_run_candidate_count": dry_run.get("candidate_count") if dry_run else None,
        "dry_run_candidate_counts": dry_run.get("candidate_counts") if dry_run else None,
        "dry_run_geometry_summary": dry_run.get("geometry_summary") if dry_run else None,
        "dry_run_artifact": str(dry_run_path) if dry_run_path else None,
        "steps": steps,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# OGCF Maintenance Candidate Gate",
        "",
        f"Gate passed: **{report['ok']}**",
        "",
        "## Required Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["required_summary"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Dry-Run Summary",
            "",
            f"- Candidate count: `{report['dry_run_candidate_count']}`",
            "",
            "```json",
            json.dumps(report["dry_run_candidate_counts"], indent=2),
            "```",
            "",
            "## Geometry Summary",
            "",
            "```json",
            json.dumps(report["dry_run_geometry_summary"], indent=2),
            "```",
            "",
            "## Steps",
            "",
            "| step | pass | return code | command |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for step in report["steps"]:
        lines.append(
            f"| `{step['name']}` | `{step['ok']}` | {step['returncode']} | `{clean_cell(' '.join(step['command']))}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate OGCF maintenance candidate dry-run tooling.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--n-clusters", type=int, default=30)
    parser.add_argument("--random-baselines", type=int, default=5)
    parser.add_argument("--skip-real-db", action="store_true")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    python = sys.executable
    dry_run_json = Path(args.out_json).with_name(Path(args.out_json).stem + "_dry_run.json")
    dry_run_md = Path(args.out_md).with_name(Path(args.out_md).stem + "_dry_run.md")
    steps = [
        run_step(
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                str(ROOT / "core" / "ogcf_geometry.py"),
                str(ROOT / "eval" / "ogcf_maintenance_candidates.py"),
                str(ROOT / "eval" / "ogcf_maintenance_candidates_regression.py"),
                str(ROOT / "eval" / "ogcf_maintenance_candidate_gate.py"),
            ],
        ),
        run_step(
            "ogcf_maintenance_candidates_regression",
            [python, str(ROOT / "eval" / "ogcf_maintenance_candidates_regression.py")],
        ),
    ]

    dry_run_path: Path | None = None
    db_path = Path(args.db)
    if not args.skip_real_db and db_path.exists():
        dry_run_path = dry_run_json
        steps.append(
            run_step(
                "ogcf_maintenance_candidates_real_dry_run",
                [
                    python,
                    str(ROOT / "eval" / "ogcf_maintenance_candidates.py"),
                    "--db",
                    str(db_path),
                    "--limit",
                    str(max(1, int(args.limit))),
                    "--n-clusters",
                    str(max(2, int(args.n_clusters))),
                    "--random-baselines",
                    str(max(1, int(args.random_baselines))),
                    "--out-json",
                    str(dry_run_json),
                    "--out-md",
                    str(dry_run_md),
                ],
            )
        )
    elif not args.skip_real_db:
        steps.append(
            {
                "name": "real_db_exists",
                "ok": False,
                "returncode": 1,
                "command": ["check", str(db_path)],
                "stdout": "",
                "stderr": f"DB does not exist: {db_path}",
                "parsed_stdout": None,
            }
        )

    report = build_report(steps, dry_run_path)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "required_summary": report["required_summary"],
                "dry_run_candidate_count": report["dry_run_candidate_count"],
                "dry_run_candidate_counts": report["dry_run_candidate_counts"],
                "json": str(out_json),
                "markdown": str(out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
