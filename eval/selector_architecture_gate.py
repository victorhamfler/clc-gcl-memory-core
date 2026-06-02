from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_RETRIEVAL_CANDIDATES = ROOT / "test_corpora" / "retrieval_signal_candidates_v1.json"
DEFAULT_EVIDENCE_CANDIDATES = ROOT / "test_corpora" / "evidence_state_candidates_v1.json"
OUT_JSON = REPO_ROOT / "experiments" / "selector_architecture_gate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_architecture_gate_report.md"


def resolve_candidate_path(raw_path: str | None, default_path: Path, *, allow_missing: bool) -> tuple[Path, dict[str, Any]]:
    if raw_path is None or str(raw_path).strip().lower() in {"", "default"}:
        return default_path, {"requested": raw_path, "resolved": str(default_path), "used_default": True, "missing": False}
    path = Path(raw_path)
    if path.exists():
        return path, {"requested": raw_path, "resolved": str(path), "used_default": False, "missing": False}
    if allow_missing:
        return default_path, {
            "requested": raw_path,
            "resolved": str(default_path),
            "used_default": True,
            "missing": True,
        }
    return path, {"requested": raw_path, "resolved": str(path), "used_default": False, "missing": True}


def run_step(name: str, command: list[str], cwd: Path = ROOT, timeout_seconds: int = 240) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
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
            "name": name,
            "ok": False,
            "returncode": None,
            "command": command,
            "stdout": stdout.strip(),
            "stderr": (stderr.strip() + f"\nTimed out after {timeout_seconds} seconds.").strip(),
            "parsed_stdout": parse_last_json(stdout),
            "timed_out": True,
        }
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "parsed_stdout": parse_last_json(proc.stdout),
    }


