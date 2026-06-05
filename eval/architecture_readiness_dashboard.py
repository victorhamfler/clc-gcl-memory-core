from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO_ROOT / "experiments"
DEFAULT_GATE = EXPERIMENTS / "selector_architecture_gate_results.json"
DEFAULT_VALUATION = EXPERIMENTS / "architecture_valuation_report_results.json"
DEFAULT_MERGE_EVAL = EXPERIMENTS / "memory_maintenance_rpg_feedback_merge_evaluation_regression_results.json"
OUT_JSON = EXPERIMENTS / "architecture_readiness_dashboard_results.json"
OUT_MD = EXPERIMENTS / "architecture_readiness_dashboard.md"


CHAINS = [
    {
        "name": "retrieval_controller",
        "label": "Retrieval and controller",
        "keys": [
            "retrieval_signal_gate_ok",
            "evidence_state_gate_ok",
            "controller_packet_regression_ok",
            "controller_packet_memory_bank_ok",
            "controller_packet_calibration_pipeline_ok",
        ],
        "policy": "stable_context_spine",
    },
    {
        "name": "rpg_diagnostics",
        "label": "RPG diagnostics",
        "keys": [
            "rpg_relational_substrate_probe_ok",
            "memory_maintenance_rpg_rehearsal_calibration_ok",
            "memory_maintenance_rpg_copied_real_calibration_ok",
            "memory_maintenance_rpg_natural_candidate_calibration_ok",
        ],
        "policy": "diagnostic_only",
    },
    {
        "name": "maintenance_rehearsal",
        "label": "Maintenance rehearsal",
        "keys": [
            "memory_maintenance_apply_plan_ok",
            "memory_maintenance_apply_backend_ok",
            "memory_maintenance_copied_db_rehearsal_ok",
            "memory_maintenance_rich_copied_db_target_quality_ok",
            "memory_maintenance_rehearsal_candidate_guard_ok",
        ],
        "policy": "copied_db_rehearsal_only",
    },
    {
        "name": "operator_feedback",
        "label": "Operator feedback loop",
        "keys": [
            "memory_maintenance_operator_review_packet_ok",
            "memory_maintenance_operator_outcome_capture_ok",
            "memory_maintenance_operator_outcome_rpg_feedback_ok",
        ],
        "policy": "operator_review_report_only",
    },
    {
        "name": "rpg_learning",
        "label": "RPG supervised learning",
        "keys": [
            "memory_maintenance_rpg_natural_candidate_review_packet_ok",
            "memory_maintenance_rpg_natural_label_bank_ok",
            "memory_maintenance_rpg_label_quality_report_ok",
            "memory_maintenance_rpg_label_scorer_ok",
            "memory_maintenance_rpg_feedback_merge_evaluation_ok",
        ],
        "policy": "shadow_learning_only",
    },
]


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


def chain_status(summary: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in chain["keys"] if key not in summary]
    failing = [key for key in chain["keys"] if summary.get(key) is not True]
    return {
        "schema": "architecture_readiness_chain_status/v1",
        "name": chain["name"],
        "label": chain["label"],
        "ok": not failing and not missing,
        "policy": chain["policy"],
        "key_count": len(chain["keys"]),
        "missing_keys": missing,
        "failing_keys": failing,
        "keys": {key: bool(summary.get(key)) for key in chain["keys"]},
    }


def merge_summary(merge_eval_regression: dict[str, Any]) -> dict[str, Any]:
    evaluation = merge_eval_regression.get("evaluation")
    if not isinstance(evaluation, dict):
        return {}
    comparison = evaluation.get("comparison") if isinstance(evaluation.get("comparison"), dict) else {}
    combined = evaluation.get("combined") if isinstance(evaluation.get("combined"), dict) else {}
    combined_summary = combined.get("summary") if isinstance(combined.get("summary"), dict) else {}
    return {
        "schema": "architecture_readiness_merge_summary/v1",
        "ok": bool(merge_eval_regression.get("ok")),
        "label_gain_from_operator_feedback": comparison.get("label_gain_from_operator_feedback"),
        "operator_feedback_materially_improves_training_evidence": comparison.get(
            "operator_feedback_materially_improves_training_evidence"
        ),
        "combined_labeled_count": combined_summary.get("labeled_count"),
        "combined_quality_ready_for_shadow": combined_summary.get("quality_ready_for_shadow"),
        "combined_scorer_ready_for_shadow": combined_summary.get("scorer_ready_for_shadow"),
        "combined_scorer_ready_for_policy": combined_summary.get("scorer_ready_for_policy"),
        "family_prediction_accuracy_delta": comparison.get("family_prediction_accuracy_delta"),
        "scorer_leave_one_out_accuracy_delta": comparison.get("scorer_leave_one_out_accuracy_delta"),
    }


