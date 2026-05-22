from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_CANDIDATES = ROOT / "test_corpora" / "retrieval_signal_candidates_v1.json"
OUT_JSON = REPO_ROOT / "experiments" / "retrieval_signal_promotion_gate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "retrieval_signal_promotion_gate_report.md"


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


def parsed_step(steps: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for step in steps:
        if step.get("name") == name and isinstance(step.get("parsed_stdout"), dict):
            return step["parsed_stdout"]
    return None


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_report(args: argparse.Namespace, steps: list[dict[str, Any]], artifacts: dict[str, str]) -> dict[str, Any]:
    candidate_report = read_json(Path(artifacts["candidate_json"]))
    module_smoke = read_json(REPO_ROOT / "experiments" / "retrieval_signals_module_smoke_results.json")
    miner_regression = read_json(REPO_ROOT / "experiments" / "retrieval_signal_miner_regression_results.json")
    nested_config = read_json(REPO_ROOT / "experiments" / "config_nested_parser_regression_results.json")
    claim_scope_gate = read_json(REPO_ROOT / "experiments" / "claim_scope_promotion_gate_results.json")
    randomized = read_json(REPO_ROOT / "experiments" / "selector_retrieval_guard_randomized_eval_seed20260520_n64_results.json")
    policy_deflection = read_json(REPO_ROOT / "experiments" / "policy_correction_deflection_regression_results.json")
    answer_quality = read_json(REPO_ROOT / "experiments" / "answer_quality_eval_results.json") or parsed_step(
        steps,
        "answer_quality",
    )

    required_summary = {
        "candidate_eval_ok": bool(candidate_report and candidate_report.get("ok")),
        "module_smoke_ok": bool(module_smoke and module_smoke.get("ok")),
        "miner_regression_ok": bool(miner_regression and miner_regression.get("ok")),
        "nested_config_ok": bool(nested_config and nested_config.get("ok")),
        "claim_scope_gate_ok": bool(claim_scope_gate and claim_scope_gate.get("ok")),
        "randomized_guard_ok": bool(randomized and randomized.get("ok")),
        "policy_deflection_ok": bool(policy_deflection and policy_deflection.get("ok")),
        "answer_quality_ok": bool(answer_quality and answer_quality.get("ok")),
    }
    gate_ok = all(step["ok"] for step in steps) and all(required_summary.values())
    return {
        "ok": gate_ok,
        "candidate_path": str(Path(args.candidates).resolve()),
        "required_summary": required_summary,
        "artifacts": artifacts,
        "steps": steps,
        "candidate_eval": {
            "ok": candidate_report.get("ok") if candidate_report else None,
            "check_count": candidate_report.get("check_count") if candidate_report else None,
            "validation_failures": candidate_report.get("validation_failures") if candidate_report else None,
            "failures": candidate_report.get("failures") if candidate_report else None,
        },
        "module_smoke": {
            "ok": module_smoke.get("ok") if module_smoke else None,
            "check_count": len(module_smoke.get("checks") or []) if module_smoke else None,
        },
        "miner_regression": {
            "ok": miner_regression.get("ok") if miner_regression else None,
            "checks": miner_regression.get("checks") if miner_regression else None,
        },
        "claim_scope_gate": {
            "ok": claim_scope_gate.get("ok") if claim_scope_gate else None,
            "required_summary": claim_scope_gate.get("required_summary") if claim_scope_gate else None,
        },
        "randomized_guard": {
            "ok": randomized.get("ok") if randomized else None,
            "alignment_rate": randomized.get("alignment_rate") if randomized else None,
            "aligned_cases": randomized.get("aligned_cases") if randomized else None,
            "case_count": randomized.get("case_count") if randomized else None,
        },
        "policy_deflection": {
            "ok": policy_deflection.get("ok") if policy_deflection else None,
            "case_count": policy_deflection.get("case_count") if policy_deflection else None,
        },
        "answer_quality": {
            "ok": answer_quality.get("ok") if answer_quality else None,
            "mean_score": answer_quality.get("mean_score") if answer_quality else None,
        },
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Retrieval Signal Promotion Gate",
        "",
        f"Promotion ready: **{report['ok']}**",
        f"Candidate file: `{report['candidate_path']}`",
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
            "## Candidate Eval",
            "",
            f"- Passed: `{report['candidate_eval']['ok']}`",
            f"- Checks: `{report['candidate_eval']['check_count']}`",
            f"- Validation failures: `{', '.join(report['candidate_eval']['validation_failures'] or []) or 'none'}`",
            f"- Check failures: `{', '.join(report['candidate_eval']['failures'] or []) or 'none'}`",
            "",
            "## Miner Regression",
            "",
            f"- Passed: `{report['miner_regression']['ok']}`",
            f"- Checks: `{json.dumps(report['miner_regression']['checks'], sort_keys=True)}`",
            "",
            "## Behavior Gates",
            "",
            f"- Claim-scope gate: `{report['claim_scope_gate']['ok']}`",
            f"- Randomized guard: `{report['randomized_guard']['ok']}` "
            f"({report['randomized_guard']['aligned_cases']}/{report['randomized_guard']['case_count']})",
            f"- Policy deflection: `{report['policy_deflection']['ok']}`",
            f"- Answer quality: `{report['answer_quality']['ok']}`, mean `{report['answer_quality']['mean_score']}`",
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
    parser = argparse.ArgumentParser(description="Run the retrieval-signal promotion gate.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--random-cases", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260520)
    args = parser.parse_args()

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    candidate_json = out_json.with_name(out_json.stem + "_candidate_eval.json")
    candidate_md = out_md.with_name(out_md.stem + "_candidate_eval.md")
    artifacts = {
        "gate_json": str(out_json),
        "gate_markdown": str(out_md),
        "candidate_json": str(candidate_json),
        "candidate_markdown": str(candidate_md),
    }

    python = sys.executable
    steps = [
        run_step(
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                str(ROOT / "core" / "retrieval_signals.py"),
                str(ROOT / "core" / "pipeline.py"),
                str(ROOT / "core" / "runtime.py"),
                str(ROOT / "eval" / "retrieval_signal_candidate_eval.py"),
                str(ROOT / "eval" / "mine_retrieval_signal_candidates.py"),
                str(ROOT / "eval" / "retrieval_signal_miner_regression.py"),
                str(ROOT / "eval" / "retrieval_signals_module_smoke.py"),
                str(ROOT / "eval" / "policy_correction_deflection_regression.py"),
            ],
        ),
        run_step(
            "candidate_eval",
            [
                python,
                str(ROOT / "eval" / "retrieval_signal_candidate_eval.py"),
                "--candidates",
                str(Path(args.candidates)),
                "--out-json",
                str(candidate_json),
                "--out-md",
                str(candidate_md),
            ],
        ),
        run_step("module_smoke", [python, str(ROOT / "eval" / "retrieval_signals_module_smoke.py")]),
        run_step("miner_regression", [python, str(ROOT / "eval" / "retrieval_signal_miner_regression.py")]),
        run_step("nested_config", [python, str(ROOT / "eval" / "config_nested_parser_regression.py")]),
        run_step("claim_scope_gate", [python, str(ROOT / "eval" / "claim_scope_promotion_gate.py")]),
        run_step(
            "randomized_guard",
            [
                python,
                str(ROOT / "eval" / "selector_retrieval_guard_randomized_eval.py"),
                "--embedding-backend",
                "hash",
                "--cases",
                str(args.random_cases),
                "--seed",
                str(args.seed),
                "--top-k",
                "10",
            ],
        ),
        run_step(
            "policy_deflection",
            [python, str(ROOT / "eval" / "policy_correction_deflection_regression.py")],
        ),
        run_step("answer_quality", [python, str(ROOT / "eval" / "answer_quality_eval.py")]),
    ]

    report = build_report(args, steps, artifacts)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "required_summary": report["required_summary"],
                "json": str(out_json),
                "markdown": str(out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
