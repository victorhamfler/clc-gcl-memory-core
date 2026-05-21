from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_CANDIDATES = REPO_ROOT / "experiments" / "claim_scope_alias_candidates_v2.json"
OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_promotion_gate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_promotion_gate_report.md"


def run_step(name: str, command: list[str], cwd: Path = ROOT) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    parsed_stdout = parse_last_json(proc.stdout)
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "parsed_stdout": parsed_stdout,
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


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_report(args: argparse.Namespace, steps: list[dict[str, Any]], artifacts: dict[str, str]) -> dict[str, Any]:
    nested_config_report = read_json(REPO_ROOT / "experiments" / "config_nested_parser_regression_results.json")
    candidate_report = read_json(Path(artifacts["candidate_json"]))
    replay_report = read_json(Path(artifacts["replay_json"]))
    config_report = read_json(REPO_ROOT / "experiments" / "claim_scope_config_regression_results.json")
    deadline_filename_report = read_json(
        REPO_ROOT / "experiments" / "claim_scope_deadline_filename_regression_results.json"
    )
    answer_type_report = read_json(REPO_ROOT / "experiments" / "answer_type_relation_regression_results.json")
    answer_type_config_report = read_json(REPO_ROOT / "experiments" / "answer_type_config_regression_results.json")
    answer_type_method_report = read_json(REPO_ROOT / "experiments" / "answer_type_method_filename_regression_results.json")
    answer_type_policy_report = read_json(REPO_ROOT / "experiments" / "answer_type_policy_split_probe_results.json")
    policy_deflection_report = read_json(
        REPO_ROOT / "experiments" / "policy_correction_deflection_regression_results.json"
    )
    gate_ok = all(step["ok"] for step in steps)

    required_summary = {
        "nested_config_ok": bool(nested_config_report and nested_config_report.get("ok")),
        "candidate_ab_ok": bool(candidate_report and candidate_report.get("ok")),
        "outcome_replay_ok": bool(replay_report and replay_report.get("ok")),
        "config_regression_ok": bool(config_report and config_report.get("passed")),
        "claim_scope_deadline_filename_ok": bool(deadline_filename_report and deadline_filename_report.get("ok")),
        "answer_type_regression_ok": bool(answer_type_report and answer_type_report.get("ok")),
        "answer_type_config_ok": bool(answer_type_config_report and answer_type_config_report.get("ok")),
        "answer_type_method_filename_ok": bool(answer_type_method_report and answer_type_method_report.get("ok")),
        "answer_type_policy_split_probe_ok": bool(answer_type_policy_report and answer_type_policy_report.get("ok")),
        "policy_correction_deflection_ok": bool(policy_deflection_report and policy_deflection_report.get("ok")),
    }
    if args.include_selector_guards:
        required_summary["selector_guards_ok"] = all(
            step["ok"]
            for step in steps
            if step["name"] in {"near_topic_distractor", "agent_workflow_integration", "randomized_guard"}
        )
    promotion_ready = gate_ok and all(required_summary.values())
    return {
        "ok": promotion_ready,
        "candidate_path": str(Path(args.candidates).resolve()),
        "log_path": str(Path(args.log).resolve()) if args.log else None,
        "include_selector_guards": bool(args.include_selector_guards),
        "required_summary": required_summary,
        "artifacts": artifacts,
        "steps": steps,
        "nested_config_regression": {
            "ok": nested_config_report.get("ok") if nested_config_report else None,
            "failures": nested_config_report.get("failures") if nested_config_report else None,
            "answer_type_rules": nested_config_report.get("actual_answer_type_rules") if nested_config_report else None,
        },
        "candidate_ab": {
            "ok": candidate_report.get("ok") if candidate_report else None,
            "case_count": candidate_report.get("case_count") if candidate_report else None,
            "failures": candidate_report.get("failures") if candidate_report else None,
            "conservative_slots": candidate_report.get("conservative_slots") if candidate_report else None,
            "split_overlay_slots": candidate_report.get("split_overlay_slots") if candidate_report else None,
            "risky_slots_detected": candidate_report.get("risky_slots_detected") if candidate_report else None,
        },
        "outcome_replay": {
            "ok": replay_report.get("ok") if replay_report else None,
            "evaluated_positive": replay_report.get("evaluated_positive") if replay_report else None,
            "evaluated_negative": replay_report.get("evaluated_negative") if replay_report else None,
            "metrics": replay_report.get("metrics") if replay_report else None,
        },
        "config_regression": {
            "passed": config_report.get("passed") if config_report else None,
            "target_rank": config_report.get("target_rank") if config_report else None,
            "color_correction_rank": config_report.get("color_correction_rank") if config_report else None,
        },
        "claim_scope_deadline_filename_regression": {
            "ok": deadline_filename_report.get("ok") if deadline_filename_report else None,
            "deadline_rank": deadline_filename_report.get("deadline_rank") if deadline_filename_report else None,
            "filename_rank": deadline_filename_report.get("filename_rank") if deadline_filename_report else None,
            "filename_claim_scope": deadline_filename_report.get("filename_claim_scope")
            if deadline_filename_report
            else None,
        },
        "answer_type_regression": {
            "ok": answer_type_report.get("ok") if answer_type_report else None,
            "case_count": answer_type_report.get("case_count") if answer_type_report else None,
        },
        "answer_type_config_regression": {
            "ok": answer_type_config_report.get("ok") if answer_type_config_report else None,
            "target_rank": answer_type_config_report.get("target_rank") if answer_type_config_report else None,
            "owner_rank": answer_type_config_report.get("owner_rank") if answer_type_config_report else None,
        },
        "answer_type_method_filename_regression": {
            "ok": answer_type_method_report.get("ok") if answer_type_method_report else None,
            "case_count": answer_type_method_report.get("case_count") if answer_type_method_report else None,
        },
        "answer_type_policy_split_probe": {
            "ok": answer_type_policy_report.get("ok") if answer_type_policy_report else None,
            "case_count": answer_type_policy_report.get("case_count") if answer_type_policy_report else None,
            "policy_rules": answer_type_policy_report.get("policy_rules") if answer_type_policy_report else None,
        },
        "policy_correction_deflection_regression": {
            "ok": policy_deflection_report.get("ok") if policy_deflection_report else None,
            "case_count": policy_deflection_report.get("case_count") if policy_deflection_report else None,
        },
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Claim Scope Promotion Gate",
        "",
        f"Promotion ready: **{report['ok']}**",
        f"Candidate file: `{report['candidate_path']}`",
        f"Outcome log: `{report['log_path'] or 'default'}`",
        f"Selector guards included: `{report['include_selector_guards']}`",
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
            "## Nested Config Regression",
            "",
            f"- Passed: `{report['nested_config_regression']['ok']}`",
            f"- Failures: `{', '.join(report['nested_config_regression']['failures'] or []) or 'none'}`",
            f"- Answer-type rules: `{', '.join(report['nested_config_regression']['answer_type_rules'] or []) or 'none'}`",
            "",
            "## Candidate A/B",
            "",
            f"- Passed: `{report['candidate_ab']['ok']}`",
            f"- Cases: `{report['candidate_ab']['case_count']}`",
            f"- Failures: `{', '.join(report['candidate_ab']['failures'] or []) or 'none'}`",
            f"- Conservative slots: `{', '.join(report['candidate_ab']['conservative_slots'] or []) or 'none'}`",
            f"- Split-overlay slots: `{', '.join(report['candidate_ab']['split_overlay_slots'] or []) or 'none'}`",
            f"- Risky slots detected: `{', '.join(report['candidate_ab']['risky_slots_detected'] or []) or 'none'}`",
            "",
            "## Outcome Replay",
            "",
            f"- Passed: `{report['outcome_replay']['ok']}`",
            f"- Evaluated positives: `{report['outcome_replay']['evaluated_positive']}`",
            f"- Evaluated negatives: `{report['outcome_replay']['evaluated_negative']}`",
        ]
    )
    for key, value in (report["outcome_replay"]["metrics"] or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Config Regression",
            "",
            f"- Passed: `{report['config_regression']['passed']}`",
            f"- Target rank: `{report['config_regression']['target_rank']}`",
            f"- Color correction rank: `{report['config_regression']['color_correction_rank']}`",
            "",
            "## Claim Scope Deadline/Filename Regression",
            "",
            f"- Passed: `{report['claim_scope_deadline_filename_regression']['ok']}`",
            f"- Deadline rank: `{report['claim_scope_deadline_filename_regression']['deadline_rank']}`",
            f"- Filename rank: `{report['claim_scope_deadline_filename_regression']['filename_rank']}`",
            f"- Filename claim-scope: `{report['claim_scope_deadline_filename_regression']['filename_claim_scope']}`",
            "",
            "## Answer Type Regression",
            "",
            f"- Passed: `{report['answer_type_regression']['ok']}`",
            f"- Cases: `{report['answer_type_regression']['case_count']}`",
            "",
            "## Answer Type Config Regression",
            "",
            f"- Passed: `{report['answer_type_config_regression']['ok']}`",
            f"- Target rank: `{report['answer_type_config_regression']['target_rank']}`",
            f"- Owner rank: `{report['answer_type_config_regression']['owner_rank']}`",
            "",
            "## Answer Type Method/Filename Regression",
            "",
            f"- Passed: `{report['answer_type_method_filename_regression']['ok']}`",
            f"- Cases: `{report['answer_type_method_filename_regression']['case_count']}`",
            "",
            "## Answer Type Policy Split Probe",
            "",
            f"- Passed: `{report['answer_type_policy_split_probe']['ok']}`",
            f"- Cases: `{report['answer_type_policy_split_probe']['case_count']}`",
            f"- Policy rules: `{', '.join(report['answer_type_policy_split_probe']['policy_rules'] or []) or 'none'}`",
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
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for label, path in report["artifacts"].items():
        lines.append(f"- `{label}`: `{path}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the claim-scope promotion gate.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--log", default="")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--include-selector-guards", action="store_true")
    parser.add_argument("--random-cases", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260520)
    args = parser.parse_args()

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    candidate_json = out_json.with_name(out_json.stem + "_candidate_ab.json")
    candidate_md = out_md.with_name(out_md.stem + "_candidate_ab.md")
    replay_json = out_json.with_name(out_json.stem + "_outcome_replay.json")
    replay_md = out_md.with_name(out_md.stem + "_outcome_replay.md")
    artifacts = {
        "gate_json": str(out_json),
        "gate_markdown": str(out_md),
        "candidate_json": str(candidate_json),
        "candidate_markdown": str(candidate_md),
        "replay_json": str(replay_json),
        "replay_markdown": str(replay_md),
    }

    python = sys.executable
    steps = [
        run_step(
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                str(ROOT / "core" / "pipeline.py"),
                str(ROOT / "core" / "runtime.py"),
                str(ROOT / "core" / "config.py"),
                str(ROOT / "eval" / "config_nested_parser_regression.py"),
                str(ROOT / "eval" / "claim_scope_candidate_ab_eval.py"),
                str(ROOT / "eval" / "claim_scope_outcome_replay_eval.py"),
                str(ROOT / "eval" / "claim_scope_config_regression.py"),
                str(ROOT / "eval" / "claim_scope_deadline_filename_regression.py"),
                str(ROOT / "eval" / "answer_type_relation_regression.py"),
                str(ROOT / "eval" / "answer_type_config_regression.py"),
                str(ROOT / "eval" / "answer_type_method_filename_regression.py"),
                str(ROOT / "eval" / "answer_type_policy_split_probe.py"),
                str(ROOT / "eval" / "policy_correction_deflection_regression.py"),
            ],
        ),
        run_step("nested_config_regression", [python, str(ROOT / "eval" / "config_nested_parser_regression.py")]),
        run_step(
            "candidate_ab",
            [
                python,
                str(ROOT / "eval" / "claim_scope_candidate_ab_eval.py"),
                "--candidates",
                str(Path(args.candidates)),
                "--out-json",
                str(candidate_json),
                "--out-md",
                str(candidate_md),
            ],
        ),
        run_step(
            "outcome_replay",
            [
                python,
                str(ROOT / "eval" / "claim_scope_outcome_replay_eval.py"),
                "--out-json",
                str(replay_json),
                "--out-md",
                str(replay_md),
            ]
            + (["--log", str(Path(args.log))] if args.log else []),
        ),
        run_step("config_regression", [python, str(ROOT / "eval" / "claim_scope_config_regression.py")]),
        run_step(
            "claim_scope_deadline_filename_regression",
            [python, str(ROOT / "eval" / "claim_scope_deadline_filename_regression.py")],
        ),
        run_step("answer_type_regression", [python, str(ROOT / "eval" / "answer_type_relation_regression.py")]),
        run_step("answer_type_config_regression", [python, str(ROOT / "eval" / "answer_type_config_regression.py")]),
        run_step(
            "answer_type_method_filename_regression",
            [python, str(ROOT / "eval" / "answer_type_method_filename_regression.py")],
        ),
        run_step(
            "answer_type_policy_split_probe",
            [python, str(ROOT / "eval" / "answer_type_policy_split_probe.py")],
        ),
        run_step(
            "policy_correction_deflection_regression",
            [python, str(ROOT / "eval" / "policy_correction_deflection_regression.py")],
        ),
    ]
    if args.include_selector_guards:
        steps.extend(
            [
                run_step(
                    "near_topic_distractor",
                    [
                        python,
                        str(ROOT / "eval" / "selector_near_topic_distractor_eval.py"),
                        "--embedding-backend",
                        "hash",
                        "--top-k",
                        "10",
                    ],
                ),
                run_step(
                    "agent_workflow_integration",
                    [
                        python,
                        str(ROOT / "eval" / "agent_workflow_selector_integration_eval.py"),
                        "--embedding-backend",
                        "hash",
                        "--top-k",
                        "10",
                    ],
                ),
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
            ]
        )

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
