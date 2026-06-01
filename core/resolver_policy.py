from __future__ import annotations

from typing import Any


DEFAULT_RESOLVER_POLICY = {
    "answer_confidence": {
        "base": 0.28,
        "score_divisor": 1.7,
        "score_cap": 0.34,
        "text_match_weight": 0.10,
        "feedback_weight": 0.12,
        "supersession_weight": 0.10,
        "relation_weight": 0.08,
        "summary_weight": 0.06,
        "usage_bonus_cap": 0.08,
        "usage_bonus_weight": 0.025,
        "count_bonus_cap": 0.06,
        "count_bonus_weight": 0.02,
        "conflict_penalty": 0.14,
        "weak_score_threshold": 0.35,
        "weak_text_match_threshold": 0.20,
        "weak_evidence_penalty": 0.08,
    },
    "evidence_preference": {
        "text_match_weight": 0.20,
        "claim_scope_weight": 0.24,
        "answer_type_weight": 0.28,
        "intent_match_weight": 0.12,
        "term_overlap_weight": 0.05,
        "rank_one_bonus": 0.08,
        "rank_one_decay": 0.015,
        "broad_generic_penalty": 0.18,
        "scope_deflection_penalty": 0.35,
        "negative_permission_penalty": 0.22,
        "current_authority_weight": 0.35,
        "current_authority_floor": 0.30,
        "superseded_penalty": 0.55,
        "does_not_change_penalty": 0.18,
        "assignment_statement_bonus": 0.08,
        "memory_improvement_penalty": 0.18,
        "original_preview_penalty": 0.06,
        "clean_text_bonus": 0.04,
        "summary_mechanism_bonus": 0.12,
    },
    "evidence_selection": {
        "max_selected_evidence": 3,
    },
    "answer_composition": {
        "low_confidence_threshold": 0.45,
    },
    "answer_snippets": {
        "max_evidence_scan": 3,
        "multi_intent_max_evidence_scan": 4,
        "single_intent_max_snippets": 2,
        "multi_intent_max_snippets": 3,
        "current_state_bonus": 3.0,
        "summary_state_bonus": 1.2,
        "historical_state_bonus": 0.4,
        "stale_state_penalty": 2.2,
        "broad_generic_penalty": 2.0,
        "scope_deflection_penalty": 3.5,
        "primary_evidence_bonus": 1.2,
        "secondary_min_score": 1.6,
        "secondary_top_ratio": 0.92,
        "multi_intent_rank_bonus_base": 0.45,
        "multi_intent_rank_bonus_decay": 0.12,
        "multi_intent_broad_generic_penalty": 0.8,
        "coverage_weight": 2.0,
        "correction_bonus": 2.0,
        "procedure_bonus": 1.4,
        "preference_bonus": 0.8,
        "generic_intro_penalty": 4.0,
        "exact_phrase_bonus_weight": 0.4,
        "exact_phrase_bonus_cap": 1.2,
        "snippet_max_chars": 360,
    },
    "evidence_arbitration": {
        "stored_contradiction_conflict_threshold": 0.75,
        "historical_scope_threshold": 0.75,
        "historical_score_margin": 0.04,
        "nondeflecting_historical_margin": 0.02,
        "current_scope_threshold": 0.75,
        "current_score_margin": 0.04,
        "session_focus_threshold": 0.50,
        "session_focus_margin": 0.02,
        "current_relevance_floor_min": 0.18,
        "current_relevance_floor_ratio": 0.90,
        "stale_supplement_margin": 0.08,
        "rank_one_takeover_margin": 0.15,
        "positive_claim_scope_threshold": 0.50,
        "positive_text_match_threshold": 0.50,
    },
    "query_relevance": {
        "negative_intent_threshold": -0.40,
        "negative_intent_text_match_floor": 0.67,
        "text_match_accept_threshold": 0.34,
        "intent_accept_threshold": 0.65,
        "answer_type_min_overlap": 2,
        "vector_score_accept_threshold": 0.30,
        "cosine_accept_threshold": 0.62,
    },
}


