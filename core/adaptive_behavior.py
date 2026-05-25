from __future__ import annotations

from typing import Any


DEFAULT_SUPERFAMILIES = {
    "supported_evidence": ("answer_correct", "answer_good_citation", "answer_bad_citation"),
    "ogcf_bridge_warning": ("answer_bridge_warning_useful", "answer_bridge_warning_noise"),
    "missing_support": ("answer_missing_support", "answer_overconfident"),
    "stale_conflict": ("answer_stale", "answer_conflict_not_disclosed"),
}

DEFAULT_SHADOW = {
    "enabled": False,
    "include_in_outcome_log": False,
    "positive_threshold": 0.65,
    "negative_threshold": 0.35,
    "min_route_confidence": 0.35,
    "require_promotion_guard": True,
}


def split_terms(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        raw = str(value or "").replace("|", ",").split(",")
    return [item.strip().lower() for item in raw if item.strip()]


def normalize_adaptive_behavior_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = config if isinstance(config, dict) else {}
    raw_superfamilies = raw.get("superfamilies")
    superfamilies: dict[str, list[str]] = {
        name: list(labels)
        for name, labels in DEFAULT_SUPERFAMILIES.items()
    }
    if isinstance(raw_superfamilies, dict):
        for family, labels in raw_superfamilies.items():
            family_name = str(family or "").strip().lower()
            if family_name:
                parsed = split_terms(labels)
                if parsed:
                    superfamilies[family_name] = parsed
    label_to_superfamily = {
        label: family
        for family, labels in superfamilies.items()
        for label in labels
    }
    shadow = dict(DEFAULT_SHADOW)
    raw_shadow = raw.get("shadow")
    if isinstance(raw_shadow, dict):
        for key in DEFAULT_SHADOW:
            if key in raw_shadow:
                shadow[key] = raw_shadow[key]
    for key in ("positive_threshold", "negative_threshold", "min_route_confidence"):
        try:
            shadow[key] = float(shadow[key])
        except (TypeError, ValueError):
            shadow[key] = float(DEFAULT_SHADOW[key])
    shadow["enabled"] = bool(shadow.get("enabled"))
    shadow["include_in_outcome_log"] = bool(shadow.get("include_in_outcome_log"))
    shadow["require_promotion_guard"] = bool(shadow.get("require_promotion_guard"))
    return {
        "schema": "adaptive_behavior_config/v1",
        "superfamilies": superfamilies,
        "label_to_superfamily": label_to_superfamily,
        "shadow": shadow,
    }


def superfamily_for_label(label: str, config: dict[str, Any] | None = None) -> str:
    normalized = normalize_adaptive_behavior_config(config)
    value = str(label or "").strip().lower()
    return normalized["label_to_superfamily"].get(value, value or "unknown")
