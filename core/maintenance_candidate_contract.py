from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


GUARD_SCHEMA = "ogcf_maintenance_candidate_guard/v1"
CANDIDATE_SCHEMA = "ogcf_guarded_maintenance_candidate/v1"
PLAN_SCHEMA = "memory_maintenance_candidate_review_plan/v1"
OUTCOME_SCHEMA = "memory_maintenance_candidate_review_outcomes/v1"
OUTCOME_SUMMARY_SCHEMA = "memory_maintenance_candidate_review_outcome_summary/v1"
APPLY_DECISION_SCHEMA = "memory_maintenance_manual_apply_decisions/v1"
APPLY_PLAN_SCHEMA = "memory_maintenance_apply_plan/v1"

ALLOWED_OUTCOMES = {
    "accept",
    "reject",
    "needs_more_evidence",
    "unsafe_to_apply",
    "already_resolved",
}

ACTION_TO_MEMORY_REVIEW_KIND = {
    "exact_duplicate_group": "duplicate_deprecation_review",
    "semantic_duplicate_group": "semantic_merge_review",
    "semantic_conflict_or_update_group": "conflict_update_review",
    "stale_version_candidate": "stale_deprecation_review",
    "bridge_cluster_review": "bridge_split_or_canonicalization_review",
}


@dataclass(frozen=True)
class MaintenanceReviewPlanItem:
    candidate_id: str
    source_cluster_key: str
    action: str
    memory_review_kind: str
    recommended_action: str
    run_count: int
    support: int
    mean_priority: float
    max_priority: float
    ready_for_manual_review: bool
    promotion_ready: bool
    blocked_reasons: tuple[str, ...]
    promotion_blockers: tuple[str, ...]
    example_memory_ids: tuple[str, ...]


