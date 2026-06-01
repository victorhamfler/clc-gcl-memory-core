from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.resolver import (
    candidate_snippets,
    estimate_confidence,
    evidence_preference_score,
    is_relevant_to_query,
    order_evidence,
    resolve_answer,
)  # noqa: E402
from core.resolver_policy import DEFAULT_RESOLVER_POLICY, normalize_resolver_policy  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "resolver_policy_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_policy_config_regression_report.md"


EVIDENCE = [
    {
        "memory_id": "mem_resolver_policy",
        "score": 0.68,
        "text_match_score": 0.55,
        "feedback_score": 0.5,
        "supersession_score": 0.25,
        "relation_supersession_score": 0.1,
        "summary_relation_score": 0.0,
        "usage_count": 2,
        "claim_scope_score": 0.6,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "current",
        "text": "Current memory says resolver policy confidence should remain configurable and evidence-backed.",
    },
    {
        "memory_id": "mem_resolver_policy_support",
        "score": 0.44,
        "text_match_score": 0.35,
        "feedback_score": 0.0,
        "supersession_score": 0.0,
        "relation_supersession_score": 0.0,
        "summary_relation_score": 0.0,
        "usage_count": 0,
        "claim_scope_score": 0.4,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "text": "Resolver policy extraction should preserve current answer behavior by default.",
    },
]

SELECTION_EVIDENCE = [
    {
        "memory_id": f"mem_select_{idx}",
        "score": 0.9 - (idx * 0.05),
        "text_match_score": 0.7,
        "claim_scope_score": 0.7,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "text": f"Resolver selected evidence item {idx} supports configurable evidence limits.",
    }
    for idx in range(5)
]

WEAK_EVIDENCE = [
    {
        "memory_id": "mem_weak_policy",
        "score": 0.21,
        "text_match_score": 0.21,
        "claim_scope_score": 0.21,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "text": "Weak resolver evidence exists but should be marked low confidence when threshold demands it.",
    }
]

SNIPPET_EVIDENCE = [
    {
        "memory_id": "mem_snippet_generic",
        "score": 0.72,
        "text_match_score": 0.7,
        "claim_scope_score": 0.7,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "text": (
            "This document answers the resolver policy question. "
            "Resolver policy snippet controls should preserve answer behavior by default."
        ),
    }
]

CONTRADICTION_EVIDENCE = [
    {
        "memory_id": "mem_stored_contradiction",
        "score": 0.76,
        "text_match_score": 0.72,
        "claim_scope_score": 0.72,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "stored_contradiction_score": 0.80,
        "stored_contradiction_memory_ids": ["mem_conflicting_claim"],
        "text": "Resolver arbitration evidence has a stored CSD contradiction marker.",
    }
]

RELEVANCE_EVIDENCE = {
    "memory_id": "mem_relevance_borderline",
    "score": 0.20,
    "cosine": 0.20,
    "text_match_score": 0.33,
    "claim_scope_score": 0.0,
    "answer_type_score": 0.0,
    "intent_match_score": 0.0,
    "authority_state": "standalone",
    "text": "Borderline resolver relevance evidence.",
}

RANKING_EVIDENCE = [
    {
        "memory_id": "mem_high_vector",
        "rank": 1,
        "score": 0.72,
        "text_match_score": 0.10,
        "claim_scope_score": 0.10,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "text": "General resolver note: answer confidence exists.",
    },
    {
        "memory_id": "mem_high_scope",
        "rank": 2,
        "score": 0.18,
        "text_match_score": 0.20,
        "claim_scope_score": 0.95,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
        "authority_state": "standalone",
        "text": "Scoped answer row for the exact target claim.",
    },
]


def legacy_formula(evidence: list[dict], conflict: bool) -> float:
    top = evidence[0]
    score = float(top.get("score") or 0.0)
    feedback = max(0.0, float(top.get("feedback_score") or 0.0))
    supersession = max(0.0, float(top.get("supersession_score") or 0.0))
    relation = max(0.0, float(top.get("relation_supersession_score") or 0.0))
    summary = max(0.0, float(top.get("summary_relation_score") or 0.0))
    text_match = max(0.0, float(top.get("text_match_score") or 0.0))
    usage_count = max(0, int(top.get("usage_count") or 0))
    evidence_count = len(evidence)
    confidence = (
        0.28
        + min(0.34, score / 1.7)
        + 0.10 * text_match
        + 0.12 * feedback
        + 0.10 * supersession
        + 0.08 * relation
        + 0.06 * summary
        + min(0.08, 0.025 * usage_count)
        + min(0.06, 0.02 * max(0, evidence_count - 1))
    )
    if conflict:
        confidence -= 0.14
    if score < 0.35 and text_match < 0.2 and not summary:
        confidence -= 0.08
    return round(max(0.0, min(1.0, confidence)), 4)


