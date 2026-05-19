from __future__ import annotations

from pathlib import Path
from typing import Any

from core.clc_policy_selector import (
    CLCLearnedPolicySelector,
    CLCPolicyFeatures,
    CLCPolicySelector,
    CLCPolicyDecision,
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