def skip_step(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": True,
        "returncode": 0,
        "command": ["<skipped>"],
        "stdout": json.dumps({"ok": True, "skipped": True, "reason": reason}),
        "stderr": "",
        "parsed_stdout": {"ok": True, "skipped": True, "reason": reason},
        "skipped": True,
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


def step_json(steps: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for step in steps:
        if step["name"] == name and isinstance(step.get("parsed_stdout"), dict):
            return step["parsed_stdout"]
    return None


def build_report(args: argparse.Namespace, steps: list[dict[str, Any]], artifacts: dict[str, str]) -> dict[str, Any]:
    retrieval_gate = read_json(Path(artifacts["retrieval_gate_json"])) or step_json(steps, "retrieval_signal_gate")
    evidence_gate = read_json(Path(artifacts["evidence_gate_json"])) or step_json(steps, "evidence_state_gate")
    required_summary = {
        "retrieval_signal_gate_ok": bool(retrieval_gate and retrieval_gate.get("ok")),
        "evidence_state_gate_ok": bool(evidence_gate and evidence_gate.get("ok")),
        "shadow_coverage_guard_ok": bool(
            (step_json(steps, "canonical_ogcf_shadow_coverage_regression") or {}).get("ok")
        ),
        "gemma_shadow_regression_ok": bool(
            (step_json(steps, "adaptive_context_gemma_shadow_regression") or {}).get("ok")
        ),
        "adaptive_behavior_shadow_runtime_ok": bool(
            (step_json(steps, "adaptive_behavior_shadow_runtime_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_runtime_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_runtime_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_runtime_view_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_runtime_view_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_logged_eval_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_logged_eval") or {}).get("ok")
        ),
        "adaptive_residual_shadow_multi_log_eval_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_multi_log_eval") or {}).get("ok")
        ),
        "adaptive_residual_shadow_suppressor_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_suppressor_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_external_failure_replay_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_external_failure_replay") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_miner_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_candidate_miner") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_miner_regression_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_miner_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_patch_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_patch_proposal") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_patch_regression_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_patch_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_patch_pipeline_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_patch_pipeline_regression") or {}).get("ok")
        ),
        "adaptive_residual_shadow_term_patch_guard_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_term_patch_guard") or {}).get("ok")
        ),
        "adaptive_residual_shadow_promotion_readiness_ok": bool(
            (step_json(steps, "adaptive_residual_shadow_promotion_readiness") or {}).get("ok")
        ),
        "adaptive_residual_risk_scorer_ok": bool(
            (step_json(steps, "adaptive_residual_risk_scorer_regression") or {}).get("ok")
        ),
        "adaptive_residual_risk_disagreement_ok": bool(
            (step_json(steps, "adaptive_residual_risk_disagreement_eval") or {}).get("ok")
        ),
        "adaptive_residual_risk_logged_eval_ok": bool(
            (step_json(steps, "adaptive_residual_risk_logged_eval") or {}).get("ok")
        ),
        "adaptive_residual_risk_overprotection_candidate_ok": bool(
            (step_json(steps, "adaptive_residual_risk_overprotection_candidate") or {}).get("ok")
        ),
        "adaptive_residual_risk_overprotection_recurrence_ok": bool(
            (step_json(steps, "adaptive_residual_risk_overprotection_recurrence") or {}).get("ok")
        ),
        "adaptive_residual_risk_exception_simulation_ok": bool(
            (step_json(steps, "adaptive_residual_risk_exception_simulation") or {}).get("ok")
        ),
        "adaptive_residual_learned_risk_veto_ok": bool(
            (step_json(steps, "adaptive_residual_learned_risk_veto_regression") or {}).get("ok")
        ),
        "adaptive_residual_learned_risk_external_failure_replay_ok": bool(
            (step_json(steps, "adaptive_residual_learned_risk_external_failure_replay") or {}).get("ok")
        ),
        "adaptive_residual_learned_risk_authority_paraphrase_ok": bool(
            (step_json(steps, "adaptive_residual_learned_risk_authority_paraphrase_regression") or {}).get("ok")
        ),
        "adaptive_residual_learned_risk_hermes_authority_boundary_replay_ok": bool(
            (step_json(steps, "adaptive_residual_learned_risk_hermes_authority_boundary_replay") or {}).get("ok")
        ),
        "adaptive_behavior_candidate_profile_guard_ok": bool(
            (step_json(steps, "adaptive_behavior_candidate_profile_guard_regression") or {}).get("ok")
        ),
        "adaptive_behavior_profile_memory_bank_guard_ok": bool(
            (step_json(steps, "adaptive_behavior_profile_memory_bank_guard_regression") or {}).get("ok")
        ),
        "adaptive_behavior_stale_conflict_candidate_ok": bool(
            (step_json(steps, "adaptive_behavior_stale_conflict_candidate_promotion") or {}).get("ok")
        ),
        "adaptive_behavior_stale_conflict_config_ok": bool(
            (step_json(steps, "adaptive_behavior_stale_conflict_config_regression") or {}).get("ok")
        ),
        "adaptive_behavior_missing_support_config_ok": bool(
            (step_json(steps, "adaptive_behavior_missing_support_config_regression") or {}).get("ok")
        ),
        "adaptive_behavior_wrong_scope_config_ok": bool(
            (step_json(steps, "adaptive_behavior_wrong_scope_config_regression") or {}).get("ok")
        ),
        "evidence_context_regression_ok": bool(
            (step_json(steps, "evidence_context_regression") or {}).get("ok")
        ),
        "evidence_context_selector_runtime_ok": bool(
            (step_json(steps, "evidence_context_selector_runtime_regression") or {}).get("ok")
        ),
        "resolver_policy_config_ok": bool(
            (step_json(steps, "resolver_policy_config_regression") or {}).get("ok")
        ),
        "resolver_policy_runtime_view_ok": bool(
            (step_json(steps, "resolver_policy_runtime_view_regression") or {}).get("ok")
        ),
        "resolver_shadow_runtime_view_ok": bool(
            (step_json(steps, "resolver_shadow_runtime_view_regression") or {}).get("ok")
        ),
        "answer_quality_eval_ok": bool(
            (step_json(steps, "answer_quality_eval") or {}).get("ok")
        ),
        "multi_intent_answer_composition_ok": bool(
            (step_json(steps, "multi_intent_answer_composition_regression") or {}).get("ok")
        ),
        "controller_packet_regression_ok": bool(
            (step_json(steps, "controller_packet_regression") or {}).get("ok")
        ),
        "controller_packet_residual_pipeline_ok": bool(
            (step_json(steps, "controller_packet_residual_pipeline_regression") or {}).get("ok")
        ),
        "controller_packet_answer_feedback_pipeline_ok": bool(
            (step_json(steps, "controller_packet_answer_feedback_pipeline_regression") or {}).get("ok")
        ),
        "outcome_logging_controller_packet_ok": bool(
            (step_json(steps, "outcome_logging_regression") or {}).get("ok")
        ),
        "controller_packet_memory_bank_ok": bool(
            (step_json(steps, "controller_packet_memory_bank_regression") or {}).get("ok")
        ),
        "controller_packet_calibration_proposals_ok": bool(
            (step_json(steps, "controller_packet_calibration_proposals_regression") or {}).get("ok")
        ),
        "controller_packet_calibration_guard_ok": bool(
            (step_json(steps, "controller_packet_calibration_guard_regression") or {}).get("ok")
        ),
        "controller_packet_calibration_config_ok": bool(
            (step_json(steps, "controller_packet_calibration_config_regression") or {}).get("ok")
        ),
        "controller_packet_calibration_runtime_view_ok": bool(
            (step_json(steps, "controller_packet_calibration_runtime_view_regression") or {}).get("ok")
        ),
        "controller_packet_calibration_pipeline_ok": bool(
            (step_json(steps, "controller_packet_calibration_pipeline_regression") or {}).get("ok")
        ),
        "controller_packet_multirun_calibration_ok": bool(
            (step_json(steps, "controller_packet_multirun_calibration_regression") or {}).get("ok")
        ),
        "controller_packet_recurring_holdout_ok": bool(
            (step_json(steps, "controller_packet_recurring_holdout_regression") or {}).get("ok")
        ),
        "controller_packet_review_separation_ok": bool(
            (step_json(steps, "controller_packet_review_separation_regression") or {}).get("ok")
        ),
        "controller_packet_bridge_separator_ok": bool(
            (step_json(steps, "controller_packet_bridge_separator_regression") or {}).get("ok")
        ),
        "controller_packet_bridge_separator_holdout_ok": bool(
            (step_json(steps, "controller_packet_bridge_separator_holdout_regression") or {}).get("ok")
        ),
        "controller_packet_ogcf_bridge_scorer_ok": bool(
            (step_json(steps, "controller_packet_ogcf_bridge_scorer_regression") or {}).get("ok")
        ),
        "controller_packet_ogcf_bridge_scorer_feature_ok": bool(
            (step_json(steps, "controller_packet_ogcf_bridge_scorer_feature_regression") or {}).get("ok")
        ),
        "controller_packet_ogcf_bridge_feature_audit_ok": bool(
            (step_json(steps, "controller_packet_ogcf_bridge_feature_audit_regression") or {}).get("ok")
        ),
        "controller_packet_ogcf_bridge_source_holdout_ok": bool(
            (step_json(steps, "controller_packet_ogcf_bridge_source_holdout_regression") or {}).get("ok")
        ),
        "controller_packet_ogcf_bridge_leave_one_source_out_ok": bool(
            (step_json(steps, "controller_packet_ogcf_bridge_leave_one_source_out_regression") or {}).get("ok")
        ),
        "adaptive_behavior_feature_scorer_ok": bool(
            (step_json(steps, "adaptive_behavior_feature_scorer_regression") or {}).get("ok")
        ),
        "adaptive_behavior_feature_scorer_hybrid_ok": bool(
            (step_json(steps, "adaptive_behavior_feature_scorer_hybrid_regression") or {}).get("ok")
        ),
        "adaptive_behavior_feature_challenge_ok": bool(
            (step_json(steps, "adaptive_behavior_feature_challenge_regression") or {}).get("ok")
        ),
    }
    return {
        "ok": all(step["ok"] for step in steps) and all(required_summary.values()),
        "retrieval_candidates": artifacts["retrieval_candidates_resolved"],
        "evidence_candidates": artifacts["evidence_candidates_resolved"],
        "candidate_resolution": {
            "retrieval": artifacts["retrieval_candidate_resolution"],
            "evidence": artifacts["evidence_candidate_resolution"],
        },
        "required_summary": required_summary,
        "artifacts": artifacts,
        "retrieval_gate_summary": retrieval_gate.get("required_summary") if retrieval_gate else None,
        "evidence_gate_summary": evidence_gate.get("required_summary") if evidence_gate else None,
        "steps": steps,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Architecture Gate",
        "",
        f"Architecture ready: **{report['ok']}**",
        f"Retrieval candidates: `{report['retrieval_candidates']}`",
        f"Evidence candidates: `{report['evidence_candidates']}`",
        "",
        "## Required Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["required_summary"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Retrieval Signal Gate", "", "```json"])
    lines.append(json.dumps(report["retrieval_gate_summary"], indent=2))
    lines.extend(["```", "", "## Evidence State Gate", "", "```json"])
    lines.append(json.dumps(report["evidence_gate_summary"], indent=2))
    lines.extend(["```", "", "## Shadow Guard Regressions", "", "| regression | pass |", "| --- | --- |"])
    for key in (
        "shadow_coverage_guard_ok",
        "gemma_shadow_regression_ok",
        "adaptive_behavior_shadow_runtime_ok",
        "adaptive_residual_shadow_runtime_ok",
        "adaptive_residual_shadow_runtime_view_ok",
        "adaptive_residual_shadow_logged_eval_ok",
        "adaptive_residual_shadow_multi_log_eval_ok",
        "adaptive_residual_shadow_suppressor_ok",
        "adaptive_residual_shadow_external_failure_replay_ok",
        "adaptive_residual_shadow_term_miner_ok",
        "adaptive_residual_shadow_term_miner_regression_ok",
        "adaptive_residual_shadow_term_patch_ok",
        "adaptive_residual_shadow_term_patch_regression_ok",
        "adaptive_residual_shadow_term_patch_pipeline_ok",
        "adaptive_residual_shadow_term_patch_guard_ok",
        "adaptive_residual_shadow_promotion_readiness_ok",
        "adaptive_residual_risk_scorer_ok",
        "adaptive_residual_risk_disagreement_ok",
        "adaptive_residual_risk_logged_eval_ok",
        "adaptive_residual_risk_overprotection_candidate_ok",
        "adaptive_residual_risk_overprotection_recurrence_ok",
        "adaptive_residual_risk_exception_simulation_ok",
        "adaptive_residual_learned_risk_veto_ok",
        "adaptive_residual_learned_risk_external_failure_replay_ok",
        "adaptive_residual_learned_risk_authority_paraphrase_ok",
        "adaptive_residual_learned_risk_hermes_authority_boundary_replay_ok",
        "adaptive_behavior_candidate_profile_guard_ok",
        "adaptive_behavior_profile_memory_bank_guard_ok",
        "adaptive_behavior_stale_conflict_candidate_ok",
        "adaptive_behavior_stale_conflict_config_ok",
        "adaptive_behavior_missing_support_config_ok",
        "adaptive_behavior_wrong_scope_config_ok",
        "evidence_context_regression_ok",
        "evidence_context_selector_runtime_ok",
        "resolver_policy_config_ok",
        "resolver_policy_runtime_view_ok",
        "resolver_shadow_runtime_view_ok",
        "answer_quality_eval_ok",
        "multi_intent_answer_composition_ok",
        "controller_packet_regression_ok",
        "controller_packet_residual_pipeline_ok",
        "controller_packet_answer_feedback_pipeline_ok",
        "outcome_logging_controller_packet_ok",
        "controller_packet_memory_bank_ok",
        "controller_packet_calibration_proposals_ok",
        "controller_packet_calibration_guard_ok",
        "controller_packet_calibration_config_ok",
        "controller_packet_calibration_pipeline_ok",
        "controller_packet_multirun_calibration_ok",
        "controller_packet_recurring_holdout_ok",
        "controller_packet_review_separation_ok",
        "controller_packet_bridge_separator_ok",
        "controller_packet_bridge_separator_holdout_ok",
        "controller_packet_ogcf_bridge_scorer_ok",
        "controller_packet_ogcf_bridge_scorer_feature_ok",
        "controller_packet_ogcf_bridge_feature_audit_ok",
        "controller_packet_ogcf_bridge_source_holdout_ok",
        "controller_packet_ogcf_bridge_leave_one_source_out_ok",
        "adaptive_behavior_feature_scorer_ok",
        "adaptive_behavior_feature_scorer_hybrid_ok",
        "adaptive_behavior_feature_challenge_ok",
    ):
        lines.append(f"| `{key}` | `{report['required_summary'].get(key)}` |")
    lines.extend(
        [
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
    parser = argparse.ArgumentParser(description="Run the unified selector architecture promotion gate.")
    parser.add_argument("--retrieval-candidates", default=str(DEFAULT_RETRIEVAL_CANDIDATES))
    parser.add_argument("--evidence-candidates", default=str(DEFAULT_EVIDENCE_CANDIDATES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--random-cases", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260520)
    parser.add_argument(
        "--allow-missing-runtime-artifacts",
        action="store_true",
        help="Skip log/DB/model-artifact dependent checks for fresh external-agent clones before they generate runtime logs.",
    )
    parser.add_argument(
        "--allow-missing-candidates",
        action="store_true",
        help="If a supplied candidate file is missing, use the default fixture for that family and record the fallback.",
    )
    args = parser.parse_args()

    retrieval_candidates, retrieval_resolution = resolve_candidate_path(
        args.retrieval_candidates,
        DEFAULT_RETRIEVAL_CANDIDATES,
        allow_missing=args.allow_missing_candidates,
    )
    evidence_candidates, evidence_resolution = resolve_candidate_path(
        args.evidence_candidates,
        DEFAULT_EVIDENCE_CANDIDATES,
        allow_missing=args.allow_missing_candidates,
    )
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    retrieval_gate_json = out_json.with_name(out_json.stem + "_retrieval_signal_gate.json")
    retrieval_gate_md = out_md.with_name(out_md.stem + "_retrieval_signal_gate.md")
    evidence_gate_json = out_json.with_name(out_json.stem + "_evidence_state_gate.json")
    evidence_gate_md = out_md.with_name(out_md.stem + "_evidence_state_gate.md")
    artifacts = {
        "gate_json": str(out_json),
        "gate_markdown": str(out_md),
        "retrieval_gate_json": str(retrieval_gate_json),
        "retrieval_gate_markdown": str(retrieval_gate_md),
        "evidence_gate_json": str(evidence_gate_json),
        "evidence_gate_markdown": str(evidence_gate_md),
        "retrieval_candidates_resolved": str(retrieval_candidates),
        "evidence_candidates_resolved": str(evidence_candidates),
        "retrieval_candidate_resolution": retrieval_resolution,
        "evidence_candidate_resolution": evidence_resolution,
    }

    python = sys.executable
    artifact_skip_reason = "portable sanity mode: runtime logs, local DBs, or local model artifacts may be absent"
    maybe_artifact_step = (
        lambda name, command: skip_step(name, artifact_skip_reason)
        if args.allow_missing_runtime_artifacts
        else run_step(name, command)
    )
    steps = [
        run_step(
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                str(ROOT / "core" / "retrieval_signals.py"),
                str(ROOT / "core" / "evidence_states.py"),
                str(ROOT / "core" / "adaptive_behavior.py"),
                str(ROOT / "core" / "adaptive_behavior_shadow.py"),
                str(ROOT / "core" / "adaptive_residual_shadow.py"),
                str(ROOT / "core" / "evidence_context.py"),
                str(ROOT / "core" / "controller_context.py"),
                str(ROOT / "core" / "controller_packet.py"),
                str(ROOT / "core" / "pipeline.py"),
                str(ROOT / "core" / "resolver.py"),
                str(ROOT / "core" / "resolver_policy.py"),
                str(ROOT / "core" / "runtime.py"),
                str(ROOT / "eval" / "retrieval_signal_promotion_gate.py"),
                str(ROOT / "eval" / "evidence_state_promotion_gate.py"),
                str(ROOT / "eval" / "canonical_ogcf_production_shadow_eval.py"),
                str(ROOT / "eval" / "canonical_ogcf_shadow_coverage_regression.py"),
                str(ROOT / "eval" / "adaptive_context_gemma_shadow_eval.py"),
                str(ROOT / "eval" / "adaptive_context_gemma_shadow_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_shadow_runtime_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_runtime_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_runtime_view_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_fourth_holdout_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_fifth_holdout_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_sixth_natural_holdout_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_seventh_agent_style_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_ninth_authority_veto_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_tenth_authority_boundary_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_benefit_opportunity_log.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_logged_eval.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_multi_log_eval.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_suppressor_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_external_failure_replay.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_candidate_miner.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_miner_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_proposal.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_pipeline_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_guard.py"),
                str(ROOT / "eval" / "adaptive_residual_shadow_promotion_readiness.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_scorer_eval.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_scorer_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_disagreement_eval.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_logged_eval.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_overprotection_candidate.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_overprotection_recurrence.py"),
                str(ROOT / "eval" / "adaptive_residual_risk_exception_simulation.py"),
                str(ROOT / "eval" / "adaptive_residual_learned_risk_veto_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_learned_risk_external_failure_replay.py"),
                str(ROOT / "eval" / "adaptive_residual_learned_risk_authority_paraphrase_regression.py"),
                str(ROOT / "eval" / "adaptive_residual_learned_risk_hermes_authority_boundary_replay.py"),
                str(ROOT / "eval" / "adaptive_behavior_shadow_real_log_calibration.py"),
                str(ROOT / "eval" / "adaptive_behavior_shadow_real_log_rerun.py"),
                str(ROOT / "eval" / "adaptive_behavior_candidate_profile.py"),
                str(ROOT / "eval" / "adaptive_behavior_candidate_profile_guard.py"),
                str(ROOT / "eval" / "adaptive_behavior_candidate_profile_guard_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_profile_memory_bank.py"),
                str(ROOT / "eval" / "adaptive_behavior_profile_memory_bank_guard.py"),
                str(ROOT / "eval" / "adaptive_behavior_profile_memory_bank_guard_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_stale_conflict_candidate_promotion.py"),
                str(ROOT / "eval" / "adaptive_behavior_stale_conflict_config_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_missing_support_config_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_wrong_scope_config_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_scorer_eval.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_scorer_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_scorer_hybrid_eval.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_scorer_hybrid_regression.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_challenge_log.py"),
                str(ROOT / "eval" / "adaptive_behavior_feature_challenge_regression.py"),
                str(ROOT / "eval" / "evidence_context_regression.py"),
                str(ROOT / "eval" / "evidence_context_selector_runtime_regression.py"),
                str(ROOT / "eval" / "resolver_policy_config_regression.py"),
                str(ROOT / "eval" / "resolver_policy_runtime_view_regression.py"),
                str(ROOT / "eval" / "resolver_shadow_runtime_view_regression.py"),
                str(ROOT / "eval" / "answer_quality_eval.py"),
                str(ROOT / "eval" / "multi_intent_answer_composition_regression.py"),
                str(ROOT / "eval" / "controller_packet_collector.py"),
                str(ROOT / "eval" / "controller_packet_answer_feedback_eval.py"),
                str(ROOT / "eval" / "controller_packet_answer_feedback_pipeline_regression.py"),
                str(ROOT / "eval" / "controller_packet_residual_eval.py"),
                str(ROOT / "eval" / "controller_packet_residual_pipeline_regression.py"),
                str(ROOT / "eval" / "controller_packet_regression.py"),
                str(ROOT / "eval" / "controller_packet_memory_bank.py"),
                str(ROOT / "eval" / "controller_packet_memory_bank_regression.py"),
                str(ROOT / "eval" / "controller_packet_calibration_proposals.py"),
                str(ROOT / "eval" / "controller_packet_calibration_proposals_regression.py"),
                str(ROOT / "eval" / "controller_packet_calibration_guard.py"),
                str(ROOT / "eval" / "controller_packet_calibration_guard_regression.py"),
                str(ROOT / "eval" / "controller_packet_calibration_config_regression.py"),
                str(ROOT / "eval" / "controller_packet_calibration_runtime_view_regression.py"),
                str(ROOT / "eval" / "controller_packet_calibration_pipeline.py"),
                str(ROOT / "eval" / "controller_packet_calibration_pipeline_regression.py"),
                str(ROOT / "eval" / "controller_packet_multirun_calibration.py"),
                str(ROOT / "eval" / "controller_packet_multirun_calibration_regression.py"),
                str(ROOT / "eval" / "controller_packet_recurring_holdout.py"),
                str(ROOT / "eval" / "controller_packet_recurring_holdout_regression.py"),
                str(ROOT / "eval" / "controller_packet_review_separation.py"),
                str(ROOT / "eval" / "controller_packet_review_separation_regression.py"),
                str(ROOT / "eval" / "controller_packet_bridge_separator.py"),
                str(ROOT / "eval" / "controller_packet_bridge_separator_regression.py"),
                str(ROOT / "eval" / "controller_packet_bridge_separator_holdout.py"),
                str(ROOT / "eval" / "controller_packet_bridge_separator_holdout_regression.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_scorer.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_scorer_regression.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_scorer_feature_regression.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_feature_audit.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_feature_audit_regression.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_source_holdout.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_source_holdout_regression.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_leave_one_source_out.py"),
                str(ROOT / "eval" / "controller_packet_ogcf_bridge_leave_one_source_out_regression.py"),
                str(ROOT / "eval" / "outcome_logging_regression.py"),
                str(ROOT / "eval" / "selector_architecture_gate.py"),
            ],
        ),
        run_step(
            "retrieval_signal_gate",
            [
                python,
                str(ROOT / "eval" / "retrieval_signal_promotion_gate.py"),
                "--candidates",
                str(retrieval_candidates),
                "--out-json",
                str(retrieval_gate_json),
                "--out-md",
                str(retrieval_gate_md),
                "--random-cases",
                str(args.random_cases),
                "--seed",
                str(args.seed),
            ],
        ),
        run_step(
            "evidence_state_gate",
            [
                python,
                str(ROOT / "eval" / "evidence_state_promotion_gate.py"),
                "--candidates",
                str(evidence_candidates),
                "--out-json",
                str(evidence_gate_json),
                "--out-md",
                str(evidence_gate_md),
                "--random-cases",
                str(args.random_cases),
                "--seed",
                str(args.seed),
            ],
        ),
        run_step(
            "canonical_ogcf_shadow_coverage_regression",
            [python, str(ROOT / "eval" / "canonical_ogcf_shadow_coverage_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_context_gemma_shadow_regression",
            [python, str(ROOT / "eval" / "adaptive_context_gemma_shadow_regression.py")],
        ),
        run_step(
            "adaptive_behavior_shadow_runtime_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_shadow_runtime_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_runtime_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_runtime_regression.py")],
        ),
        run_step(
            "adaptive_residual_shadow_runtime_view_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_runtime_view_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_logged_eval",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_logged_eval.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_multi_log_eval",
            [
                python,
                str(ROOT / "eval" / "adaptive_residual_shadow_multi_log_eval.py"),
                "--min-logs",
                "7",
                "--exclude-processed-failures",
            ],
        ),
        run_step(
            "adaptive_residual_shadow_suppressor_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_suppressor_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_external_failure_replay",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_external_failure_replay.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_term_candidate_miner",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_candidate_miner.py")],
        ),
        run_step(
            "adaptive_residual_shadow_term_miner_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_miner_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_term_patch_proposal",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_proposal.py")],
        ),
        run_step(
            "adaptive_residual_shadow_term_patch_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_regression.py")],
        ),
        run_step(
            "adaptive_residual_shadow_term_patch_pipeline_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_pipeline_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_term_patch_guard",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_term_patch_guard.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_shadow_promotion_readiness",
            [python, str(ROOT / "eval" / "adaptive_residual_shadow_promotion_readiness.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_risk_scorer_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_scorer_regression.py")],
        ),
        run_step(
            "adaptive_residual_risk_disagreement_eval",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_disagreement_eval.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_risk_logged_eval",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_logged_eval.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_risk_overprotection_candidate",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_overprotection_candidate.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_risk_overprotection_recurrence",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_overprotection_recurrence.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_risk_exception_simulation",
            [python, str(ROOT / "eval" / "adaptive_residual_risk_exception_simulation.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_learned_risk_veto_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_learned_risk_veto_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_learned_risk_external_failure_replay",
            [python, str(ROOT / "eval" / "adaptive_residual_learned_risk_external_failure_replay.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_learned_risk_authority_paraphrase_regression",
            [python, str(ROOT / "eval" / "adaptive_residual_learned_risk_authority_paraphrase_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_residual_learned_risk_hermes_authority_boundary_replay",
            [python, str(ROOT / "eval" / "adaptive_residual_learned_risk_hermes_authority_boundary_replay.py")],
        ),
        run_step(
            "adaptive_behavior_candidate_profile_guard_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_candidate_profile_guard_regression.py")],
        ),
        run_step(
            "adaptive_behavior_profile_memory_bank_guard_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_profile_memory_bank_guard_regression.py")],
        ),
        run_step(
            "adaptive_behavior_stale_conflict_candidate_promotion",
            [python, str(ROOT / "eval" / "adaptive_behavior_stale_conflict_candidate_promotion.py")],
        ),
        run_step(
            "adaptive_behavior_stale_conflict_config_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_stale_conflict_config_regression.py")],
        ),
        run_step(
            "adaptive_behavior_missing_support_config_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_missing_support_config_regression.py")],
        ),
        run_step(
            "adaptive_behavior_wrong_scope_config_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_wrong_scope_config_regression.py")],
        ),
        run_step(
            "evidence_context_regression",
            [python, str(ROOT / "eval" / "evidence_context_regression.py")],
        ),
        run_step(
            "evidence_context_selector_runtime_regression",
            [python, str(ROOT / "eval" / "evidence_context_selector_runtime_regression.py")],
        ),
        run_step(
            "resolver_policy_config_regression",
            [python, str(ROOT / "eval" / "resolver_policy_config_regression.py")],
        ),
        run_step(
            "resolver_policy_runtime_view_regression",
            [python, str(ROOT / "eval" / "resolver_policy_runtime_view_regression.py")],
        ),
        run_step(
            "resolver_shadow_runtime_view_regression",
            [python, str(ROOT / "eval" / "resolver_shadow_runtime_view_regression.py")],
        ),
        run_step(
            "answer_quality_eval",
            [python, str(ROOT / "eval" / "answer_quality_eval.py")],
        ),
        run_step(
            "multi_intent_answer_composition_regression",
            [python, str(ROOT / "eval" / "multi_intent_answer_composition_regression.py")],
        ),
        run_step(
            "controller_packet_regression",
            [python, str(ROOT / "eval" / "controller_packet_regression.py")],
        ),
        run_step(
            "controller_packet_residual_pipeline_regression",
            [python, str(ROOT / "eval" / "controller_packet_residual_pipeline_regression.py")],
        ),
        run_step(
            "controller_packet_answer_feedback_pipeline_regression",
            [python, str(ROOT / "eval" / "controller_packet_answer_feedback_pipeline_regression.py")],
        ),
        run_step(
            "outcome_logging_regression",
            [python, str(ROOT / "eval" / "outcome_logging_regression.py")],
        ),
        run_step(
            "controller_packet_memory_bank_regression",
            [python, str(ROOT / "eval" / "controller_packet_memory_bank_regression.py")],
        ),
        run_step(
            "controller_packet_calibration_proposals_regression",
            [python, str(ROOT / "eval" / "controller_packet_calibration_proposals_regression.py")],
        ),
        run_step(
            "controller_packet_calibration_guard_regression",
            [python, str(ROOT / "eval" / "controller_packet_calibration_guard_regression.py")],
        ),
        run_step(
            "controller_packet_calibration_config_regression",
            [python, str(ROOT / "eval" / "controller_packet_calibration_config_regression.py")],
        ),
        run_step(
            "controller_packet_calibration_runtime_view_regression",
            [python, str(ROOT / "eval" / "controller_packet_calibration_runtime_view_regression.py")],
        ),
        run_step(
            "controller_packet_calibration_pipeline_regression",
            [python, str(ROOT / "eval" / "controller_packet_calibration_pipeline_regression.py")],
        ),
        run_step(
            "controller_packet_multirun_calibration_regression",
            [python, str(ROOT / "eval" / "controller_packet_multirun_calibration_regression.py")],
        ),
        run_step(
            "controller_packet_recurring_holdout_regression",
            [python, str(ROOT / "eval" / "controller_packet_recurring_holdout_regression.py")],
        ),
        run_step(
            "controller_packet_review_separation_regression",
            [python, str(ROOT / "eval" / "controller_packet_review_separation_regression.py")],
        ),
        run_step(
            "controller_packet_bridge_separator_regression",
            [python, str(ROOT / "eval" / "controller_packet_bridge_separator_regression.py")],
        ),
        run_step(
            "controller_packet_bridge_separator_holdout_regression",
            [python, str(ROOT / "eval" / "controller_packet_bridge_separator_holdout_regression.py")],
        ),
        run_step(
            "controller_packet_ogcf_bridge_scorer_regression",
            [python, str(ROOT / "eval" / "controller_packet_ogcf_bridge_scorer_regression.py")],
        ),
        run_step(
            "controller_packet_ogcf_bridge_scorer_feature_regression",
            [python, str(ROOT / "eval" / "controller_packet_ogcf_bridge_scorer_feature_regression.py")],
        ),
        run_step(
            "controller_packet_ogcf_bridge_feature_audit_regression",
            [python, str(ROOT / "eval" / "controller_packet_ogcf_bridge_feature_audit_regression.py")],
        ),
        run_step(
            "controller_packet_ogcf_bridge_source_holdout_regression",
            [python, str(ROOT / "eval" / "controller_packet_ogcf_bridge_source_holdout_regression.py")],
        ),
        run_step(
            "controller_packet_ogcf_bridge_leave_one_source_out_regression",
            [python, str(ROOT / "eval" / "controller_packet_ogcf_bridge_leave_one_source_out_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_behavior_feature_scorer_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_feature_scorer_regression.py")],
        ),
        maybe_artifact_step(
            "adaptive_behavior_feature_scorer_hybrid_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_feature_scorer_hybrid_regression.py")],
        ),
        run_step(
            "adaptive_behavior_feature_challenge_regression",
            [python, str(ROOT / "eval" / "adaptive_behavior_feature_challenge_regression.py")],
        ),
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
