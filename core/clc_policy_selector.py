from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


POLICY_PERIODIC = "periodic_baseline"
POLICY_LONG_SEVERE = "long_severe_r16_overwrite"
POLICY_XSEQ_MEMORY = "xseq_memory_r45_badmajority"
POLICY_ACTIONS = {
    POLICY_PERIODIC: "PROTECT_PERIODIC",
    POLICY_LONG_SEVERE: "LONG_SEVERE_VERIFIED_REFRESH",
    POLICY_XSEQ_MEMORY: "XSEQ_MEMORY_REFRESH",
}
POLICY_COST = {
    POLICY_PERIODIC: 0.0,
    POLICY_LONG_SEVERE: 0.015,
    POLICY_XSEQ_MEMORY: 0.025,
}
POLICY_ORDER = (POLICY_PERIODIC, POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY)


@dataclass(frozen=True)
class CLCPolicyFeatures:
    """Small, portable state summary for CLC policy selection."""

    budget_units: float
    cycles: float
    hard: bool = False
    long_stream: bool = False
    csd_ratio: float = 0.0
    probe_drop: float = 0.0
    label_cost: float = 0.0002
    budget_pressure: float = 0.0
    recent_return_mean: float = 0.0
    memory_bad_rate: float = 0.0

    @classmethod
    def from_condition_name(
        cls,
        condition_name: str,
        *,
        budget_units: float | None = None,
        cycles: float | None = None,
        **kwargs: Any,
    ) -> "CLCPolicyFeatures":
        name = str(condition_name or "").lower()
        inferred_long = "long2" in name or "long" in name
        inferred_hard = "hard" in name
        inferred_budget = 288.0 if inferred_long else 144.0
        inferred_cycles = 2.0 if inferred_long else 1.0
        return cls(
            budget_units=float(budget_units if budget_units is not None else inferred_budget),
            cycles=float(cycles if cycles is not None else inferred_cycles),
            hard=inferred_hard,
            long_stream=inferred_long,
            **kwargs,
        )


@dataclass(frozen=True)
class CLCPolicyDecision:
    policy: str
    action: str
    reason: str
    confidence: float


@dataclass(frozen=True)
class CLCLearnedPolicySample:
    features: CLCPolicyFeatures
    policy: str
    weight: float = 1.0
    source: str = ""


