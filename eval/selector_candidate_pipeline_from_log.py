from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_LOG = REPO_ROOT / "experiments" / "memory_outcome_contract_workflow.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "selector_candidate_pipeline_from_log_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_candidate_pipeline_from_log_report.md"


def run_step(name: str, command: list[str], cwd: Path = ROOT) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
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
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def clean_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_artifact_paths(out_json: Path, out_md: Path) -> dict[str, str]:
    return {
        "pipeline_json": str(out_json),
        "pipeline_markdown": str(out_md),
        "retrieval_candidates_json": str(out_json.with_name(out_json.stem + "_retrieval_candidates.json")),
        "retrieval_candidates_markdown": str(out_md.with_name(out_md.stem + "_retrieval_candidates.md")),
        "evidence_candidates_json": str(out_json.with_name(out_json.stem + "_evidence_candidates.json")),
        "evidence_candidates_markdown": str(out_md.with_name(out_md.stem + "_evidence_candidates.md")),
        "architecture_gate_json": str(out_json.with_name(out_json.stem + "_architecture_gate.json")),
        "architecture_gate_markdown": str(out_md.with_name(out_md.stem + "_architecture_gate.md")),
    }


def build_report(log_path: Path, steps: list[dict[str, Any]], artifacts: dict[str, str]) -> dict[str, Any]:
    retrieval_candidates = read_json(Path(artifacts["retrieval_candidates_json"]))
    evidence_candidates = read_json(Path(artifacts["evidence_candidates_json"]))
    architecture_gate = read_json(Path(artifacts["architecture_gate_json"]))
    required_summary = {
        "log_exists": log_path.exists(),
        "retrieval_mining_ok": bool(retrieval_candidates and retrieval_candidates.get("schema") == "retrieval_signal_candidates/v1"),
        "evidence_mining_ok": bool(evidence_candidates and evidence_candidates.get("schema") == "evidence_state_candidates/v1"),
        "architecture_gate_ok": bool(architecture_gate and architecture_gate.get("ok")),
    }
    return {
        "ok": all(step["ok"] for step in steps) and all(required_summary.values()),
        "log_path": str(log_path),
        "required_summary": required_summary,
        "artifacts": artifacts,
        "retrieval_candidate_count": retrieval_candidates.get("candidate_count") if retrieval_candidates else None,
        "evidence_candidate_count": evidence_candidates.get("candidate_count") if evidence_candidates else None,
        "architecture_gate_summary": architecture_gate.get("required_summary") if architecture_gate else None,
        "steps": steps,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Candidate Pipeline From Log",
        "",
        f"Pipeline passed: **{report['ok']}**",
        f"Source log: `{report['log_path']}`",
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
            "## Candidate Counts",
            "",
            f"- Retrieval-signal candidate sections: `{report['retrieval_candidate_count']}`",
            f"- Evidence-state candidate sections: `{report['evidence_candidate_count']}`",
            "",
            "## Architecture Gate Summary",
            "",
            "```json",
            json.dumps(report["architecture_gate_summary"], indent=2),
            "```",
            "",
            "## Step Results",
            "",
            "| step | pass | return code | command |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for step in report["steps"]:
        command = " ".join(step["command"])
        lines.append(f"| `{step['name']}` | `{step['ok']}` | {step['returncode']} | `{clean_cell(command)}` |")
    lines.extend(["", "## Artifacts", ""])
    for label, path in report["artifacts"].items():
        lines.append(f"- `{label}`: `{path}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine selector candidates from an outcome log and run the unified selector architecture gate."
    )
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--min-support", type=int, default=1)
    parser.add_argument("--random-cases", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260520)
    args = parser.parse_args()

    log_path = Path(args.log)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifact_paths(out_json, out_md)
    python = sys.executable

    steps = [
        run_step(
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                str(ROOT / "eval" / "mine_retrieval_signal_candidates.py"),
                str(ROOT / "eval" / "mine_evidence_state_candidates.py"),
                str(ROOT / "eval" / "selector_architecture_gate.py"),
                str(ROOT / "eval" / "selector_candidate_pipeline_from_log.py"),
            ],
        )
    ]
    if not log_path.exists():
        steps.append(
            {
                "name": "log_exists",
                "ok": False,
                "returncode": 1,
                "command": ["check", str(log_path)],
                "stdout": "",
                "stderr": f"Log file does not exist: {log_path}",
                "parsed_stdout": None,
            }
        )
    else:
        steps.extend(
            [
                run_step(
                    "mine_retrieval_signal_candidates",
                    [
                        python,
                        str(ROOT / "eval" / "mine_retrieval_signal_candidates.py"),
                        "--log",
                        str(log_path),
                        "--min-support",
                        str(max(1, int(args.min_support))),
                        "--out-json",
                        artifacts["retrieval_candidates_json"],
                        "--out-md",
                        artifacts["retrieval_candidates_markdown"],
                    ],
                ),
                run_step(
                    "mine_evidence_state_candidates",
                    [
                        python,
                        str(ROOT / "eval" / "mine_evidence_state_candidates.py"),
                        "--log",
                        str(log_path),
                        "--min-support",
                        str(max(1, int(args.min_support))),
                        "--out-json",
                        artifacts["evidence_candidates_json"],
                        "--out-md",
                        artifacts["evidence_candidates_markdown"],
                    ],
                ),
                run_step(
                    "selector_architecture_gate",
                    [
                        python,
                        str(ROOT / "eval" / "selector_architecture_gate.py"),
                        "--retrieval-candidates",
                        artifacts["retrieval_candidates_json"],
                        "--evidence-candidates",
                        artifacts["evidence_candidates_json"],
                        "--allow-missing-candidates",
                        "--random-cases",
                        str(args.random_cases),
                        "--seed",
                        str(args.seed),
                        "--out-json",
                        artifacts["architecture_gate_json"],
                        "--out-md",
                        artifacts["architecture_gate_markdown"],
                    ],
                ),
            ]
        )

    report = build_report(log_path, steps, artifacts)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "required_summary": report["required_summary"],
                "retrieval_candidate_count": report["retrieval_candidate_count"],
                "evidence_candidate_count": report["evidence_candidate_count"],
                "json": str(out_json),
                "markdown": str(out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
