"""OGCF signal integration for the retrieval pipeline and selector.

This module computes OGCF-derived features from retrieval rows and adds them
to the feature set used by the CLC policy selector.
"""
from __future__ import annotations

from typing import Any

from core.ogcf_intent import classify_ogcf_intent, normalize_ogcf_intent_config


class OGCFSignalProvider:
    """Compute OGCF-derived signals from retrieval context.

    The provider is stateless and lightweight so it can be called per-query
    without heavy geometry recomputation. It expects pre-computed OGCF
    geometry metadata (cluster assignments, loop scores) to be injected
    from a periodic background analysis.
    """

    def __init__(
        self,
        ogcf_meta: dict[str, Any] | None = None,
        intent_config: dict[str, Any] | None = None,
    ):
        self.meta = dict(ogcf_meta or {})
        self.intent_config = normalize_ogcf_intent_config(intent_config)

    def update_meta(self, ogcf_meta: dict[str, Any]) -> None:
        """Replace the cached OGCF geometry metadata."""
        self.meta = dict(ogcf_meta)

    def signals_for_retrieval_rows(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return OGCF-derived scalar signals for a set of retrieval rows.

        The signals are designed to slot into the existing selector feature
        computation in selector_runtime.py.
        """
        if not rows or not self.meta:
            return {
                "ogcf_bridge_overload_score": 0.0,
                "ogcf_max_interaction_z": 0.0,
                "ogcf_loop_count": 0,
                "ogcf_risk_region_count": 0,
                "ogcf_cluster_count": 0,
                "ogcf_affected_memory_ratio": 0.0,
                "ogcf_weighted_affected_memory_ratio": 0.0,
            }

        max_z = float(self.meta.get("max_interaction_z", 0.0))
        bridge_score = float(self.meta.get("bridge_overload_score", 0.0))
        loop_count = int(self.meta.get("loop_count", 0))
        risk_regions = list(self.meta.get("risk_regions", []))
        cluster_summary = list(self.meta.get("cluster_summary", []))
        bridge_clusters = list(self.meta.get("bridge_clusters", []))

        # Count how many retrieved memories are in high-risk clusters
        risk_cluster_ids: set[int] = set()
        for region in risk_regions:
            if region.get("interaction_z", 0.0) >= 2.0:
                for cid in str(region.get("clusters", "")).split("-"):
                    try:
                        risk_cluster_ids.add(int(cid))
                    except ValueError:
                        pass
        for bc in bridge_clusters:
            risk_cluster_ids.add(bc["cluster_id"])

        # Map memory_id -> cluster_id from meta if available
        memory_cluster_map: dict[str, int] = dict(self.meta.get("memory_cluster_map", {}))
        affected = 0
        weighted_affected = 0.0
        total_weight = 0.0
        top_score = max(
            0.0,
            max((float(row.get("score") or row.get("cosine") or 0.0) for row in rows), default=0.0),
        )
        for rank, row in enumerate(rows, start=1):
            score = max(0.0, float(row.get("score") or row.get("cosine") or 0.0))
            score_weight = score / top_score if top_score > 1e-12 else 1.0
            lexical_weight = max(
                0.0,
                float(row.get("text_match_score") or 0.0),
                float(row.get("claim_scope_score") or 0.0),
                float(row.get("answer_type_score") or 0.0),
            )
            rank_weight = 1.0 / (1.0 + 0.18 * max(0, rank - 1))
            relevance_weight = max(0.05, min(1.0, 0.55 * score_weight + 0.45 * lexical_weight))
            weight = rank_weight * relevance_weight
            total_weight += weight
            mid = str(row.get("id") or row.get("memory_id") or "")
            cid = memory_cluster_map.get(mid, -1)
            if cid in risk_cluster_ids:
                affected += 1
                weighted_affected += weight
        affected_ratio = affected / max(1, len(rows))
        weighted_affected_ratio = weighted_affected / max(total_weight, 1e-12)

        # Risk region count above threshold
        risk_count = sum(1 for r in risk_regions if r.get("interaction_z", 0.0) >= 2.0)

        return {
            "ogcf_bridge_overload_score": round(bridge_score, 6),
            "ogcf_max_interaction_z": round(max_z, 6),
            "ogcf_loop_count": loop_count,
            "ogcf_risk_region_count": risk_count,
            "ogcf_cluster_count": len(cluster_summary),
            "ogcf_affected_memory_ratio": round(affected_ratio, 6),
            "ogcf_weighted_affected_memory_ratio": round(weighted_affected_ratio, 6),
        }

    def selector_features(
        self,
        rows: list[dict[str, Any]],
        base_stale_ratio: float = 0.0,
        base_contradiction_peak: float = 0.0,
        query: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Compute OGCF-augmented selector features.

        Returns (augmented_features, diagnostics) where the augmented features
        can be merged into CLCPolicyFeatures.
        """
        signals = self.signals_for_retrieval_rows(rows)
        bridge_score = signals["ogcf_bridge_overload_score"]
        affected_ratio = signals["ogcf_affected_memory_ratio"]
        weighted_affected_ratio = signals.get("ogcf_weighted_affected_memory_ratio", affected_ratio)
        risk_region_count = int(signals.get("ogcf_risk_region_count", 0) or 0)
        intent = classify_ogcf_intent(query, rows, self.intent_config)
        gate = self.intent_config["gate"]
        if bridge_score <= 0.0 and risk_region_count <= 0:
            if intent.score >= float(gate["high_intent_threshold"]):
                effective_affected_ratio = max(
                    weighted_affected_ratio,
                    affected_ratio * float(gate["high_affected_multiplier"]),
                )
            elif intent.score >= float(gate["medium_intent_threshold"]):
                effective_affected_ratio = (
                    weighted_affected_ratio
                    if weighted_affected_ratio >= float(gate["medium_min_weighted_ratio"])
                    else 0.0
                )
            else:
                effective_affected_ratio = (
                    0.0
                    if weighted_affected_ratio < float(gate["low_min_weighted_ratio"])
                    else weighted_affected_ratio
                )
        else:
            effective_affected_ratio = max(weighted_affected_ratio, affected_ratio * bridge_score)

        # Adjust stale pressure estimate using bridge overload
        # If bridge_score is high and affected memories are retrieved,
        # the memory graph has structural instability
        adjusted_stale_ratio = min(1.0, base_stale_ratio + 0.25 * effective_affected_ratio * bridge_score)
        adjusted_contradiction_peak = max(
            base_contradiction_peak,
            bridge_score * 0.5,  # bridge overload contributes to conflict signal
        )

        # CSD ratio boost from bridge overload
        csd_ratio_boost = 0.3 * bridge_score + 0.2 * effective_affected_ratio

        features = {
            "ogcf_bridge_overload_score": bridge_score,
            "ogcf_affected_memory_ratio": affected_ratio,
            "ogcf_weighted_affected_memory_ratio": weighted_affected_ratio,
            "ogcf_effective_affected_memory_ratio": round(effective_affected_ratio, 6),
            "ogcf_intent": intent.intent,
            "ogcf_intent_score": round(intent.score, 6),
            "ogcf_intent_reason": intent.reason,
            "adjusted_stale_ratio": round(adjusted_stale_ratio, 6),
            "adjusted_contradiction_peak": round(adjusted_contradiction_peak, 6),
            "csd_ratio_boost": round(csd_ratio_boost, 6),
        }
        diagnostics = {**signals, **features}
        return features, diagnostics


def merge_ogcf_into_retrieval_rows(
    rows: list[dict[str, Any]],
    ogcf_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    """Add per-row OGCF flags (e.g., bridge_cluster membership) to retrieval rows."""
    memory_cluster_map: dict[str, int] = dict(ogcf_meta.get("memory_cluster_map", {}))
    bridge_cluster_ids: set[int] = {
        bc["cluster_id"] for bc in ogcf_meta.get("bridge_clusters", [])
    }
    risk_cluster_ids: set[int] = set()
    for region in ogcf_meta.get("risk_regions", []):
        if region.get("interaction_z", 0.0) >= 2.0:
            for cid in str(region.get("clusters", "")).split("-"):
                try:
                    risk_cluster_ids.add(int(cid))
                except ValueError:
                    pass

    for row in rows:
        mid = str(row.get("id") or row.get("memory_id") or "")
        cid = memory_cluster_map.get(mid, -1)
        row["ogcf_cluster_id"] = cid
        row["ogcf_in_bridge_cluster"] = cid in bridge_cluster_ids
        row["ogcf_in_risk_region"] = cid in risk_cluster_ids
        if cid in bridge_cluster_ids:
            row["ogcf_bridge_penalty"] = 0.15
        elif cid in risk_cluster_ids:
            row["ogcf_bridge_penalty"] = 0.05
        else:
            row["ogcf_bridge_penalty"] = 0.0

    return rows
