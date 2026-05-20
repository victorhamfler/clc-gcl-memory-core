from __future__ import annotations

from pathlib import Path
from typing import Any

from core.clc_policy_selector import (
    CLCLearnedPolicySelector,
    CLCPolicyFeatures,
    CLCPolicySelector,
    CLCPolicyDecision,
    POLICY_ACTIONS,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
)
from core.config import resolve_project_path


DEFAULT_MATRIX_REPORT = "../experiments/clc_policy_matrix_eval_live_results.json"
DEFAULT_OUTCOME_LOG = "../experiments/hermes_clc_selector_outcome_labels.jsonl"


def selector_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = (config or {}).get("selector")
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def selector_mode(config: dict[str, Any] | None) -> str:
    mode = str(selector_config(config).get("mode") or "current").strip().lower()
    return mode if mode in {"current", "learned"} else "current"


def selector_paths(root: Path, config: dict[str, Any] | None) -> dict[str, Path]:
    cfg = selector_config(config)
    matrix_report = resolve_project_path(root, cfg.get("matrix_report"), DEFAULT_MATRIX_REPORT)
    outcome_log = resolve_project_path(root, cfg.get("outcome_log"), DEFAULT_OUTCOME_LOG)
    return {"matrix_report": matrix_report, "outcome_log": outcome_log}


def build_policy_selector(root: Path, config: dict[str, Any] | None) -> CLCPolicySelector | CLCLearnedPolicySelector:
    cfg = selector_config(config)
    mode = selector_mode(config)
    k = int(cfg.get("k") or 3)
    if mode == "learned":
        paths = selector_paths(root, config)
        if paths["matrix_report"].exists():
            return CLCLearnedPolicySelector.from_matrix_report(paths["matrix_report"], k=k)
        return CLCLearnedPolicySelector.from_outcome_log(paths["outcome_log"], k=k)
    return CLCPolicySelector(
        label_cost_ceiling=float(cfg.get("label_cost_ceiling") or 0.00025),
        high_budget_pressure=float(cfg.get("high_budget_pressure") or 0.9),
    )


def selector_features_for_condition(condition_name: str) -> CLCPolicyFeatures:
    if condition_name == "hard_budget144":
        return CLCPolicyFeatures.from_condition_name(
            condition_name, memory_bad_rate=0.75, probe_drop=0.18, csd_ratio=1.4
        )
    if condition_name == "standard_budget144":
        return CLCPolicyFeatures.from_condition_name(
            condition_name, memory_bad_rate=0.25, probe_drop=0.08, csd_ratio=0.9
        )
    if condition_name == "long2_hard_budget288":
        return CLCPolicyFeatures.from_condition_name(
            condition_name, memory_bad_rate=0.35, probe_drop=0.04, csd_ratio=0.7
        )
    if condition_name == "long2_standard_budget288":
        return CLCPolicyFeatures.from_condition_name(
            condition_name, memory_bad_rate=0.2, probe_drop=0.03, csd_ratio=0.6
        )
    return CLCPolicyFeatures.from_condition_name(condition_name)