class CLCPolicySelector:
    """Conservative selector learned from the CSD/G-CL experiments.

    The selector is intentionally tiny and dependency-free so an agent
    orchestrator can call it before deciding whether to spend labels,
    refresh an adapter, or stay in PROTECT/periodic mode.
    """

    def __init__(
        self,
        *,
        label_cost_ceiling: float = 0.00025,
        high_budget_pressure: float = 0.9,
    ):
        self.label_cost_ceiling = float(label_cost_ceiling)
        self.high_budget_pressure = float(high_budget_pressure)

    def select(self, features: CLCPolicyFeatures | dict[str, Any]) -> CLCPolicyDecision:
        f = self._normalize(features)
        if f.label_cost > self.label_cost_ceiling:
            return CLCPolicyDecision(
                policy=POLICY_PERIODIC,
                action="PROTECT_PERIODIC",
                reason="label_cost_above_break_even",
                confidence=0.86,
            )
        if f.budget_pressure >= self.high_budget_pressure:
            return CLCPolicyDecision(
                policy=POLICY_PERIODIC,
                action="PROTECT_PERIODIC",
                reason="budget_pressure_high",
                confidence=0.80,
            )
        if f.long_stream:
            return CLCPolicyDecision(
                policy=POLICY_PERIODIC,
                action="PROTECT_PERIODIC",
                reason="long_stream_periodic_won_fresh_validation",
                confidence=0.74,
            )
        if f.hard:
            return CLCPolicyDecision(
                policy=POLICY_XSEQ_MEMORY,
                action="XSEQ_MEMORY_REFRESH",
                reason="short_hard_stream_memory_positive",
                confidence=0.72,
            )
        return CLCPolicyDecision(
            policy=POLICY_LONG_SEVERE,
            action="LONG_SEVERE_VERIFIED_REFRESH",
            reason="short_standard_stream_verified_refresh_positive",
            confidence=0.70,
        )

    def explain(self, features: CLCPolicyFeatures | dict[str, Any], *, top_k: int | None = None) -> dict[str, Any]:
        f = self._normalize(features)
        decision = self.select(f)
        return {
            "selector_class": self.__class__.__name__,
            "features": asdict(f),
            "decision": _decision_dict(decision),
            "guardrails": {
                "label_cost_ceiling": self.label_cost_ceiling,
                "high_budget_pressure": self.high_budget_pressure,
            },
            "nearest_samples": [],
            "votes": {},
            "total_vote": 0.0,
            "sample_count": 0,
            "explanation": decision.reason,
        }

    def _normalize(self, features: CLCPolicyFeatures | dict[str, Any]) -> CLCPolicyFeatures:
        if isinstance(features, CLCPolicyFeatures):
            return features
        if "condition_name" in features:
            return CLCPolicyFeatures.from_condition_name(
                str(features.get("condition_name") or ""),
                budget_units=features.get("budget_units"),
                cycles=features.get("cycles"),
                csd_ratio=float(features.get("csd_ratio", 0.0) or 0.0),
                probe_drop=float(features.get("probe_drop", 0.0) or 0.0),
                label_cost=float(features.get("label_cost", 0.0002) or 0.0002),
                budget_pressure=float(features.get("budget_pressure", 0.0) or 0.0),
                recent_return_mean=float(features.get("recent_return_mean", 0.0) or 0.0),
                memory_bad_rate=float(features.get("memory_bad_rate", 0.0) or 0.0),
            )
        return CLCPolicyFeatures(
            budget_units=float(features.get("budget_units", 144.0) or 144.0),
            cycles=float(features.get("cycles", 1.0) or 1.0),
            hard=bool(features.get("hard", False)),
            long_stream=bool(features.get("long_stream", False)),
            csd_ratio=float(features.get("csd_ratio", 0.0) or 0.0),
            probe_drop=float(features.get("probe_drop", 0.0) or 0.0),
            label_cost=float(features.get("label_cost", 0.0002) or 0.0002),
            budget_pressure=float(features.get("budget_pressure", 0.0) or 0.0),
            recent_return_mean=float(features.get("recent_return_mean", 0.0) or 0.0),
            memory_bad_rate=float(features.get("memory_bad_rate", 0.0) or 0.0),
        )


def _feature_vector(features: CLCPolicyFeatures) -> tuple[float, ...]:
    return (
        1.0 if features.hard else 0.0,
        1.0 if features.long_stream else 0.0,
        features.budget_units / 288.0,
        features.cycles / 2.0,
        features.csd_ratio,
        features.probe_drop,
        features.label_cost / 0.0002,
        features.budget_pressure,
        features.memory_bad_rate,
        features.recent_return_mean,
    )


def _distance(a: CLCPolicyFeatures, b: CLCPolicyFeatures) -> float:
    av = _feature_vector(a)
    bv = _feature_vector(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(av, bv)))


def _policy_action(policy: str) -> str:
    return POLICY_ACTIONS.get(policy, "PROTECT_PERIODIC")