def build_dashboard(gate: dict[str, Any], valuation: dict[str, Any], merge_eval_regression: dict[str, Any]) -> dict[str, Any]:
    summary = gate.get("required_summary") if isinstance(gate.get("required_summary"), dict) else {}
    chains = [chain_status(summary, chain) for chain in CHAINS]
    policy_boundary = valuation.get("policy_boundary") if isinstance(valuation.get("policy_boundary"), dict) else {}
    merge = merge_summary(merge_eval_regression)
    hard_blockers = []
    if policy_boundary.get("runtime_policy_mutation_allowed") is not False:
        hard_blockers.append("runtime_policy_boundary_not_explicitly_blocked")
    if policy_boundary.get("real_db_mutation_allowed_by_default") is not False:
        hard_blockers.append("real_db_mutation_boundary_not_explicitly_blocked")
    if policy_boundary.get("rpg_policy_use_allowed") is not False:
        hard_blockers.append("rpg_policy_boundary_not_explicitly_blocked")
    if merge.get("combined_scorer_ready_for_policy") is True:
        hard_blockers.append("unexpected_policy_ready_scorer")
    all_chains_ok = all(item["ok"] for item in chains)
    return {
        "schema": "architecture_readiness_dashboard/v1",
        "description": "Compact readiness dashboard for the combined selector, memory maintenance, RPG, and operator-feedback architecture.",
        "architecture_gate_ok": bool(gate.get("ok")),
        "architecture_valuation_ok": bool(valuation.get("ok")),
        "chain_count": len(chains),
        "chains_ok": all_chains_ok,
        "chains": chains,
        "merge_evaluation": merge,
        "policy_boundary": {
            "runtime_policy_mutation_allowed": False,
            "real_db_mutation_allowed_by_default": False,
            "rpg_policy_use_allowed": False,
            "real_db_apply_requires_operator_command": True,
            "rpg_signals_are_explanation_or_shadow_only": True,
        },
        "hard_blockers": hard_blockers,
        "handover_ready": bool(gate.get("ok")) and bool(valuation.get("ok")) and all_chains_ok and not hard_blockers,
        "github_upload_ready": bool(gate.get("ok")) and bool(valuation.get("ok")) and all_chains_ok and not hard_blockers,
        "next_action": "handover_or_upload_ready"
        if bool(gate.get("ok")) and bool(valuation.get("ok")) and all_chains_ok and not hard_blockers
        else "resolve_architecture_readiness_blockers",
        "recommended_next_development": "collect_real_or_hermes_operator_feedback_and_recheck_merge_evaluation",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(dashboard: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    merge = dashboard.get("merge_evaluation") or {}
    lines = [
        "# Architecture Readiness Dashboard",
        "",
        "Compact readiness dashboard for the combined selector, memory maintenance, RPG, and operator-feedback architecture.",
        "",
        f"Architecture gate OK: `{dashboard['architecture_gate_ok']}`",
        f"Architecture valuation OK: `{dashboard['architecture_valuation_ok']}`",
        f"Chains OK: `{dashboard['chains_ok']}`",
        f"Handover ready: `{dashboard['handover_ready']}`",
        f"GitHub upload ready: `{dashboard['github_upload_ready']}`",
        f"Next action: `{dashboard['next_action']}`",
        "",
        "## Chains",
        "",
        "| chain | ok | policy | failing |",
        "| --- | --- | --- | --- |",
    ]
    for chain in dashboard.get("chains") or []:
        lines.append(
            f"| `{clean_cell(chain.get('label'), 60)}` | `{chain.get('ok')}` | "
            f"`{clean_cell(chain.get('policy'), 70)}` | `{clean_cell(', '.join(chain.get('failing_keys') or []), 100)}` |"
        )
    lines.extend(
        [
            "",
            "## RPG Feedback Merge",
            "",
            f"Label gain from operator feedback: `{merge.get('label_gain_from_operator_feedback')}`",
            f"Material improvement: `{merge.get('operator_feedback_materially_improves_training_evidence')}`",
            f"Combined labeled count: `{merge.get('combined_labeled_count')}`",
            f"Combined scorer policy ready: `{merge.get('combined_scorer_ready_for_policy')}`",
            "",
            "## Policy Boundary",
            "",
            "```json",
            json.dumps(dashboard.get("policy_boundary"), indent=2),
            "```",
            "",
            "## Next Development",
            "",
            f"`{dashboard['recommended_next_development']}`",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact architecture readiness dashboard.")
    parser.add_argument("--gate", default=str(DEFAULT_GATE))
    parser.add_argument("--valuation", default=str(DEFAULT_VALUATION))
    parser.add_argument("--merge-eval", default=str(DEFAULT_MERGE_EVAL))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    dashboard = build_dashboard(
        read_json(Path(args.gate)),
        read_json(Path(args.valuation)),
        read_json(Path(args.merge_eval)),
    )
    write_report(dashboard, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": dashboard["schema"],
                "handover_ready": dashboard["handover_ready"],
                "github_upload_ready": dashboard["github_upload_ready"],
                "next_action": dashboard["next_action"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
