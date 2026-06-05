from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXPERIMENTS = REPO_ROOT / "experiments"
DEFAULT_GATE = EXPERIMENTS / "selector_architecture_gate_results.json"
DEFAULT_VALUATION = EXPERIMENTS / "architecture_valuation_report_results.json"
DEFAULT_DASHBOARD = EXPERIMENTS / "architecture_readiness_dashboard_results.json"
DEFAULT_MERGE_EVAL = EXPERIMENTS / "memory_maintenance_rpg_feedback_merge_evaluation_regression_results.json"
OUT_JSON = EXPERIMENTS / "architecture_transition_map_results.json"
OUT_MD = EXPERIMENTS / "architecture_transition_map.md"


SUBSYSTEMS = [
    {
        "name": "retrieval_controller_context",
        "label": "Retrieval/controller context",
        "stage": "stable_configured_spine",
        "gate_keys": [
            "retrieval_signal_gate_ok",
            "evidence_state_gate_ok",
            "controller_packet_regression_ok",
            "controller_packet_memory_bank_ok",
            "controller_packet_calibration_pipeline_ok",
        ],
        "promotion_blockers": [],
        "next_step": "keep as the shared feature contract for learned/shadow controllers",
    },
    {
        "name": "maintenance_apply_lifecycle",
        "label": "Maintenance apply lifecycle",
        "stage": "operator_gated_rehearsal",
        "gate_keys": [
            "memory_maintenance_apply_plan_ok",
            "memory_maintenance_apply_backend_ok",
            "memory_maintenance_copied_db_rehearsal_ok",
            "memory_maintenance_operator_review_packet_ok",
            "memory_maintenance_operator_outcome_capture_ok",
        ],
        "promotion_blockers": ["real_db_apply_requires_explicit_operator_command"],
        "next_step": "continue feeding reviewed outcomes into report-only label artifacts",
    },
    {
        "name": "rpg_relational_substrate",
        "label": "RPG relational substrate",
        "stage": "diagnostic_report_only",
        "gate_keys": [
            "rpg_relational_substrate_probe_ok",
            "memory_maintenance_rpg_rehearsal_calibration_ok",
            "memory_maintenance_rpg_copied_real_calibration_ok",
            "memory_maintenance_rpg_natural_candidate_calibration_ok",
        ],
        "promotion_blockers": ["rpg_relation_is_not_a_standalone_safety_label"],
        "next_step": "use RPG relation/island features only with symbolic labels and reviewed outcomes",
    },
    {
        "name": "operator_feedback_loop",
        "label": "Operator feedback loop",
        "stage": "feedback_ready_report_only",
        "gate_keys": [
            "memory_maintenance_operator_review_packet_ok",
            "memory_maintenance_operator_outcome_capture_ok",
            "memory_maintenance_operator_outcome_rpg_feedback_ok",
        ],
        "promotion_blockers": ["needs_real_or_hermes_reviewed_outcomes"],
        "next_step": "collect and merge more operator-derived RPG feedback labels",
    },
    {
        "name": "rpg_supervised_learning",
        "label": "RPG supervised learning",
        "stage": "shadow_learning_blocked_by_evidence",
        "gate_keys": [
            "memory_maintenance_rpg_natural_candidate_review_packet_ok",
            "memory_maintenance_rpg_natural_label_bank_ok",
            "memory_maintenance_rpg_label_quality_report_ok",
            "memory_maintenance_rpg_label_scorer_ok",
            "memory_maintenance_rpg_reviewed_label_batch_ok",
            "memory_maintenance_rpg_feedback_merge_evaluation_ok",
        ],
        "promotion_blockers": ["label_diversity_and_external_validation_required"],
        "next_step": "use the reviewed fixture as a scorer sanity check, then grow real labeled packets before policy behavior",
    },
    {
        "name": "adaptive_residual_shadow",
        "label": "Adaptive residual shadow",
        "stage": "learned_veto_shadow_only",
        "gate_keys": [
            "adaptive_residual_shadow_runtime_ok",
            "adaptive_residual_shadow_multi_log_eval_ok",
            "adaptive_residual_learned_risk_veto_ok",
            "adaptive_residual_learned_risk_authority_paraphrase_ok",
        ],
        "promotion_blockers": ["fresh_external_agent_validation_required"],
        "next_step": "keep learned-risk veto report-only until fresh external validation passes",
    },
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def clean_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def required_summary(gate: dict[str, Any]) -> dict[str, Any]:
    summary = gate.get("required_summary")
    return summary if isinstance(summary, dict) else {}


def subsystem_status(summary: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in spec["gate_keys"] if key not in summary]
    failing = [key for key in spec["gate_keys"] if summary.get(key) is not True]
    return {
        "schema": "architecture_transition_subsystem/v1",
        "name": spec["name"],
        "label": spec["label"],
        "stage": spec["stage"],
        "ok": not missing and not failing,
        "gate_keys": {key: bool(summary.get(key)) for key in spec["gate_keys"]},
        "missing_gate_keys": missing,
        "failing_gate_keys": failing,
        "promotion_blockers": list(spec["promotion_blockers"]),
        "next_step": spec["next_step"],
    }


def merge_details(merge_eval: dict[str, Any]) -> dict[str, Any]:
    evaluation = merge_eval.get("evaluation")
    if not isinstance(evaluation, dict):
        return {}
    comparison = evaluation.get("comparison") if isinstance(evaluation.get("comparison"), dict) else {}
    combined = evaluation.get("combined") if isinstance(evaluation.get("combined"), dict) else {}
    summary = combined.get("summary") if isinstance(combined.get("summary"), dict) else {}
    return {
        "schema": "architecture_transition_merge_details/v1",
        "label_gain_from_operator_feedback": comparison.get("label_gain_from_operator_feedback"),
        "operator_feedback_materially_improves_training_evidence": comparison.get(
            "operator_feedback_materially_improves_training_evidence"
        ),
        "combined_labeled_count": summary.get("labeled_count"),
        "combined_quality_ready_for_shadow": summary.get("quality_ready_for_shadow"),
        "combined_scorer_ready_for_shadow": summary.get("scorer_ready_for_shadow"),
        "combined_scorer_ready_for_policy": summary.get("scorer_ready_for_policy"),
    }


def build_transition_map(
    gate: dict[str, Any],
    valuation: dict[str, Any],
    dashboard: dict[str, Any],
    merge_eval: dict[str, Any],
) -> dict[str, Any]:
    summary = required_summary(gate)
    subsystems = [subsystem_status(summary, spec) for spec in SUBSYSTEMS]
    policy_boundary = valuation.get("policy_boundary") if isinstance(valuation.get("policy_boundary"), dict) else {}
    merge = merge_details(merge_eval)
    hard_blockers = []
    if policy_boundary.get("runtime_policy_mutation_allowed") is not False:
        hard_blockers.append("runtime_policy_boundary_not_explicitly_blocked")
    if policy_boundary.get("real_db_mutation_allowed_by_default") is not False:
        hard_blockers.append("real_db_mutation_boundary_not_explicitly_blocked")
    if policy_boundary.get("rpg_policy_use_allowed") is not False:
        hard_blockers.append("rpg_policy_boundary_not_explicitly_blocked")
    if merge.get("combined_scorer_ready_for_policy") is True:
        hard_blockers.append("unexpected_rpg_policy_ready_signal")
    blocked_subsystems = [item["name"] for item in subsystems if not item["ok"]]
    return {
        "schema": "architecture_transition_map/v1",
        "description": "Report-only neural-symbolic transition map for the combined memory and selector architecture.",
        "architecture_gate_ok": bool(gate.get("ok")),
        "architecture_valuation_ok": bool(valuation.get("ok")),
        "architecture_dashboard_ready": bool(dashboard.get("handover_ready")),
        "subsystems": subsystems,
        "blocked_subsystems": blocked_subsystems,
        "hard_blockers": hard_blockers,
        "merge_evidence": merge,
        "transition_state": "stable_report_only_learning_loop"
        if not blocked_subsystems and not hard_blockers
        else "resolve_transition_blockers",
        "policy_readiness": {
            "runtime_policy_mutation_allowed": False,
            "real_db_mutation_allowed_by_default": False,
            "rpg_policy_use_allowed": False,
            "learned_signals_allowed_as_shadow_or_explanation": True,
        },
        "recommended_next_development": "collect_reviewed_rpg_labels_and_recheck_label_quality"
        if not blocked_subsystems and not hard_blockers
        else "fix_transition_map_blockers_before_new_learning_work",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
        "ok": bool(gate.get("ok"))
        and bool(valuation.get("ok"))
        and not blocked_subsystems
        and not hard_blockers
        and dashboard.get("handover_ready") is not False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Transition Map",
        "",
        "Report-only neural-symbolic transition map for the combined memory and selector architecture.",
        "",
        f"Transition state: `{report['transition_state']}`",
        f"OK: `{report['ok']}`",
        f"Recommended next development: `{report['recommended_next_development']}`",
        "",
        "## Subsystems",
        "",
        "| subsystem | stage | ok | promotion blockers | next step |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.get("subsystems") or []:
        lines.append(
            f"| `{clean_cell(item.get('label'), 50)}` | `{clean_cell(item.get('stage'), 50)}` | "
            f"`{item.get('ok')}` | `{clean_cell(', '.join(item.get('promotion_blockers') or []), 90)}` | "
            f"{clean_cell(item.get('next_step'), 110)} |"
        )
    lines.extend(
        [
            "",
            "## Merge Evidence",
            "",
            "```json",
            json.dumps(report.get("merge_evidence"), indent=2),
            "```",
            "",
            "## Policy Readiness",
            "",
            "```json",
            json.dumps(report.get("policy_readiness"), indent=2),
            "```",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report-only architecture transition map.")
    parser.add_argument("--gate", default=str(DEFAULT_GATE))
    parser.add_argument("--valuation", default=str(DEFAULT_VALUATION))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    parser.add_argument("--merge-eval", default=str(DEFAULT_MERGE_EVAL))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_transition_map(
        read_json(Path(args.gate)),
        read_json(Path(args.valuation)),
        read_json(Path(args.dashboard)),
        read_json(Path(args.merge_eval)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "transition_state": report["transition_state"],
                "recommended_next_development": report["recommended_next_development"],
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
