"""OGCF integration layer for the CLC policy selector.

This module bridges OGCF geometry signals with the existing selector runtime
so that bridge overload and composition instability feed into policy decisions.
"""
from __future__ import annotations

from typing import Any

from core.clc_policy_selector import CLCPolicyFeatures, CLCPolicyDecision
from core.ogcf_signals import OGCFSignalProvider


def augment_selector_features(
    features: CLCPolicyFeatures,
    retrieval_rows: list[dict[str, Any]],
    ogcf_meta: dict[str, Any] | None,
    base_diagnostics: dict[str, Any] | None = None,
) -> tuple[CLCPolicyFeatures, dict[str, Any]]:
    """Augment CLCPolicyFeatures with OGCF-derived signals.

    This is the main integration point. It takes the base features computed by
    selector_features_from_retrieval_context() and adds OGCF geometry-based
    adjustments to memory_bad_rate, probe_drop, and csd_ratio.
    """
    provider = OGCFSignalProvider(ogcf_meta)
    ogcf_feats, ogcf_diag = provider.selector_features(
        retrieval_rows,
        base_stale_ratio=base_diagnostics.get("stale_ratio", 0.0) if base_diagnostics else 0.0,
        base_contradiction_peak=base_diagnostics.get("contradiction_peak", 0.0) if base_diagnostics else 0.0,
    )
    effective_affected_ratio = float(
        ogcf_feats.get("ogcf_effective_affected_memory_ratio", ogcf_feats.get("ogcf_affected_memory_ratio", 0.0))
        or 0.0
    )

    # Adjust features
    adjusted_memory_bad_rate = min(
        0.98,
        features.memory_bad_rate + 0.15 * ogcf_feats["ogcf_bridge_overload_score"],
    )
    adjusted_probe_drop = min(
        0.98,
        features.probe_drop + 0.10 * effective_affected_ratio,
    )
    adjusted_csd_ratio = min(
        3.5,
        features.csd_ratio + ogcf_feats["csd_ratio_boost"],
    )

    # Create new features (immutable dataclass workaround)
    import dataclasses
    field_values = {f.name: getattr(features, f.name) for f in dataclasses.fields(features)}
    field_values["memory_bad_rate"] = adjusted_memory_bad_rate
    field_values["probe_drop"] = adjusted_probe_drop
    field_values["csd_ratio"] = adjusted_csd_ratio
    new_features = CLCPolicyFeatures(**field_values)

    diagnostics = dict(base_diagnostics or {})
    diagnostics.update(ogcf_diag)
    diagnostics["ogcf_memory_bad_rate_delta"] = round(
        adjusted_memory_bad_rate - features.memory_bad_rate, 6
    )
    diagnostics["ogcf_csd_ratio_delta"] = round(
        adjusted_csd_ratio - features.csd_ratio, 6
    )

    return new_features, diagnostics


def select_with_ogcf(
    selector,
    features: CLCPolicyFeatures,
    retrieval_rows: list[dict[str, Any]],
    ogcf_meta: dict[str, Any] | None,
    base_diagnostics: dict[str, Any] | None = None,
) -> tuple[CLCPolicyDecision, dict[str, Any]]:
    """Run policy selection with OGCF-augmented features.

    This wraps the selector's select() method, pre-augmenting features with
    OGCF geometry signals before the decision.
    """
    aug_features, diagnostics = augment_selector_features(
        features, retrieval_rows, ogcf_meta, base_diagnostics
    )
    decision = selector.select(aug_features)
    diagnostics["policy"] = decision.policy
    diagnostics["action"] = decision.action
    diagnostics["confidence"] = decision.confidence
    return decision, diagnostics