def _decision_dict(decision: CLCPolicyDecision) -> dict[str, Any]:
    return {
        "policy": decision.policy,
        "action": decision.action,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def _normalize_features(features: CLCPolicyFeatures | dict[str, Any]) -> CLCPolicyFeatures:
    return CLCPolicySelector()._normalize(features)


def _features_from_outcome_row(row: dict[str, Any]) -> CLCPolicyFeatures:
    family = str(row.get("family") or "").lower()
    condition = str(row.get("condition_name") or "")
    kwargs: dict[str, Any] = {}
    if family == "hard_bad_majority":
        kwargs = {"memory_bad_rate": 0.75, "probe_drop": 0.18, "csd_ratio": 1.4}
    elif family == "standard_update":
        kwargs = {"memory_bad_rate": 0.25, "probe_drop": 0.08, "csd_ratio": 0.9}
    elif family == "long_topic":
        kwargs = {"memory_bad_rate": 0.35, "probe_drop": 0.04, "csd_ratio": 0.7}
    elif family == "long_session":
        kwargs = {"memory_bad_rate": 0.2, "probe_drop": 0.03, "csd_ratio": 0.6}
    return CLCPolicyFeatures.from_condition_name(condition, **kwargs)


class CLCLearnedPolicySelector:
    """Tiny kNN selector over CLC/CSD/G-CL outcome labels.

    This selector is deliberately small: it turns validated outcome rows into
    nearest-neighbor policy choices, then falls back to the conservative CLC
    selector when no useful labels exist.
    """

    def __init__(
        self,
        samples: list[CLCLearnedPolicySample] | None = None,
        *,
        k: int = 3,
        fallback: CLCPolicySelector | None = None,
        label_cost_ceiling: float = 0.00025,
        high_budget_pressure: float = 0.9,
    ):
        self.samples = list(samples or [])
        self.k = max(1, int(k))
        self.fallback = fallback or CLCPolicySelector(
            label_cost_ceiling=label_cost_ceiling,
            high_budget_pressure=high_budget_pressure,
        )
        self.label_cost_ceiling = float(label_cost_ceiling)
        self.high_budget_pressure = float(high_budget_pressure)

    @classmethod
    def from_matrix_report(cls, path: str | Path, *, k: int = 3) -> "CLCLearnedPolicySelector":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        samples: list[CLCLearnedPolicySample] = []
        for row in data.get("scenarios", []):
            policy = str(row.get("oracle_policy") or "")
            features = row.get("features")
            if policy not in POLICY_ORDER or not isinstance(features, dict):
                continue
            try:
                weight = float(row.get("weight", 1.0) or 1.0)
            except (TypeError, ValueError):
                weight = 1.0
            samples.append(
                CLCLearnedPolicySample(
                    features=_normalize_features(features),
                    policy=policy,
                    weight=max(0.05, min(5.0, weight)),
                    source=str(row.get("id") or path),
                )
            )
        return cls(samples, k=k)

    @classmethod
    def from_outcome_log(cls, path: str | Path, *, k: int = 3) -> "CLCLearnedPolicySelector":
        samples: list[CLCLearnedPolicySample] = []
        log_path = Path(path)
        if not log_path.exists():
            return cls(samples, k=k)
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            policy = str(row.get("oracle_policy") or "")
            label = str(row.get("outcome_label") or "")
            if policy not in POLICY_ORDER:
                if label in {"helped", "oracle_match_passed"}:
                    policy = str(row.get("selected_policy") or "")
                else:
                    continue
            if policy not in POLICY_ORDER:
                continue
            weight = 1.0
            if label == "oracle_match_passed":
                weight = 1.5
            elif label == "helped":
                weight = 1.25
            elif label == "passed_non_oracle":
                weight = 0.75
            samples.append(
                CLCLearnedPolicySample(
                    features=_features_from_outcome_row(row),
                    policy=policy,
                    weight=weight,
                    source=str(row.get("scenario_id") or log_path),
                )
            )
        return cls(samples, k=k)

    def select(self, features: CLCPolicyFeatures | dict[str, Any]) -> CLCPolicyDecision:
        f = _normalize_features(features)
        if f.label_cost > self.label_cost_ceiling:
            return CLCPolicyDecision(
                policy=POLICY_PERIODIC,
                action=POLICY_ACTIONS[POLICY_PERIODIC],
                reason="learned_guard_label_cost_above_break_even",
                confidence=0.86,
            )
        if f.budget_pressure >= self.high_budget_pressure:
            return CLCPolicyDecision(
                policy=POLICY_PERIODIC,
                action=POLICY_ACTIONS[POLICY_PERIODIC],
                reason="learned_guard_budget_pressure_high",
                confidence=0.80,
            )
        if not self.samples:
            decision = self.fallback.select(f)
            return CLCPolicyDecision(
                policy=decision.policy,
                action=decision.action,
                reason=f"learned_fallback_no_samples:{decision.reason}",
                confidence=decision.confidence,
            )

        ranked = sorted(self.samples, key=lambda sample: _distance(f, sample.features))
        votes = {policy: 0.0 for policy in POLICY_ORDER}
        total_vote = 0.0
        for sample in ranked[: self.k]:
            vote = sample.weight / (_distance(f, sample.features) + 0.05)
            votes[sample.policy] += vote
            total_vote += vote
        if total_vote <= 0.0:
            decision = self.fallback.select(f)
            return CLCPolicyDecision(
                policy=decision.policy,
                action=decision.action,
                reason=f"learned_fallback_zero_vote:{decision.reason}",
                confidence=decision.confidence,
            )
        policy = max(POLICY_ORDER, key=lambda item: (votes[item], -POLICY_COST[item]))
        confidence = max(0.5, min(0.95, votes[policy] / total_vote))
        return CLCPolicyDecision(
            policy=policy,
            action=_policy_action(policy),
            reason=f"learned_knn_k{self.k}_samples{len(self.samples)}",
            confidence=round(confidence, 6),
        )

    def explain(self, features: CLCPolicyFeatures | dict[str, Any], *, top_k: int | None = None) -> dict[str, Any]:
        f = _normalize_features(features)
        nearest_count = max(self.k, int(top_k or self.k))
        if f.label_cost > self.label_cost_ceiling or f.budget_pressure >= self.high_budget_pressure or not self.samples:
            decision = self.select(f)
            explanation = {
                "selector_class": self.__class__.__name__,
                "features": asdict(f),
                "decision": _decision_dict(decision),
                "guardrails": {
                    "label_cost_ceiling": self.label_cost_ceiling,
                    "high_budget_pressure": self.high_budget_pressure,
                },
                "nearest_samples": [],
                "votes": {},
                "total_vote": 0.0,
                "sample_count": len(self.samples),
                "explanation": decision.reason,
            }
            if not self.samples:
                explanation["fallback"] = self.fallback.explain(f, top_k=nearest_count)
            return explanation

        ranked = sorted(
            (
                {
                    "source": sample.source,
                    "policy": sample.policy,
                    "weight": sample.weight,
                    "distance": _distance(f, sample.features),
                    "features": asdict(sample.features),
                }
                for sample in self.samples
            ),
            key=lambda row: row["distance"],
        )
        votes = {policy: 0.0 for policy in POLICY_ORDER}
        total_vote = 0.0
        nearest_samples = []
        for index, row in enumerate(ranked[:nearest_count]):
            vote = float(row["weight"]) / (float(row["distance"]) + 0.05)
            row["vote"] = round(vote, 6)
            row["vote_counted"] = index < self.k
            row["distance"] = round(float(row["distance"]), 6)
            nearest_samples.append(row)
        for row in nearest_samples:
            if not row["vote_counted"]:
                continue
            votes[str(row["policy"])] += float(row["vote"])
            total_vote += float(row["vote"])
        decision = self.select(f)
        return {
            "selector_class": self.__class__.__name__,
            "features": asdict(f),
            "decision": _decision_dict(decision),
            "guardrails": {
                "label_cost_ceiling": self.label_cost_ceiling,
                "high_budget_pressure": self.high_budget_pressure,
            },
            "nearest_samples": nearest_samples,
            "votes": {policy: round(vote, 6) for policy, vote in votes.items()},
            "total_vote": round(total_vote, 6),
            "sample_count": len(self.samples),
            "k": self.k,
            "explanation": f"nearest_neighbor_vote:k={self.k},top_k={nearest_count}",
        }
