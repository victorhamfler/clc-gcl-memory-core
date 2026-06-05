from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXPERIMENTS = REPO_ROOT / "experiments"
OUT_JSON = EXPERIMENTS / "architecture_valuation_report_results.json"
OUT_MD = EXPERIMENTS / "architecture_valuation_report.md"


ARTIFACTS = {
    "architecture_gate": EXPERIMENTS / "selector_architecture_gate_results.json",
    "rpg_probe": EXPERIMENTS / "rpg_relational_substrate_probe_regression_results.json",
    "rpg_copied_real": EXPERIMENTS / "memory_maintenance_rpg_copied_real_calibration_results.json",
    "rpg_natural_candidates": EXPERIMENTS / "memory_maintenance_rpg_natural_candidate_calibration_results.json",
    "rpg_review_packet": EXPERIMENTS / "memory_maintenance_rpg_natural_candidate_review_packet_regression_results.json",
    "rpg_label_bank": EXPERIMENTS / "memory_maintenance_rpg_natural_label_bank_regression_results.json",
    "rpg_label_scorer": EXPERIMENTS / "memory_maintenance_rpg_label_scorer_regression_results.json",
    "rpg_label_quality": EXPERIMENTS / "memory_maintenance_rpg_label_quality_report_regression_results.json",
    "operator_packet": EXPERIMENTS / "memory_maintenance_operator_review_packet_regression_results.json",
    "operator_outcome_capture": EXPERIMENTS / "memory_maintenance_operator_outcome_capture_regression_results.json",
    "operator_outcome_rpg_feedback": EXPERIMENTS
    / "memory_maintenance_operator_outcome_rpg_feedback_regression_results.json",
    "rpg_feedback_merge_evaluation": EXPERIMENTS
    / "memory_maintenance_rpg_feedback_merge_evaluation_regression_results.json",
    "architecture_readiness_dashboard": EXPERIMENTS / "architecture_readiness_dashboard_regression_results.json",
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


def gate_ok(gate: dict[str, Any], key: str) -> bool:
    return bool((gate.get("required_summary") or {}).get(key))


def phase_key_ok(gate: dict[str, Any], artifacts: dict[str, dict[str, Any]], key: str) -> bool:
    if gate_ok(gate, key):
        return True
    artifact_fallbacks = {
        "memory_maintenance_rpg_label_quality_report_ok": "rpg_label_quality",
        "memory_maintenance_operator_outcome_capture_ok": "operator_outcome_capture",
        "memory_maintenance_operator_outcome_rpg_feedback_ok": "operator_outcome_rpg_feedback",
        "memory_maintenance_rpg_feedback_merge_evaluation_ok": "rpg_feedback_merge_evaluation",
    }
    artifact_name = artifact_fallbacks.get(key)
    return bool(artifact_name and artifacts.get(artifact_name, {}).get("ok"))


def build_report() -> dict[str, Any]:
    artifacts = {name: read_json(path) for name, path in ARTIFACTS.items()}
    gate = artifacts["architecture_gate"]
    copied_real = artifacts["rpg_copied_real"]
    natural = artifacts["rpg_natural_candidates"]
    label_scorer = artifacts["rpg_label_scorer"]
    label_quality = artifacts["rpg_label_quality"]
    scorer = label_scorer.get("scorer") if isinstance(label_scorer.get("scorer"), dict) else {}
    quality = label_quality.get("good_report") if isinstance(label_quality.get("good_report"), dict) else {}
    copied_calibration = copied_real.get("calibration") if isinstance(copied_real.get("calibration"), dict) else {}
    natural_report = natural.get("natural_candidate_report")
    if not isinstance(natural_report, dict):
        natural_report = natural

    phases = [
        {
            "phase": "retrieval_and_controller_context",
            "status": "stable",
            "gate_keys": [
                "evidence_context_selector_runtime_ok",
                "controller_packet_regression_ok",
                "controller_packet_memory_bank_ok",
                "controller_packet_calibration_pipeline_ok",
            ],
            "role": "shared adaptive-memory context and selector calibration spine",
        },
        {
            "phase": "maintenance_apply_lifecycle",
            "status": "safe_report_only_with_copied_db_rehearsal",
            "gate_keys": [
                "memory_maintenance_apply_plan_ok",
                "memory_maintenance_apply_backend_ok",
                "memory_maintenance_copied_db_rehearsal_ok",
                "memory_maintenance_operator_review_packet_ok",
                "memory_maintenance_operator_outcome_capture_ok",
            ],
            "role": "manual review, dry-run apply planning, copied-DB rehearsal, operator packet, and operator outcome capture",
        },
        {
            "phase": "rpg_relational_substrate",
            "status": "diagnostic_active",
            "gate_keys": [
                "rpg_relational_substrate_probe_ok",
                "memory_maintenance_rpg_rehearsal_calibration_ok",
                "memory_maintenance_rpg_copied_real_calibration_ok",
                "memory_maintenance_rpg_natural_candidate_calibration_ok",
            ],
            "role": "RPG relation/island/activity diagnostics for memory maintenance candidates",
        },
        {
            "phase": "rpg_supervised_learning_path",
            "status": "data_collection_ready_but_policy_blocked",
            "gate_keys": [
                "memory_maintenance_rpg_natural_candidate_review_packet_ok",
                "memory_maintenance_rpg_natural_label_bank_ok",
                "memory_maintenance_rpg_label_scorer_ok",
                "memory_maintenance_rpg_label_quality_report_ok",
                "memory_maintenance_operator_outcome_rpg_feedback_ok",
                "memory_maintenance_rpg_feedback_merge_evaluation_ok",
            ],
            "role": "review packet, label bank, label-quality audit, operator-feedback bridge, merge evaluation, transparent scorer, and readiness blockers",
        },
    ]
    for phase in phases:
        phase["gate_ok"] = all(phase_key_ok(gate, artifacts, key) for key in phase["gate_keys"])

    natural_summary = natural_report.get("candidate_class_summary") or {}
    copied_safe_relation = float(copied_calibration.get("safe_relation_mean") or 0.0)
    copied_blocked_relation = float(copied_calibration.get("blocked_relation_mean") or 0.0)
    scorer_payload = scorer if scorer else label_scorer.get("scorer", {})
    if not isinstance(scorer_payload, dict):
        scorer_payload = {}

    findings = [
        "The architecture gate is currently green across retrieval, evidence, controller packet, maintenance lifecycle, OGCF/ERG, RPG, and adaptive behavior/residual paths.",
        "The maintenance mutation path is intentionally still operator-gated and rehearsal-first; copied DB tests and operator packets exist, but policy and real DB mutation remain blocked by default.",
        "RPG has matured from a standalone relational-substrate probe into a full report-only evidence lifecycle: probe, rehearsal annotation, repeated-run aggregation, copied-real calibration, natural candidate mining, review packet, label bank, and transparent scorer.",
        "The new RPG label-quality audit separates label collection readiness from scorer mechanics; this prevents sparse or collapsed labels from being treated as learning evidence.",
        "Operator packet outcomes can now be captured as non-mutating feedback, preserving RPG context and producing training labels for later review-loop integration.",
        "Operator outcome feedback can now be converted into an RPG label-bank-compatible packet, closing the first report-only supervised feedback loop.",
        "Natural and operator-derived RPG labels can now be compared as separate and merged banks before any scorer or policy promotion is considered.",
        "Natural candidate calibration showed an important constraint: high RPG target relation can indicate stale/update attractors or bridge-like relation, not only safe duplicate quality.",
        "The RPG scorer exists but correctly remains blocked because the label set is sparse and synthetic; the next real requirement is labeled natural RPG review packets.",
    ]
    risks = [
        "The eval layer is now large and contains many research-stage pipelines; without periodic consolidation, it will become hard to maintain.",
        "Several RPG components are intentionally report-only and should not be mistaken for policy-ready learned behavior.",
        "Natural RPG candidate classes are heuristic until reviewed labels are collected.",
        "Label quality can fail from sparse labels, class imbalance, or contradictory pair labels even when the label bank script itself passes.",
        "Operator outcome capture is still a feedback artifact only; it needs an explicit label-bank feedback integration before it becomes training data.",
        "Operator-derived RPG feedback still needs label-quality rechecks before scorer promotion.",
        "Merged label-bank improvement is currently an evaluation signal only; it does not bypass real outcome validation.",
        "The current scorer regression proves the safety boundary more than predictive strength; real label data is needed.",
    ]
    next_steps = [
        {
            "priority": 1,
            "step": "Collect labels for the RPG natural candidate review packet using Hermes or manual review.",
            "owner": "Hermes_or_user_review",
            "why": "The scorer and policy path are blocked by label scarcity, not by code structure.",
        },
        {
            "priority": 2,
            "step": "Create a compact architecture status document or dashboard from this valuation for future handovers.",
            "owner": "selector_session",
            "why": "The codebase now needs a standing map of readiness boundaries and evidence artifacts.",
        },
        {
            "priority": 3,
            "step": "Keep memory-program integration separate but coordinated through handover docs and shared artifact schemas.",
            "owner": "both_sessions",
            "why": "Selector/RPG development and memory-store/API development are coupled by contracts, not by one monolithic session.",
        },
    ]
    return {
        "schema": "architecture_valuation_report/v1",
        "ok": all(phase["gate_ok"] for phase in phases),
        "description": "Current architecture valuation for the CLC-GCL selector, memory maintenance, OGCF/ERG, and RPG adaptive memory paths.",
        "artifact_paths": {name: str(path) for name, path in ARTIFACTS.items()},
        "phases": phases,
        "readiness": {
            "architecture_gate_ok": bool(gate.get("ok")),
            "copied_real_safe_relation_mean": copied_safe_relation,
            "copied_real_blocked_relation_mean": copied_blocked_relation,
            "copied_real_relation_separation_positive": copied_safe_relation > copied_blocked_relation,
            "natural_candidate_class_summary": natural_summary,
            "rpg_scorer_ready_for_shadow": bool((scorer_payload or {}).get("ready_for_shadow_scorer")),
            "rpg_scorer_ready_for_policy": bool((scorer_payload or {}).get("ready_for_policy_use")),
            "rpg_scorer_blockers": (scorer_payload or {}).get("promotion_blockers") or [],
            "rpg_label_quality_ready_for_shadow": bool((quality or {}).get("ready_for_shadow_scorer_training")),
            "rpg_label_quality_blockers": (quality or {}).get("promotion_blockers") or [],
            "operator_outcome_capture_ok": bool(artifacts["operator_outcome_capture"].get("ok")),
            "operator_outcome_rpg_feedback_ok": bool(artifacts["operator_outcome_rpg_feedback"].get("ok")),
            "rpg_feedback_merge_evaluation_ok": bool(artifacts["rpg_feedback_merge_evaluation"].get("ok")),
            "architecture_readiness_dashboard_ok": bool(artifacts["architecture_readiness_dashboard"].get("ok")),
        },
        "findings": findings,
        "risks": risks,
        "recommended_next_steps": next_steps,
        "policy_boundary": {
            "runtime_policy_mutation_allowed": False,
            "real_db_mutation_allowed_by_default": False,
            "rpg_policy_use_allowed": False,
            "reason": "label scarcity and real outcome validation are still blockers",
        },
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Architecture Valuation Report",
        "",
        "Current valuation of the combined selector, memory maintenance, OGCF/ERG, and RPG adaptive memory architecture.",
        "",
        f"Architecture OK: `{report['ok']}`",
        f"RPG shadow scorer ready: `{report['readiness']['rpg_scorer_ready_for_shadow']}`",
        f"RPG policy ready: `{report['readiness']['rpg_scorer_ready_for_policy']}`",
        "",
        "## Phases",
        "",
        "| phase | status | gate ok | role |",
        "| --- | --- | --- | --- |",
    ]
    for phase in report.get("phases") or []:
        lines.append(
            f"| `{clean_cell(phase.get('phase'), 60)}` | `{clean_cell(phase.get('status'), 60)}` | "
            f"`{phase.get('gate_ok')}` | {clean_cell(phase.get('role'), 120)} |"
        )
    lines.extend(["", "## Findings", ""])
    for finding in report.get("findings") or []:
        lines.append(f"- {finding}")
    lines.extend(["", "## Risks", ""])
    for risk in report.get("risks") or []:
        lines.append(f"- {risk}")
    lines.extend(["", "## Recommended Next Steps", ""])
    for item in report.get("recommended_next_steps") or []:
        lines.append(f"{item['priority']}. {item['step']}  ")
        lines.append(f"   Owner: `{item['owner']}`. Why: {item['why']}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report-only architecture valuation.")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report()
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
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
