from __future__ import annotations

import re
from typing import Any, Callable


CURRENT_THRESHOLD = 0.30
STALE_THRESHOLD = -0.25
SENSITIVE_LOOKUP_TERMS = {
    "address",
    "email",
    "key",
    "license",
    "passport",
    "password",
    "phone",
    "private",
    "secret",
    "signing",
    "ssn",
    "token",
}
DEFAULT_STALE_LANGUAGE_TERMS = (
    "not final truth",
    "marked stale",
    "stale memory",
    "superseded",
    "no longer current",
    "historical but no longer current",
)
DEFAULT_STALE_REGEX = r"\bold\s+(policy|memory|fact|rule|preference|profile|deployment|geometry|evidence|version|value)\b"
DEFAULT_CORRECTION_LANGUAGE_TERMS = (
    "correction:",
    "must not",
    "only when",
    "prefer the corrected",
    "no longer current",
)
DEFAULT_EVIDENCE_STATE_CONFIG = {
    "current_threshold": CURRENT_THRESHOLD,
    "stale_threshold": STALE_THRESHOLD,
    "stale_feedback_threshold": -0.5,
    "disputed_feedback_threshold": -0.2,
    "stale_language_terms": DEFAULT_STALE_LANGUAGE_TERMS,
    "stale_regex": DEFAULT_STALE_REGEX,
    "correction_language_terms": DEFAULT_CORRECTION_LANGUAGE_TERMS,
    "sensitive_lookup_terms": tuple(sorted(SENSITIVE_LOOKUP_TERMS)),
    "weak_evidence": {
        "score_threshold": 0.20,
        "text_match_threshold": 0.50,
        "intent_match_threshold": 0.80,
        "intent_text_match_threshold": 0.30,
    },
}


def normalize_evidence_state_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    weak_cfg = dict(cfg.get("weak_evidence") or {})
    default_weak = DEFAULT_EVIDENCE_STATE_CONFIG["weak_evidence"]
    return {
        "current_threshold": _float_value(cfg.get("current_threshold"), CURRENT_THRESHOLD),
        "stale_threshold": _float_value(cfg.get("stale_threshold"), STALE_THRESHOLD),
        "stale_feedback_threshold": _float_value(cfg.get("stale_feedback_threshold"), -0.5),
        "disputed_feedback_threshold": _float_value(cfg.get("disputed_feedback_threshold"), -0.2),
        "stale_language_terms": parse_term_sequence(
            cfg.get("stale_language_terms"),
            DEFAULT_STALE_LANGUAGE_TERMS,
        ),
        "stale_regex": str(cfg.get("stale_regex") or DEFAULT_STALE_REGEX),
        "correction_language_terms": parse_term_sequence(
            cfg.get("correction_language_terms"),
            DEFAULT_CORRECTION_LANGUAGE_TERMS,
        ),
        "sensitive_lookup_terms": parse_term_sequence(
            cfg.get("sensitive_lookup_terms"),
            tuple(sorted(SENSITIVE_LOOKUP_TERMS)),
        ),
        "weak_evidence": {
            "score_threshold": _float_value(weak_cfg.get("score_threshold"), default_weak["score_threshold"]),
            "text_match_threshold": _float_value(
                weak_cfg.get("text_match_threshold"),
                default_weak["text_match_threshold"],
            ),
            "intent_match_threshold": _float_value(
                weak_cfg.get("intent_match_threshold"),
                default_weak["intent_match_threshold"],
            ),
            "intent_text_match_threshold": _float_value(
                weak_cfg.get("intent_text_match_threshold"),
                default_weak["intent_text_match_threshold"],
            ),
        },
    }


def parse_term_sequence(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(term).strip().lower() for term in value if str(term).strip())
    raw = str(value or "")
    for separator in ("|", ";"):
        raw = raw.replace(separator, ",")
    parsed = tuple(term.strip().lower() for term in raw.split(",") if term.strip())
    return parsed or tuple(default)


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_memory_state(item: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    cfg = normalize_evidence_state_config(config)
    supersession = float(item.get("supersession_score") or 0.0)
    relation_supersession = float(item.get("relation_supersession_score") or 0.0)
    summary_relation = float(item.get("summary_relation_score") or 0.0)
    feedback = float(item.get("feedback_score") or 0.0)
    text = str(item.get("text") or "").lower()
    authority_state = str(item.get("authority_state") or "").strip().lower()

    if text.startswith("consolidated summary:") or (summary_relation > 0.0 and "source memory ids:" in text):
        return "summary"
    if authority_state == "current":
        return "current"
    if authority_state == "superseded" or item.get("superseded_by_memory_ids"):
        return "stale"

    stale_language = any(
        term in text for term in cfg["stale_language_terms"]
    ) or bool(re.search(str(cfg["stale_regex"]), text))
    correction_language = any(term in text for term in cfg["correction_language_terms"])

    if (
        supersession <= float(cfg["stale_threshold"])
        or relation_supersession < 0.0
        or feedback <= float(cfg["stale_feedback_threshold"])
    ):
        return "stale"
    if feedback < float(cfg["disputed_feedback_threshold"]):
        return "disputed"
    if supersession >= float(cfg["current_threshold"]):
        return "current"
    if relation_supersession > 0.0 and correction_language:
        return "current"
    if correction_language and not stale_language:
        return "current"
    if stale_language:
        return "stale"
    return "historical"


def evidence_is_too_weak(evidence: list[dict[str, Any]], config: dict[str, Any] | None = None) -> bool:
    if not evidence:
        return False
    cfg = normalize_evidence_state_config(config)["weak_evidence"]
    top_score = max(float(item.get("score") or 0.0) for item in evidence)
    top_text_match = max(float(item.get("text_match_score") or 0.0) for item in evidence)
    top_intent_match = max(float(item.get("intent_match_score") or 0.0) for item in evidence)
    has_authority_signal = any(
        float(item.get("supersession_score") or 0.0) > 0.0
        or float(item.get("relation_supersession_score") or 0.0) > 0.0
        or float(item.get("stored_contradiction_score") or 0.0) > 0.0
        for item in evidence
    )
    if has_authority_signal:
        return False
    if top_intent_match >= float(cfg["intent_match_threshold"]) and top_text_match >= float(
        cfg["intent_text_match_threshold"]
    ):
        return False
    return top_score < float(cfg["score_threshold"]) and top_text_match < float(cfg["text_match_threshold"])


def requires_sensitive_evidence(
    query: str,
    normalized_terms_fn: Callable[[Any], set[str]] | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    if normalized_terms_fn is None:
        terms = _basic_terms(query)
    else:
        terms = normalized_terms_fn(query)
    sensitive_terms = set(normalize_evidence_state_config(config)["sensitive_lookup_terms"])
    return bool(terms & sensitive_terms)


def _basic_terms(text: Any) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return {token for token in cleaned.split() if len(token) > 1}