def _string(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()
    return tuple(_string(item) for item in values if _string(item))


def _example_memory_ids(candidate: dict[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for example in candidate.get("examples") or []:
        if not isinstance(example, dict):
            continue
        for key in ("candidate_id", "keeper_memory_id"):
            value = _string(example.get(key))
            if value and value not in ids:
                ids.append(value)
    return tuple(ids)


def normalize_guarded_candidate(candidate: dict[str, Any]) -> MaintenanceReviewPlanItem:
    action = _string(candidate.get("action")) or "unknown"
    return MaintenanceReviewPlanItem(
        candidate_id=_string(candidate.get("id")),
        source_cluster_key=_string(candidate.get("source_cluster_key")),
        action=action,
        memory_review_kind=ACTION_TO_MEMORY_REVIEW_KIND.get(action, "manual_maintenance_review"),
        recommended_action=_string(candidate.get("recommended_action")) or "manual_maintenance_review_required",
        run_count=_int(candidate.get("run_count")),
        support=_int(candidate.get("support")),
        mean_priority=round(_float(candidate.get("mean_priority")), 6),
        max_priority=round(_float(candidate.get("max_priority")), 6),
        ready_for_manual_review=bool(candidate.get("ready_for_manual_review")),
        promotion_ready=bool(candidate.get("promotion_ready")),
        blocked_reasons=_strings(candidate.get("blocked_reasons")),
        promotion_blockers=_strings(candidate.get("promotion_blockers")),
        example_memory_ids=_example_memory_ids(candidate),
    )


def build_review_plan(guard: dict[str, Any]) -> dict[str, Any]:
    """Convert an OGCF guard artifact into a memory-side manual review plan.

    This is the shared handoff contract between selector/ERG maintenance
    evidence and the memory program. It is intentionally non-mutating.
    """

    candidates = [
        normalize_guarded_candidate(item)
        for item in guard.get("guarded_candidates") or []
        if isinstance(item, dict) and item.get("schema") == CANDIDATE_SCHEMA
    ]
    blocked = [
        normalize_guarded_candidate(item)
        for item in guard.get("blocked_candidates") or []
        if isinstance(item, dict) and item.get("schema") == CANDIDATE_SCHEMA
    ]
    kind_counts = Counter(item.memory_review_kind for item in candidates)
    blocked_kind_counts = Counter(item.memory_review_kind for item in blocked)
    return {
        "schema": PLAN_SCHEMA,
        "source_guard_schema": guard.get("schema"),
        "source_guard_ok": guard.get("schema") == GUARD_SCHEMA,
        "candidate_count": len(candidates),
        "blocked_count": len(blocked),
        "memory_review_kind_counts": dict(sorted(kind_counts.items())),
        "blocked_review_kind_counts": dict(sorted(blocked_kind_counts.items())),
        "items": [asdict(item) for item in candidates],
        "blocked_items": [asdict(item) for item in blocked],
        "next_action": "manual_review_memory_maintenance_candidates"
        if candidates
        else "collect_more_reviewed_maintenance_runs",
        "promotion_ready": False,
        "promotion_blockers": ["manual_review_required", "memory_mutation_path_not_enabled"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def normalize_review_outcomes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        outcomes = raw.get("outcomes")
        if isinstance(outcomes, list):
            return [item for item in outcomes if isinstance(item, dict)]
        if raw.get("candidate_id"):
            return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def build_outcome_template(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": OUTCOME_SCHEMA,
        "source_plan_schema": plan.get("schema"),
        "allowed_outcomes": sorted(ALLOWED_OUTCOMES),
        "outcomes": [
            {
                "candidate_id": item.get("candidate_id"),
                "memory_review_kind": item.get("memory_review_kind"),
                "outcome": "",
                "reviewer": "",
                "reason": "",
                "apply_note": "",
            }
            for item in plan.get("items") or []
        ],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def summarize_review_outcomes(plan: dict[str, Any], outcomes_raw: Any) -> dict[str, Any]:
    outcomes = normalize_review_outcomes(outcomes_raw)
    by_id = {str(item.get("candidate_id") or ""): item for item in plan.get("items") or []}
    counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    unknown_candidate_ids: list[str] = []
    invalid_outcomes: list[dict[str, Any]] = []
    normalized = []
    for outcome in outcomes:
        candidate_id = _string(outcome.get("candidate_id"))
        label = _string(outcome.get("outcome")).lower()
        if candidate_id not in by_id:
            unknown_candidate_ids.append(candidate_id)
        if label not in ALLOWED_OUTCOMES:
            invalid_outcomes.append({"candidate_id": candidate_id, "outcome": label})
        plan_item = by_id.get(candidate_id) or {}
        review_kind = _string(outcome.get("memory_review_kind")) or _string(plan_item.get("memory_review_kind"))
        counts[label or "missing"] += 1
        if review_kind:
            kind_counts[f"{review_kind}|{label or 'missing'}"] += 1
        normalized.append(
            {
                "candidate_id": candidate_id,
                "memory_review_kind": review_kind,
                "outcome": label,
                "reviewer": _string(outcome.get("reviewer")),
                "reason": _string(outcome.get("reason")),
                "apply_note": _string(outcome.get("apply_note")),
                "known_candidate": candidate_id in by_id,
                "valid_outcome": label in ALLOWED_OUTCOMES,
            }
        )
    accepted = counts.get("accept", 0)
    rejected = counts.get("reject", 0) + counts.get("unsafe_to_apply", 0)
    readiness = "ready_for_manual_apply_path_review" if accepted and not rejected and not invalid_outcomes else "review_outcomes_need_analysis"
    if not outcomes:
        readiness = "collect_review_outcomes"
    return {
        "schema": OUTCOME_SUMMARY_SCHEMA,
        "source_plan_schema": plan.get("schema"),
        "outcome_count": len(outcomes),
        "known_outcome_count": sum(1 for item in normalized if item["known_candidate"]),
        "unknown_candidate_ids": unknown_candidate_ids,
        "invalid_outcomes": invalid_outcomes,
        "outcome_counts": dict(sorted(counts.items())),
        "review_kind_outcome_counts": dict(sorted(kind_counts.items())),
        "accepted_count": accepted,
        "blocked_or_rejected_count": rejected,
        "readiness": readiness,
        "next_action": "design_manual_apply_reject_logging_endpoint"
        if readiness == "ready_for_manual_apply_path_review"
        else "collect_or_review_more_outcomes",
        "outcomes": normalized,
        "promotion_ready": False,
        "promotion_blockers": ["manual_apply_path_not_implemented", "database_mutation_not_allowed"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_manual_apply_decisions(plan: dict[str, Any], outcomes_raw: Any, *, dry_run: bool = True) -> dict[str, Any]:
    """Build auditable manual apply/reject decisions without changing memory rows."""

    outcomes = summarize_review_outcomes(plan, outcomes_raw)
    by_id = {str(item.get("candidate_id") or ""): item for item in plan.get("items") or []}
    decisions = []
    for outcome in outcomes.get("outcomes") or []:
        candidate_id = _string(outcome.get("candidate_id"))
        plan_item = by_id.get(candidate_id) or {}
        label = _string(outcome.get("outcome")).lower()
        if label == "accept":
            decision = "ready_for_manual_apply"
            next_action = "manual_apply_requires_explicit_operator_command"
            blockers = ["dry_run_enabled"] if dry_run else ["apply_backend_not_implemented"]
        elif label in {"reject", "unsafe_to_apply"}:
            decision = "manual_reject_logged"
            next_action = "preserve_memory_state_and_record_rejection"
            blockers = []
        elif label == "already_resolved":
            decision = "manual_noop_logged"
            next_action = "preserve_memory_state_already_resolved"
            blockers = []
        else:
            decision = "hold_for_more_evidence"
            next_action = "collect_more_review_evidence"
            blockers = ["insufficient_manual_evidence"]
        decisions.append(
            {
                "schema": "memory_maintenance_manual_apply_decision/v1",
                "candidate_id": candidate_id,
                "memory_review_kind": outcome.get("memory_review_kind") or plan_item.get("memory_review_kind"),
                "outcome": label,
                "decision": decision,
                "recommended_action": plan_item.get("recommended_action"),
                "next_action": next_action,
                "blockers": blockers,
                "reviewer": outcome.get("reviewer"),
                "reason": outcome.get("reason"),
                "apply_note": outcome.get("apply_note"),
                "example_memory_ids": plan_item.get("example_memory_ids") or [],
                "known_candidate": outcome.get("known_candidate") is True,
                "valid_outcome": outcome.get("valid_outcome") is True,
                "dry_run": bool(dry_run),
                "applied": False,
                "report_only": True,
                "mutates_db": False,
            }
        )
    ready = [item for item in decisions if item["decision"] == "ready_for_manual_apply"]
    rejected = [item for item in decisions if item["decision"] == "manual_reject_logged"]
    held = [item for item in decisions if item["decision"] == "hold_for_more_evidence"]
    return {
        "schema": APPLY_DECISION_SCHEMA,
        "source_plan_schema": plan.get("schema"),
        "source_outcome_summary_schema": outcomes.get("schema"),
        "decision_count": len(decisions),
        "ready_for_manual_apply_count": len(ready),
        "rejected_count": len(rejected),
        "held_count": len(held),
        "decisions": decisions,
        "outcome_summary": outcomes,
        "next_action": "operator_review_ready_apply_decisions"
        if ready
        else "collect_or_review_more_outcomes",
        "dry_run": bool(dry_run),
        "applied_count": 0,
        "promotion_ready": False,
        "promotion_blockers": ["operator_apply_command_required", "database_mutation_disabled_by_default"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_manual_apply_plan(
    manual_decisions: dict[str, Any],
    *,
    dry_run: bool = True,
    operator_id: str = "",
) -> dict[str, Any]:
    """Build a guarded memory-maintenance apply plan without mutating memory.

    The first supported operation is deliberately narrow: accepted duplicate
    deprecation reviews can become planned operations, but they still require
    explicit operator confirmation and before/after audit capture before any
    future mutation backend is allowed to execute them.
    """

    source_ok = manual_decisions.get("schema") == APPLY_DECISION_SCHEMA
    planned_operations: list[dict[str, Any]] = []
    blocked_operations: list[dict[str, Any]] = []
    for decision in manual_decisions.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        candidate_id = _string(decision.get("candidate_id"))
        review_kind = _string(decision.get("memory_review_kind"))
        decision_label = _string(decision.get("decision"))
        base = {
            "schema": "memory_maintenance_apply_operation/v1",
            "candidate_id": candidate_id,
            "memory_review_kind": review_kind,
            "source_decision": decision_label,
            "source_outcome": _string(decision.get("outcome")),
            "example_memory_ids": list(decision.get("example_memory_ids") or []),
            "operator_id": _string(operator_id),
            "operator_confirmation_required": True,
            "operator_confirmed": False,
            "dry_run": bool(dry_run),
            "ready_to_execute": False,
            "applied": False,
            "mutates_db": False,
        }
        if decision_label == "ready_for_manual_apply" and review_kind == "duplicate_deprecation_review":
            example_ids = list(decision.get("example_memory_ids") or [])
            operation = {
                **base,
                "operation_kind": "duplicate_deprecation",
                "recommended_backend": "mark_duplicate_memory_rows_deprecated",
                "keeper_memory_id": example_ids[0] if example_ids else "",
                "deprecate_memory_ids": example_ids[1:],
                "blocked_reasons": ["operator_confirmation_required", "dry_run_enabled"]
                if dry_run
                else ["operator_confirmation_required", "mutation_backend_disabled"],
                "rollback": {
                    "required": True,
                    "strategy": "restore_duplicate_rows_and_clear_deprecation_marker",
                    "metadata_required": [
                        "candidate_id",
                        "operator_id",
                        "before_memory_rows",
                        "after_memory_rows",
                        "audit_event_id",
                    ],
                },
                "before_after_audit": {
                    "before_required": True,
                    "after_required": True,
                    "captured": False,
                    "audit_event_required": True,
                },
            }
            planned_operations.append(operation)
            continue
        reason = "decision_not_ready_for_apply"
        if decision_label == "ready_for_manual_apply":
            reason = "unsupported_memory_review_kind"
        elif decision_label in {"manual_reject_logged", "hold_for_more_evidence", "manual_noop_logged"}:
            reason = f"{decision_label}_cannot_mutate"
        blocked_operations.append(
            {
                **base,
                "operation_kind": "blocked_memory_maintenance_operation",
                "blocked_reasons": [reason],
                "rollback": {"required": False, "strategy": "no_mutation_to_rollback"},
                "before_after_audit": {
                    "before_required": False,
                    "after_required": False,
                    "captured": False,
                    "audit_event_required": True,
                },
            }
        )
    return {
        "schema": APPLY_PLAN_SCHEMA,
        "source_apply_decision_schema": manual_decisions.get("schema"),
        "source_apply_decision_ok": source_ok,
        "operation_count": len(planned_operations) + len(blocked_operations),
        "planned_operation_count": len(planned_operations),
        "duplicate_deprecation_operation_count": sum(
            1 for item in planned_operations if item.get("operation_kind") == "duplicate_deprecation"
        ),
        "blocked_operation_count": len(blocked_operations),
        "ready_to_execute_count": 0,
        "applied_count": 0,
        "planned_operations": planned_operations,
        "blocked_operations": blocked_operations,
        "next_action": "operator_confirmation_and_audit_backend_design"
        if planned_operations
        else "collect_or_review_more_manual_apply_decisions",
        "promotion_ready": False,
        "promotion_blockers": [
            "operator_confirmation_required",
            "before_after_audit_not_captured",
            "database_mutation_backend_disabled",
        ],
        "dry_run": bool(dry_run),
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
