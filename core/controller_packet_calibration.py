from __future__ import annotations

from typing import Any


DEFAULT_BRIDGE_SCORER_MIN_TEST_SAMPLES = 4
DEFAULT_BRIDGE_LOSO_MIN_SOURCES = 3
DEFAULT_BRIDGE_LOSO_MIN_SAMPLES = 30
DEFAULT_READINESS_MIN_PACKETS_FOR_RUNTIME_COLLECTION = 12
DEFAULT_READINESS_MIN_SOURCES_FOR_RUNTIME_COLLECTION = 2
DEFAULT_READINESS_MIN_PACKETS_FOR_LEARNED_SCORER_EVAL = 30
DEFAULT_READINESS_MIN_SOURCES_FOR_LEARNED_SCORER_EVAL = 3


def positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "on", "1"}:
            return True
        if low in {"false", "no", "off", "0"}:
            return False
    return default


def controller_packet_calibration_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    root = config if isinstance(config, dict) else {}
    value = root.get("controller_packet_calibration")
    return value if isinstance(value, dict) else {}


def normalize_bridge_scorer_policy(
    config: dict[str, Any] | None = None,
    *,
    min_test_samples: int | None = None,
) -> dict[str, Any]:
    controller = controller_packet_calibration_config(config)
    scorer = controller.get("bridge_scorer") if isinstance(controller.get("bridge_scorer"), dict) else {}
    resolved_min = positive_int(
        scorer.get("min_test_samples_for_candidate"),
        DEFAULT_BRIDGE_SCORER_MIN_TEST_SAMPLES,
    )
    if min_test_samples is not None:
        resolved_min = positive_int(min_test_samples, resolved_min)
    return {
        "schema": "controller_packet_bridge_scorer_policy/v1",
        "min_test_samples_for_candidate": resolved_min,
        "require_zero_false_positives": bool_value(scorer.get("require_zero_false_positives"), True),
        "require_zero_false_negatives": bool_value(scorer.get("require_zero_false_negatives"), True),
        "require_not_worse_than_symbolic": bool_value(scorer.get("require_not_worse_than_symbolic"), True),
        "source": "config_with_cli_overrides" if min_test_samples is not None else "config_or_defaults",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def normalize_bridge_loso_policy(
    config: dict[str, Any] | None = None,
    *,
    min_sources: int | None = None,
    min_samples: int | None = None,
) -> dict[str, Any]:
    controller = controller_packet_calibration_config(config)
    loso = (
        controller.get("bridge_leave_one_source_out")
        if isinstance(controller.get("bridge_leave_one_source_out"), dict)
        else {}
    )
    resolved_sources = positive_int(loso.get("min_sources_for_candidate"), DEFAULT_BRIDGE_LOSO_MIN_SOURCES)
    resolved_samples = positive_int(loso.get("min_samples_for_candidate"), DEFAULT_BRIDGE_LOSO_MIN_SAMPLES)
    if min_sources is not None:
        resolved_sources = positive_int(min_sources, resolved_sources)
    if min_samples is not None:
        resolved_samples = positive_int(min_samples, resolved_samples)
    return {
        "schema": "controller_packet_bridge_loso_policy/v1",
        "min_sources_for_candidate": resolved_sources,
        "min_samples_for_candidate": resolved_samples,
        "source": "config_with_cli_overrides" if min_sources is not None or min_samples is not None else "config_or_defaults",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def normalize_real_log_readiness_policy(config: dict[str, Any] | None = None) -> dict[str, Any]:
    controller = controller_packet_calibration_config(config)
    readiness = controller.get("real_log_readiness") if isinstance(controller.get("real_log_readiness"), dict) else {}
    return {
        "schema": "controller_packet_real_log_readiness_policy/v1",
        "min_packets_for_runtime_collection": positive_int(
            readiness.get("min_packets_for_runtime_collection"),
            DEFAULT_READINESS_MIN_PACKETS_FOR_RUNTIME_COLLECTION,
        ),
        "min_sources_for_runtime_collection": positive_int(
            readiness.get("min_sources_for_runtime_collection"),
            DEFAULT_READINESS_MIN_SOURCES_FOR_RUNTIME_COLLECTION,
        ),
        "min_packets_for_learned_scorer_evaluation": positive_int(
            readiness.get("min_packets_for_learned_scorer_evaluation"),
            DEFAULT_READINESS_MIN_PACKETS_FOR_LEARNED_SCORER_EVAL,
        ),
        "min_sources_for_learned_scorer_evaluation": positive_int(
            readiness.get("min_sources_for_learned_scorer_evaluation"),
            DEFAULT_READINESS_MIN_SOURCES_FOR_LEARNED_SCORER_EVAL,
        ),
        "require_full_evidence_context_feature_coverage": bool_value(
            readiness.get("require_full_evidence_context_feature_coverage"),
            True,
        ),
        "block_on_review_items": bool_value(readiness.get("block_on_review_items"), True),
        "source": "config_or_defaults",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def normalize_controller_packet_calibration_policy(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "controller_packet_calibration_policy/v1",
        "bridge_scorer": normalize_bridge_scorer_policy(config),
        "bridge_leave_one_source_out": normalize_bridge_loso_policy(config),
        "real_log_readiness": normalize_real_log_readiness_policy(config),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