def selector_features_from_retrieval_context(
    retrieval_rows: list[dict[str, Any]],
    *,
    condition_name: str = "hard_budget144",
    label_cost: float = 0.0002,
    budget_pressure: float = 0.2,
) -> tuple[CLCPolicyFeatures, dict[str, Any]]:
    rows = [row for row in retrieval_rows if isinstance(row, dict)]
    total = max(1, len(rows))
    contradiction_scores = [max(0.0, float(row.get("stored_contradiction_score") or 0.0)) for row in rows]
    supersession_scores = [float(row.get("supersession_score") or 0.0) for row in rows]
    relation_scores = [float(row.get("relation_supersession_score") or 0.0) for row in rows]
    source_reliability = [float(row.get("source_reliability") or 0.0) for row in rows]
    domain_reliability = [float(row.get("domain_reliability") or 0.0) for row in rows]
    retrieval_scores = [float(row.get("score") or row.get("cosine") or 0.0) for row in rows]
    text_match_scores = [float(row.get("text_match_score") or 0.0) for row in rows]
    claim_scope_scores = [float(row.get("claim_scope_score") or row.get("text_match_score") or 0.0) for row in rows]

    stale_rows = 0
    current_rows = 0
    stale_scores: list[float] = []
    current_scores: list[float] = []
    standalone_scores: list[float] = []
    stale_text_matches: list[float] = []
    current_text_matches: list[float] = []
    standalone_text_matches: list[float] = []
    topical_anchor_text_matches: list[float] = []
    correction_current_text_matches: list[float] = []
    stale_claim_matches: list[float] = []
    current_claim_matches: list[float] = []
    standalone_claim_matches: list[float] = []
    topical_anchor_claim_matches: list[float] = []
    correction_current_claim_matches: list[float] = []
    top_stale_rank = 0
    top_current_rank = 0
    for row, supersession, relation, text_match, claim_match in zip(
        rows,
        supersession_scores,
        relation_scores,
        text_match_scores,
        claim_scope_scores,
    ):
        authority_state = str(row.get("authority_state") or "").lower()
        score = float(row.get("score") or row.get("cosine") or 0.0)
        explicit_current = authority_state in {"authoritative", "current"} or bool(row.get("supersedes_memory_ids"))
        is_stale = (
            authority_state in {"superseded", "stale"}
            or row.get("superseded_by_memory_ids")
            or supersession < -0.05
            or relation < -0.05
        )
        is_current = (
            explicit_current
            or supersession > 0.05
            or relation > 0.05
        )
        if authority_state in {"standalone", "unknown", ""} and not row.get("superseded_by_memory_ids"):
            topical_anchor_text_matches.append(text_match)
            topical_anchor_claim_matches.append(claim_match)
        if explicit_current:
            correction_current_text_matches.append(text_match)
            correction_current_claim_matches.append(claim_match)
        if is_stale:
            stale_rows += 1
            stale_scores.append(score)
            stale_text_matches.append(text_match)
            stale_claim_matches.append(claim_match)
            if top_stale_rank == 0:
                top_stale_rank = len(stale_scores) + len(current_scores) + len(standalone_scores)
        if is_current:
            current_rows += 1
            current_scores.append(score)
            current_text_matches.append(text_match)
            current_claim_matches.append(claim_match)
            if top_current_rank == 0:
                top_current_rank = len(stale_scores) + len(current_scores) + len(standalone_scores)
        if not is_stale and not is_current:
            standalone_scores.append(score)
            standalone_text_matches.append(text_match)
            standalone_claim_matches.append(claim_match)

    stale_ratio = stale_rows / total
    current_ratio = current_rows / total
    contradiction_peak = max(contradiction_scores or [0.0])
    contradiction_mean = sum(contradiction_scores) / total
    positive_supersession = [max(0.0, value) for value in supersession_scores + relation_scores]
    negative_supersession = [max(0.0, -value) for value in supersession_scores + relation_scores]
    current_strength = max(positive_supersession or [0.0])
    stale_strength = max(negative_supersession or [0.0])
    avg_source_reliability = sum(source_reliability) / total
    avg_domain_reliability = sum(domain_reliability) / total
    avg_retrieval_score = sum(retrieval_scores) / total
    top_score = retrieval_scores[0] if retrieval_scores else 0.0
    top_authority_state = str(rows[0].get("authority_state") or "unknown").lower() if rows else "unknown"
    stale_score_max = max(stale_scores or [0.0])
    current_score_max = max(current_scores or [0.0])
    standalone_score_max = max(standalone_scores or [0.0])
    stale_score_gap = top_score - stale_score_max
    stale_text_match_max = max(stale_text_matches or [0.0])
    current_text_match_max = max(current_text_matches or [0.0])
    standalone_text_match_max = max(standalone_text_matches or [0.0])
    topical_anchor_text_match_max = max(topical_anchor_text_matches or [0.0])
    correction_current_text_match_max = max(correction_current_text_matches or [0.0])
    stale_claim_match_max = max(stale_claim_matches or [0.0])
    current_claim_match_max = max(current_claim_matches or [0.0])
    standalone_claim_match_max = max(standalone_claim_matches or [0.0])
    topical_anchor_claim_match_max = max(topical_anchor_claim_matches or [0.0])
    correction_current_claim_match_max = max(correction_current_claim_matches or [0.0])
    irrelevant_stale_cluster = bool(
        stale_rows >= 1
        and top_stale_rank >= 3
        and contradiction_peak <= 0.0
        and (
            (
                top_authority_state in {"standalone", "unknown"}
                and stale_score_gap >= 0.10
                and stale_strength <= 0.25
            )
            or (
                standalone_text_match_max >= 0.60
                and stale_text_match_max <= 0.35
                and current_text_match_max <= 0.35
            )
            or (
                topical_anchor_text_match_max >= 0.75
                and stale_text_match_max <= 0.70
                and correction_current_text_match_max <= 0.70
            )
            or (
                topical_anchor_claim_match_max >= 0.75
                and stale_claim_match_max <= 0.70
                and correction_current_claim_match_max <= 0.70
            )
        )
    )
    reliability_gap = max(0.0, -min(0.0, avg_source_reliability, avg_domain_reliability))
    stale_pressure = max(stale_ratio, stale_strength, contradiction_peak)
    current_pressure = max(current_ratio, current_strength)
    stale_current_conflict = min(stale_pressure, current_pressure)
    memory_bad_rate = max(
        0.0,
        min(
            0.98,
            0.18
            + 0.42 * stale_ratio
            + 0.28 * contradiction_peak
            + 0.22 * stale_strength
            + 0.20 * stale_current_conflict,
        ),
    )
    probe_drop = max(
        0.0,
        min(
            0.98,
            0.04
            + 0.32 * contradiction_mean
            + 0.18 * stale_ratio
            + 0.18 * stale_current_conflict
            + 0.08 * reliability_gap,
        ),
    )
    csd_ratio = max(
        0.4,
        min(
            3.5,
            0.75
            + 0.65 * stale_pressure
            + 0.05 * current_pressure
            + 0.70 * contradiction_peak
            + 0.2 * reliability_gap,
        ),
    )
    hard = bool((stale_pressure >= 0.35 or contradiction_peak >= 0.5 or stale_rows >= 2) and not irrelevant_stale_cluster)
    condition_l = str(condition_name or "").lower()
    effective_condition = condition_name
    if hard and "hard" not in condition_l:
        effective_condition = "long2_hard_budget288" if "long" in condition_l else "hard_budget144"
    features = CLCPolicyFeatures.from_condition_name(
        effective_condition,
        memory_bad_rate=memory_bad_rate,
        probe_drop=probe_drop,
        csd_ratio=csd_ratio,
        label_cost=float(label_cost),
        budget_pressure=float(budget_pressure),
        recent_return_mean=0.0,
    )
    diagnostics = {
        "retrieval_count": len(rows),
        "stale_rows": stale_rows,
        "current_rows": current_rows,
        "stale_ratio": round(stale_ratio, 6),
        "current_ratio": round(current_ratio, 6),
        "contradiction_peak": round(contradiction_peak, 6),
        "contradiction_mean": round(contradiction_mean, 6),
        "stale_strength": round(stale_strength, 6),
        "current_strength": round(current_strength, 6),
        "stale_current_conflict": round(stale_current_conflict, 6),
        "avg_source_reliability": round(avg_source_reliability, 6),
        "avg_domain_reliability": round(avg_domain_reliability, 6),
        "avg_retrieval_score": round(avg_retrieval_score, 6),
        "top_score": round(top_score, 6),
        "top_authority_state": top_authority_state,
        "top_stale_rank": top_stale_rank,
        "top_current_rank": top_current_rank,
        "stale_score_max": round(stale_score_max, 6),
        "current_score_max": round(current_score_max, 6),
        "standalone_score_max": round(standalone_score_max, 6),
        "stale_score_gap": round(stale_score_gap, 6),
        "stale_text_match_max": round(stale_text_match_max, 6),
        "current_text_match_max": round(current_text_match_max, 6),
        "standalone_text_match_max": round(standalone_text_match_max, 6),
        "topical_anchor_text_match_max": round(topical_anchor_text_match_max, 6),
        "correction_current_text_match_max": round(correction_current_text_match_max, 6),
        "stale_claim_match_max": round(stale_claim_match_max, 6),
        "current_claim_match_max": round(current_claim_match_max, 6),
        "standalone_claim_match_max": round(standalone_claim_match_max, 6),
        "topical_anchor_claim_match_max": round(topical_anchor_claim_match_max, 6),
        "correction_current_claim_match_max": round(correction_current_claim_match_max, 6),
        "irrelevant_stale_cluster": irrelevant_stale_cluster,
        "memory_bad_rate": round(memory_bad_rate, 6),
        "probe_drop": round(probe_drop, 6),
        "csd_ratio": round(csd_ratio, 6),
        "hard": hard,
    }
    return features, diagnostics


