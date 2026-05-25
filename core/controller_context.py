from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.clc_policy_selector import CLCPolicyDecision, CLCPolicyFeatures
from core.ogcf_selector import augment_selector_features
from core.selector_runtime import (
    apply_retrieval_policy_guard,
    build_policy_selector,
    selector_features_from_payload,
    selector_features_from_retrieval_context,
)


@dataclass(frozen=True)
class AdaptiveMemoryContext:
    """Shared controller context for selector, resolver-shadow, and outcome logs."""

    ok: bool
    features: CLCPolicyFeatures | dict[str, Any]
    diagnostics: dict[str, Any]
    retrieval_context: list[dict[str, Any]]
    ogcf_meta_present: bool
    decision: CLCPolicyDecision | None = None
    error: str | None = None

    def selector_snapshot(self) -> dict[str, Any]:
        if not self.ok:
            return {"ok": False, "error": self.error or "controller_context_error"}
        decision = self.decision
        return {
            "ok": True,
            "schema": "adaptive_memory_context/v1",
            "ogcf_meta_present": self.ogcf_meta_present,
            "decision": (
                {
                    "policy": decision.policy,
                    "action": decision.action,
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                }
                if decision
                else None
            ),
            "diagnostics": self.diagnostics,
        }

    def selector_context(self) -> dict[str, Any]:
        return {
            "schema": "adaptive_memory_context/v1",
            "diagnostics": self.diagnostics,
            "retrieval_context": self.retrieval_context,
            "ogcf_meta_present": self.ogcf_meta_present,
        }

    def feature_dict(self) -> dict[str, Any]:
        return asdict(self.features) if isinstance(self.features, CLCPolicyFeatures) else dict(self.features)


def build_adaptive_memory_context(
    *,
    root: Path,
    config: dict[str, Any] | None,
    payload: dict[str, Any],
    retrieval_rows: list[dict[str, Any]] | None = None,
    include_decision: bool = True,
) -> AdaptiveMemoryContext:
    """Build the shared adaptive-memory controller context.

    This centralizes retrieval-derived selector features, optional OGCF feature
    augmentation, and guarded policy selection so API handlers and future
    learning/eval tools consume the same context schema.
    """

    rows = [row for row in (retrieval_rows or []) if isinstance(row, dict)]
    try:
        if rows:
            features, diagnostics = selector_features_from_retrieval_context(
                rows,
                condition_name=str(payload.get("condition_name") or "hard_budget144"),
                label_cost=float(payload.get("label_cost", 0.0002) or 0.0002),
                budget_pressure=float(payload.get("budget_pressure", 0.2) or 0.2),
            )
            ogcf_meta = payload.get("ogcf_meta")
            ogcf_meta_present = isinstance(ogcf_meta, dict) and bool(ogcf_meta)
            if ogcf_meta_present:
                features, diagnostics = augment_selector_features(
                    features,
                    rows,
                    ogcf_meta,
                    diagnostics,
                    query=str(payload.get("query") or payload.get("question") or payload.get("q") or ""),
                    ogcf_intent_config=_ogcf_intent_config(config),
                )
        else:
            features = selector_features_from_payload(payload)
            diagnostics = {}
            ogcf_meta_present = False

        decision = None
        if include_decision:
            selector = build_policy_selector(root, config)
            decision = selector.select(features)
            if rows:
                decision = apply_retrieval_policy_guard(decision, features, diagnostics)

        return AdaptiveMemoryContext(
            ok=True,
            features=features,
            diagnostics=diagnostics,
            retrieval_context=rows,
            ogcf_meta_present=ogcf_meta_present,
            decision=decision,
        )
    except Exception as exc:
        return AdaptiveMemoryContext(
            ok=False,
            features={},
            diagnostics={},
            retrieval_context=rows,
            ogcf_meta_present=False,
            decision=None,
            error=str(exc),
        )


def _ogcf_intent_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = (config or {}).get("ogcf_intent")
    return raw if isinstance(raw, dict) else None