def normalize_resolver_policy(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if isinstance(config, dict) else {}
    raw_confidence = cfg.get("answer_confidence") if isinstance(cfg.get("answer_confidence"), dict) else {}
    default_confidence = DEFAULT_RESOLVER_POLICY["answer_confidence"]
    confidence = {
        key: _float(raw_confidence.get(key), default)
        for key, default in default_confidence.items()
    }
    confidence["score_divisor"] = max(0.000001, confidence["score_divisor"])
    confidence["score_cap"] = max(0.0, confidence["score_cap"])
    confidence["usage_bonus_cap"] = max(0.0, confidence["usage_bonus_cap"])
    confidence["count_bonus_cap"] = max(0.0, confidence["count_bonus_cap"])
    raw_preference = cfg.get("evidence_preference") if isinstance(cfg.get("evidence_preference"), dict) else {}
    default_preference = DEFAULT_RESOLVER_POLICY["evidence_preference"]
    preference = {
        key: _float(raw_preference.get(key), default)
        for key, default in default_preference.items()
    }
    preference["rank_one_bonus"] = max(0.0, preference["rank_one_bonus"])
    preference["rank_one_decay"] = max(0.0, preference["rank_one_decay"])
    raw_selection = cfg.get("evidence_selection") if isinstance(cfg.get("evidence_selection"), dict) else {}
    selection = {
        "max_selected_evidence": max(
            1,
            int(_float(raw_selection.get("max_selected_evidence"), DEFAULT_RESOLVER_POLICY["evidence_selection"]["max_selected_evidence"])),
        )
    }
    raw_composition = cfg.get("answer_composition") if isinstance(cfg.get("answer_composition"), dict) else {}
    composition = {
        "low_confidence_threshold": _float(
            raw_composition.get("low_confidence_threshold"),
            DEFAULT_RESOLVER_POLICY["answer_composition"]["low_confidence_threshold"],
        )
    }
    raw_snippets = cfg.get("answer_snippets") if isinstance(cfg.get("answer_snippets"), dict) else {}
    default_snippets = DEFAULT_RESOLVER_POLICY["answer_snippets"]
    snippets = {
        key: _float(raw_snippets.get(key), default)
        for key, default in default_snippets.items()
    }
    for key in (
        "max_evidence_scan",
        "multi_intent_max_evidence_scan",
        "single_intent_max_snippets",
        "multi_intent_max_snippets",
        "snippet_max_chars",
    ):
        snippets[key] = max(1, int(snippets[key]))
    for key in (
        "stale_state_penalty",
        "broad_generic_penalty",
        "scope_deflection_penalty",
        "secondary_min_score",
        "secondary_top_ratio",
        "multi_intent_rank_bonus_base",
        "multi_intent_rank_bonus_decay",
        "multi_intent_broad_generic_penalty",
        "coverage_weight",
        "correction_bonus",
        "procedure_bonus",
        "preference_bonus",
        "generic_intro_penalty",
        "exact_phrase_bonus_weight",
        "exact_phrase_bonus_cap",
    ):
        snippets[key] = max(0.0, snippets[key])
    raw_arbitration = cfg.get("evidence_arbitration") if isinstance(cfg.get("evidence_arbitration"), dict) else {}
    default_arbitration = DEFAULT_RESOLVER_POLICY["evidence_arbitration"]
    arbitration = {
        key: _float(raw_arbitration.get(key), default)
        for key, default in default_arbitration.items()
    }
    for key in default_arbitration:
        if key != "stored_contradiction_conflict_threshold":
            arbitration[key] = max(0.0, arbitration[key])
    raw_relevance = cfg.get("query_relevance") if isinstance(cfg.get("query_relevance"), dict) else {}
    default_relevance = DEFAULT_RESOLVER_POLICY["query_relevance"]
    relevance = {
        key: _float(raw_relevance.get(key), default)
        for key, default in default_relevance.items()
    }
    relevance["answer_type_min_overlap"] = max(1, int(relevance["answer_type_min_overlap"]))
    return {
        "answer_confidence": confidence,
        "evidence_preference": preference,
        "evidence_selection": selection,
        "answer_composition": composition,
        "answer_snippets": snippets,
        "evidence_arbitration": arbitration,
        "query_relevance": relevance,
    }


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