def selector_features_from_payload(payload: dict[str, Any]) -> CLCPolicyFeatures | dict[str, Any]:
    if isinstance(payload.get("retrieval_context"), list):
        features, _diagnostics = selector_features_from_retrieval_context(
            payload["retrieval_context"],
            condition_name=str(payload.get("condition_name") or "hard_budget144"),
            label_cost=float(payload.get("label_cost", 0.0002) or 0.0002),
            budget_pressure=float(payload.get("budget_pressure", 0.2) or 0.2),
        )
        return features
    condition_name = str(payload.get("condition_name") or "").strip()
    if condition_name:
        features = selector_features_for_condition(condition_name)
        feature_updates = {
            key: payload[key]
            for key in (
                "budget_units",
                "cycles",
                "hard",
                "long_stream",
                "csd_ratio",
                "probe_drop",
                "label_cost",
                "budget_pressure",
                "recent_return_mean",
                "memory_bad_rate",
            )
            if key in payload
        }
        if feature_updates:
            return type(features)(**{**features.__dict__, **feature_updates})
        return features
    return dict(payload.get("features") or payload)


def apply_retrieval_policy_guard(
    decision: CLCPolicyDecision,
    features: CLCPolicyFeatures | dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> CLCPolicyDecision:
    """Apply interpretable retrieval guards around learned selector votes.

    The learned selector can be pulled by sparse outcome labels. Retrieval-derived
    diagnostics are stronger evidence for clean/non-clean boundaries, so they get
    a final veto only when the decision came from retrieved memory context.
    """

    if not diagnostics:
        return decision
    if "label_cost" in decision.reason or "budget_pressure" in decision.reason:
        return decision
    f = features if isinstance(features, CLCPolicyFeatures) else CLCPolicySelector()._normalize(features)
    stale_ratio = float(diagnostics.get("stale_ratio") or 0.0)
    contradiction_peak = float(diagnostics.get("contradiction_peak") or 0.0)
    stale_current_conflict = float(diagnostics.get("stale_current_conflict") or 0.0)
    current_ratio = float(diagnostics.get("current_ratio") or 0.0)
    memory_bad_rate = float(diagnostics.get("memory_bad_rate", f.memory_bad_rate) or 0.0)
    probe_drop = float(diagnostics.get("probe_drop", f.probe_drop) or 0.0)

    if (
        bool(diagnostics.get("irrelevant_stale_cluster"))
        and contradiction_peak <= 0.0
    ):
        return CLCPolicyDecision(
            policy=POLICY_PERIODIC,
            action=POLICY_ACTIONS[POLICY_PERIODIC],
            reason=f"retrieval_guard_irrelevant_stale_cluster:{decision.reason}",
            confidence=max(0.80, min(0.95, decision.confidence)),
        )
    if (
        not f.hard
        and stale_ratio <= 0.0
        and contradiction_peak <= 0.0
        and stale_current_conflict <= 0.0
        and memory_bad_rate <= 0.25
        and probe_drop <= 0.08
    ):
        return CLCPolicyDecision(
            policy=POLICY_PERIODIC,
            action=POLICY_ACTIONS[POLICY_PERIODIC],
            reason=f"retrieval_guard_clean_nonhard_context:{decision.reason}",
            confidence=max(0.82, min(0.95, decision.confidence)),
        )
    if (
        not f.hard
        and contradiction_peak <= 0.0
        and stale_ratio <= 0.34
        and stale_current_conflict <= 0.35
        and current_ratio >= 0.9
        and memory_bad_rate <= 0.45
        and probe_drop <= 0.18
    ):
        return CLCPolicyDecision(
            policy=POLICY_PERIODIC,
            action=POLICY_ACTIONS[POLICY_PERIODIC],
            reason=f"retrieval_guard_low_relevance_stale_context:{decision.reason}",
            confidence=max(0.78, min(0.95, decision.confidence)),
        )
    if f.hard and stale_current_conflict >= 0.8 and not bool(diagnostics.get("irrelevant_stale_cluster")):
        return CLCPolicyDecision(
            policy=POLICY_LONG_SEVERE,
            action=POLICY_ACTIONS[POLICY_LONG_SEVERE],
            reason=f"retrieval_guard_hard_stale_current_conflict:{decision.reason}",
            confidence=max(0.78, min(0.95, decision.confidence)),
        )
    return decision


def apply_retrieval_explanation_guard(
    explanation: dict[str, Any],
    features: CLCPolicyFeatures | dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    base = explanation.get("decision") or {}
    decision = CLCPolicyDecision(
        policy=str(base.get("policy") or POLICY_PERIODIC),
        action=str(base.get("action") or POLICY_ACTIONS[POLICY_PERIODIC]),
        reason=str(base.get("reason") or "unknown"),
        confidence=float(base.get("confidence") or 0.0),
    )
    guarded = apply_retrieval_policy_guard(decision, features, diagnostics)
    if guarded == decision:
        explanation["retrieval_guard"] = {"applied": False}
        return explanation
    explanation["base_decision"] = dict(base)
    explanation["decision"] = {
        "policy": guarded.policy,
        "action": guarded.action,
        "reason": guarded.reason,
        "confidence": guarded.confidence,
    }
    explanation["retrieval_guard"] = {
        "applied": True,
        "base_policy": decision.policy,
        "guarded_policy": guarded.policy,
        "reason": guarded.reason,
    }
    return explanation


def select_policy(root: Path, config: dict[str, Any] | None, features: CLCPolicyFeatures | dict[str, Any]) -> CLCPolicyDecision:
    return build_policy_selector(root, config).select(features)


def selector_config_view(root: Path, config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = selector_config(config)
    paths = selector_paths(root, config)
    mode = selector_mode(config)
    selector = build_policy_selector(root, config)
    return {
        "mode": mode,
        "class": selector.__class__.__name__,
        "k": int(cfg.get("k") or 3),
        "matrix_report": str(paths["matrix_report"]),
        "matrix_report_exists": paths["matrix_report"].exists(),
        "outcome_log": str(paths["outcome_log"]),
        "outcome_log_exists": paths["outcome_log"].exists(),
        "sample_count": len(getattr(selector, "samples", []) or []),
        "fallback": "CLCPolicySelector",
        "guardrails": {
            "label_cost_ceiling": float(cfg.get("label_cost_ceiling") or 0.00025),
            "high_budget_pressure": float(cfg.get("high_budget_pressure") or 0.9),
        },
    }
