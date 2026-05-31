from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import load_config
from core.evidence_context import normalize_text


DEFAULT_POLICY = {
    "residual_threshold": 0.8,
    "family_confidence_threshold": 0.0,
    "allowed_families": ["supported_evidence"],
    "allowed_target": "likely_helpful",
    "suppressors": [
        "sensitive_private",
        "stale_previous",
        "ordinary_namespace_profile",
        "unsupported_proof",
    ],
}
SENSITIVE_PRIVATE_TERMS = (
    "api key",
    "bank pin",
    "database password",
    "deployment key",
    "deployment password",
    "hidden deployment",
    "hostname",
    "identity number",
    "passport",
    "password",
    "personal identity",
    "private",
    "recovery phrase",
    "secret",
    "token",
    "unlogged",
    "unrecorded",
)
STALE_PREVIOUS_TERMS = (
    "old",
    "previous",
    "before the correction",
    "before the update",
    "still valid",
    "still be used",
)
ORDINARY_NAMESPACE_PROFILE_TERMS = (
    "ordinary profile",
    "ordinary namespace",
    "profile lookup",
    "namespace lookup",
    "cross-namespace",
    "cross namespaces",
    "namespace crossing",
)
UNSUPPORTED_PROOF_TERMS = (
    "already natural multi-day data",
    "changed live answers",
    "proves residual",
    "result proves",
    "unsupported claim",
)
TERM_GROUPS = {
    "sensitive_private": SENSITIVE_PRIVATE_TERMS,
    "stale_previous": STALE_PREVIOUS_TERMS,
    "ordinary_namespace_profile": ORDINARY_NAMESPACE_PROFILE_TERMS,
    "unsupported_proof": UNSUPPORTED_PROOF_TERMS,
}


def _as_term_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        terms = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple)):
        terms = [str(item).strip() for item in value]
    else:
        return default
    cleaned = tuple(term for term in terms if term)
    return cleaned or default


def load_policy(root: Path, override: dict[str, Any] | None = None) -> dict[str, Any]:
    active_policy = dict(DEFAULT_POLICY)
    config = load_config(root)
    configured = config.get("adaptive_residual_shadow") if isinstance(config, dict) else None
    if isinstance(configured, dict):
        for key in ("residual_threshold", "family_confidence_threshold", "allowed_families", "allowed_target", "suppressors"):
            if key in configured and configured[key] is not None:
                if key in {"allowed_families", "suppressors"}:
                    active_policy[key] = list(_as_term_tuple(configured[key], tuple(active_policy.get(key) or [])))
                else:
                    active_policy[key] = configured[key]
        terms = configured.get("terms") if isinstance(configured.get("terms"), dict) else {}
        active_policy["terms"] = {
            name: _as_term_tuple(terms.get(name), defaults)
            for name, defaults in TERM_GROUPS.items()
        }
    else:
        active_policy["terms"] = dict(TERM_GROUPS)
    if isinstance(override, dict):
        active_policy.update({key: value for key, value in override.items() if value is not None})
        if "terms" not in active_policy:
            active_policy["terms"] = dict(TERM_GROUPS)
    return active_policy


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def suppression_reasons(query: str, policy: dict[str, Any]) -> list[str]:
    text = normalize_text(query)
    suppressors = set(policy.get("suppressors") or [])
    terms = policy.get("terms") if isinstance(policy.get("terms"), dict) else {}
    reasons = []
    if "sensitive_private" in suppressors and _contains_any(text, _as_term_tuple(terms.get("sensitive_private"), SENSITIVE_PRIVATE_TERMS)):
        reasons.append("sensitive_private_lookup_pressure")
    if "stale_previous" in suppressors and _contains_any(text, _as_term_tuple(terms.get("stale_previous"), STALE_PREVIOUS_TERMS)):
        reasons.append("stale_previous_lookup_pressure")
    if "ordinary_namespace_profile" in suppressors and _contains_any(text, _as_term_tuple(terms.get("ordinary_namespace_profile"), ORDINARY_NAMESPACE_PROFILE_TERMS)):
        reasons.append("ordinary_namespace_profile_lookup_pressure")
    if "unsupported_proof" in suppressors and _contains_any(text, _as_term_tuple(terms.get("unsupported_proof"), UNSUPPORTED_PROOF_TERMS)):
        reasons.append("unsupported_proof_lookup_pressure")
    return reasons


def _answer_has_refusal(answer: str) -> bool:
    text = normalize_text(answer)
    return any(
        marker in text
        for marker in (
            "not enough",
            "insufficient",
            "cannot answer",
            "no memory evidence",
            "do not have enough",
        )
    )