def legacy_preference_score(query: str, item: dict) -> float:
    score = float(item.get("score") or 0.0)
    score += 0.20 * float(item.get("text_match_score") or 0.0)
    score += 0.24 * float(item.get("claim_scope_score") or 0.0)
    score += 0.28 * float(item.get("answer_type_score") or 0.0)
    score += 0.12 * float(item.get("intent_match_score") or 0.0)
    query_terms = {part for part in query.lower().split() if part}
    text_terms = {part.strip(".,:;") for part in str(item.get("text") or "").lower().split() if part}
    score += 0.05 * len(query_terms & text_terms)
    rank = int(item.get("rank") or 0)
    if rank > 0 and (
        float(item.get("answer_type_score") or 0.0) > 0.0
        or float(item.get("claim_scope_score") or 0.0) >= 0.50
        or float(item.get("text_match_score") or 0.0) >= 0.50
    ):
        score += max(0.0, 0.08 - (0.015 * (rank - 1)))
    if str(item.get("text") or "").strip():
        score += 0.04
    return score


def main() -> int:
    configured = normalize_resolver_policy(load_config(ROOT).get("resolver_policy"))
    defaults = normalize_resolver_policy(DEFAULT_RESOLVER_POLICY)
    default_confidence = estimate_confidence(EVIDENCE, False)
    configured_confidence = estimate_confidence(EVIDENCE, False, configured)
    legacy_confidence = legacy_formula(EVIDENCE, False)
    conflict_confidence = estimate_confidence(EVIDENCE, True, configured)
    boosted_policy = normalize_resolver_policy(
        {
            "answer_confidence": {
                **configured["answer_confidence"],
                "base": configured["answer_confidence"]["base"] + 0.10,
                "feedback_weight": configured["answer_confidence"]["feedback_weight"] + 0.10,
            }
        }
    )
    boosted_confidence = estimate_confidence(EVIDENCE, False, boosted_policy)
    query = "resolver policy answer confidence behavior"
    legacy_preference = legacy_preference_score(query, RANKING_EVIDENCE[1])
    configured_preference = evidence_preference_score(query, RANKING_EVIDENCE[1], configured)
    configured_order = [row["memory_id"] for row in order_evidence(query, RANKING_EVIDENCE, configured)]
    boosted_preference_policy = normalize_resolver_policy(
        {
            "evidence_preference": {
                **configured["evidence_preference"],
                "claim_scope_weight": 1.0,
                "text_match_weight": 0.5,
            }
        }
    )
    boosted_order = [row["memory_id"] for row in order_evidence(query, RANKING_EVIDENCE, boosted_preference_policy)]
    resolved_selection_default = resolve_answer(
        "What supports configurable evidence limits?",
        SELECTION_EVIDENCE,
        resolver_policy_config=configured,
    )
    selection_policy = normalize_resolver_policy(
        {
            **configured,
            "evidence_selection": {"max_selected_evidence": 1},
        }
    )
    resolved_selection_limited = resolve_answer(
        "What supports configurable evidence limits?",
        SELECTION_EVIDENCE,
        resolver_policy_config=selection_policy,
    )
    weak_policy_low = normalize_resolver_policy(
        {
            **configured,
            "answer_composition": {"low_confidence_threshold": 0.95},
        }
    )
    weak_policy_disabled = normalize_resolver_policy(
        {
            **configured,
            "answer_composition": {"low_confidence_threshold": 0.0},
        }
    )
    weak_low = resolve_answer(
        "What should happen with weak resolver evidence?",
        WEAK_EVIDENCE,
        resolver_policy_config=weak_policy_low,
    )
    weak_disabled = resolve_answer(
        "What should happen with weak resolver evidence?",
        WEAK_EVIDENCE,
        resolver_policy_config=weak_policy_disabled,
    )
    snippet_default = resolve_answer(
        "What should resolver policy snippet controls preserve?",
        SNIPPET_EVIDENCE,
        resolver_policy_config=configured,
    )
    snippet_override_policy = normalize_resolver_policy(
        {
            **configured,
            "answer_snippets": {
                **configured["answer_snippets"],
                "generic_intro_penalty": 0.0,
            },
        }
    )
    snippet_override = resolve_answer(
        "What should resolver policy snippet controls preserve?",
        SNIPPET_EVIDENCE,
        resolver_policy_config=snippet_override_policy,
    )
    direct_default_snippets = candidate_snippets(
        "resolver policy question",
        SNIPPET_EVIDENCE[0]["text"],
        configured,
    )
    direct_override_snippets = candidate_snippets(
        "resolver policy question",
        SNIPPET_EVIDENCE[0]["text"],
        snippet_override_policy,
    )
    snippet_length_policy = normalize_resolver_policy(
        {
            **configured,
            "answer_snippets": {
                **configured["answer_snippets"],
                "snippet_max_chars": 48,
            },
        }
    )
    snippet_limited = resolve_answer(
        "What should resolver policy snippet controls preserve?",
        SNIPPET_EVIDENCE,
        resolver_policy_config=snippet_length_policy,
    )
    contradiction_default = resolve_answer(
        "What does resolver arbitration evidence have?",
        CONTRADICTION_EVIDENCE,
        resolver_policy_config=configured,
    )
    contradiction_relaxed_policy = normalize_resolver_policy(
        {
            **configured,
            "evidence_arbitration": {
                **configured["evidence_arbitration"],
                "stored_contradiction_conflict_threshold": 0.95,
            },
        }
    )
    contradiction_relaxed = resolve_answer(
        "What does resolver arbitration evidence have?",
        CONTRADICTION_EVIDENCE,
        resolver_policy_config=contradiction_relaxed_policy,
    )
    relevance_query = "query relevance threshold calibration signal"
    relevance_default = is_relevant_to_query(relevance_query, RELEVANCE_EVIDENCE, configured)
    relevance_relaxed_policy = normalize_resolver_policy(
        {
            **configured,
            "query_relevance": {
                **configured["query_relevance"],
                "text_match_accept_threshold": 0.30,
            },
        }
    )
    relevance_relaxed = is_relevant_to_query(relevance_query, RELEVANCE_EVIDENCE, relevance_relaxed_policy)
    resolved_default = resolve_answer(
        "What does resolver policy extraction preserve?",
        EVIDENCE,
        resolver_policy_config=configured,
    )
    resolved_boosted = resolve_answer(
        "What does resolver policy extraction preserve?",
        EVIDENCE,
        resolver_policy_config=boosted_policy,
    )
    checks = {
        "config_matches_defaults": configured == defaults,
        "default_matches_legacy_formula": default_confidence == legacy_confidence,
        "configured_matches_default": configured_confidence == default_confidence,
        "conflict_lowers_confidence": conflict_confidence < configured_confidence,
        "override_changes_confidence": boosted_confidence > configured_confidence,
        "resolve_answer_uses_policy": float(resolved_boosted["confidence"]) > float(resolved_default["confidence"]),
        "preference_matches_legacy_formula": round(configured_preference, 6) == round(legacy_preference, 6),
        "preference_override_changes_order": configured_order != boosted_order and boosted_order[0] == "mem_high_scope",
        "default_selected_evidence_limit": len(resolved_selection_default["evidence"]) == 3,
        "configured_selected_evidence_limit": len(resolved_selection_limited["evidence"]) == 1,
        "low_confidence_notice_configurable": (
            "Confidence is low" in weak_low["answer"]
            and "Confidence is low" not in weak_disabled["answer"]
        ),
        "snippet_penalty_configurable": (
            direct_default_snippets
            and direct_override_snippets
            and not direct_default_snippets[0][0].startswith("This document answers")
            and direct_override_snippets[0][0].startswith("This document answers")
        ),
        "snippet_length_configurable": "..." in snippet_limited["answer"],
        "stored_contradiction_threshold_configurable": (
            contradiction_default["conflict"] is True
            and contradiction_relaxed["conflict"] is False
            and contradiction_default["evidence"][0]["conflict"] is True
            and contradiction_relaxed["evidence"][0]["conflict"] is False
        ),
        "query_relevance_threshold_configurable": relevance_default is False and relevance_relaxed is True,
    }
    report = {
        "schema": "resolver_policy_config_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "default_confidence": default_confidence,
        "configured_confidence": configured_confidence,
        "legacy_confidence": legacy_confidence,
        "conflict_confidence": conflict_confidence,
        "boosted_confidence": boosted_confidence,
        "resolved_default_confidence": resolved_default["confidence"],
        "resolved_boosted_confidence": resolved_boosted["confidence"],
        "legacy_preference_score": round(legacy_preference, 6),
        "configured_preference_score": round(configured_preference, 6),
        "configured_order": configured_order,
        "boosted_order": boosted_order,
        "default_selected_evidence_count": len(resolved_selection_default["evidence"]),
        "limited_selected_evidence_count": len(resolved_selection_limited["evidence"]),
        "weak_low_answer": weak_low["answer"],
        "weak_disabled_answer": weak_disabled["answer"],
        "snippet_default_answer": snippet_default["answer"],
        "snippet_override_answer": snippet_override["answer"],
        "snippet_limited_answer": snippet_limited["answer"],
        "direct_default_snippets": direct_default_snippets,
        "direct_override_snippets": direct_override_snippets,
        "contradiction_default_conflict": contradiction_default["conflict"],
        "contradiction_relaxed_conflict": contradiction_relaxed["conflict"],
        "relevance_default": relevance_default,
        "relevance_relaxed": relevance_relaxed,
        "configured_policy": configured,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Policy Config Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