def _train_models(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, int]]:
    # Imported lazily to keep normal runtime startup free of eval-time training work.
    from eval.adaptive_behavior_feature_cross_log_holdout import DEFAULT_TRAIN_LOGS, read_logs
    from eval.adaptive_behavior_feature_scorer_hybrid_eval import train_family_models, train_residual_model

    train_samples, train_counts = read_logs(DEFAULT_TRAIN_LOGS)
    return train_family_models(train_samples), train_residual_model(train_samples), [str(path) for path in DEFAULT_TRAIN_LOGS], train_counts


def _sample_for_decision(
    *,
    query: str,
    answer: str,
    decision: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation_id": "runtime_shadow_candidate",
        "query": query,
        "feedback_label": None,
        "behavior_family": str(decision.get("behavior_family") or ""),
        "expected_advisory": None,
        "symbolic_advisory": str(decision.get("advisory") or ""),
        "symbolic_probability": float(decision.get("shadow_probability") or 0.0),
        "answer_has_refusal": _answer_has_refusal(answer),
        "evidence_context_features": features,
    }


def adaptive_residual_shadow_advisories(
    *,
    root: Path,
    query: str,
    answer: str,
    adaptive_behavior_shadow: dict[str, Any] | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return report-only learned-residual shadow advisories.

    This is deliberately disabled-by-default at the API layer. It trains tiny
    local eval models from existing feature logs only when explicitly requested,
    then applies the guarded context-suppressed policy to the current ask.
    """

    active_policy = load_policy(root, policy)

    shadow = adaptive_behavior_shadow if isinstance(adaptive_behavior_shadow, dict) else {}
    diagnostics = shadow.get("diagnostics") if isinstance(shadow.get("diagnostics"), dict) else {}
    features = diagnostics.get("evidence_context_features")
    if not isinstance(features, dict) or not features:
        return {
            "schema": "adaptive_residual_shadow/v1",
            "ok": False,
            "error": "missing_evidence_context_features",
            "policy": active_policy,
            "decisions": [],
            "report_only": True,
            "mutates_answer": False,
            "mutates_selector_policy": False,
            "mutates_memory": False,
            "mutates_config": False,
        }

    try:
        family_models, residual_model, train_logs, train_counts = _train_models(root)
        from eval.adaptive_behavior_feature_scorer_hybrid_eval import family_predict, residual_predict
    except Exception as exc:
        return {
            "schema": "adaptive_residual_shadow/v1",
            "ok": False,
            "error": f"model_training_failed: {exc}",
            "policy": active_policy,
            "decisions": [],
            "report_only": True,
            "mutates_answer": False,
            "mutates_selector_policy": False,
            "mutates_memory": False,
            "mutates_config": False,
        }

    decisions = []
    counts = {"would_override": 0, "suppressed": 0, "symbolic_fallback": 0}
    for decision in shadow.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        sample = _sample_for_decision(query=query, answer=answer, decision=decision, features=features)
        family_advisory, family_confidence, family_source = family_predict(family_models, sample)
        residual_label, residual_confidence = residual_predict(residual_model, sample)
        suppressed = suppression_reasons(query, active_policy)
        allowed = (
            residual_label == "symbolic_wrong"
            and residual_confidence >= float(active_policy.get("residual_threshold") or 0.0)
            and family_confidence >= float(active_policy.get("family_confidence_threshold") or 0.0)
            and family_source == "family_model"
            and sample["behavior_family"] in set(active_policy.get("allowed_families") or [])
            and family_advisory == active_policy.get("allowed_target")
        )
        would_override = bool(allowed and not suppressed)
        if would_override:
            counts["would_override"] += 1
            advisory = family_advisory
            source = "learned_residual_context_guarded_override"
        elif suppressed and allowed:
            counts["suppressed"] += 1
            advisory = sample["symbolic_advisory"]
            source = "context_suppressed_symbolic_fallback"
        else:
            counts["symbolic_fallback"] += 1
            advisory = sample["symbolic_advisory"]
            source = "symbolic_fallback"
        decisions.append(
            {
                "behavior_family": sample["behavior_family"],
                "symbolic_advisory": sample["symbolic_advisory"],
                "family_advisory": family_advisory,
                "family_confidence": family_confidence,
                "family_source": family_source,
                "residual_prediction": residual_label,
                "residual_confidence": residual_confidence,
                "suppression_reasons": suppressed,
                "would_override": would_override,
                "report_only_advisory": advisory,
                "source": source,
                "mutates_runtime": False,
                "mutates_config": False,
            }
        )
    return {
        "schema": "adaptive_residual_shadow/v1",
        "ok": True,
        "policy": active_policy,
        "train_logs": train_logs,
        "train_counts_by_log": train_counts,
        "decision_counts": counts,
        "decisions": decisions,
        "report_only": True,
        "mutates_answer": False,
        "mutates_selector_policy": False,
        "mutates_memory": False,
        "mutates_config": False,
    }
