from __future__ import annotations

import math

from core.math_utils import EPS, clamp, cosine, dot, effective_dimension_from_vectors, normalize, norm, weighted_average
from core.models import CLCDecision, DomainState, GCLUpdateResult, SignalPacket
from storage.db import MemoryDB, new_id, normalize_namespace


class GCLMemoryUpdater:
    def __init__(self, db: MemoryDB, base_update_rate: float = 0.18, beta: float = 0.95):
        self.db = db
        self.base_update_rate = float(base_update_rate)
        self.beta = float(beta)

    def apply(
        self,
        signal: SignalPacket,
        decision: CLCDecision,
        preferred_domain: DomainState | None,
        namespace: str = "global",
    ) -> GCLUpdateResult:
        memory_namespace = normalize_namespace(namespace)
        if decision.state == "PROTECT" and preferred_domain is None:
            domain = self._create_domain(signal, memory_namespace)
            return GCLUpdateResult(
                action="no_anchor_update",
                domain_id=domain.id,
                angular_drift=0.0,
                radial_drift=0.0,
                orthogonal_drift=0.0,
                combined_drift=0.0,
                curvature=0.0,
                anchor_update_strength=0.0,
            )
        if decision.state == "SPLIT_DOMAIN" or preferred_domain is None:
            domain = self._create_domain(signal, memory_namespace)
            return GCLUpdateResult(
                action="create_domain",
                domain_id=domain.id,
                angular_drift=0.0,
                radial_drift=0.0,
                orthogonal_drift=0.0,
                combined_drift=0.0,
                curvature=0.0,
                anchor_update_strength=0.0,
            )

        domain = preferred_domain
        angular, radial, orthogonal, update_direction = self._directional_drift(domain.anchor_vector, signal.embedding)
        combined = 0.50 * angular + 0.05 * radial + 0.35 * orthogonal
        curvature = 0.0
        if domain.previous_update_direction:
            curvature = 1.0 - cosine(update_direction, domain.previous_update_direction)
            curvature = clamp(curvature)

        update_rate = self.base_update_rate * decision.update_strength * (1.0 - clamp(domain.stability))
        if decision.state == "PROTECT":
            update_rate = 0.0
        if update_rate > 0.0:
            domain.anchor_vector = normalize(weighted_average(domain.anchor_vector, signal.embedding, update_rate))

        domain.drift_ema = self.beta * domain.drift_ema + (1.0 - self.beta) * combined
        delta = combined - domain.drift_ema
        domain.drift_var = self.beta * domain.drift_var + (1.0 - self.beta) * (delta * delta)
        domain.curvature_ema = self.beta * domain.curvature_ema + (1.0 - self.beta) * curvature
        domain.previous_update_direction = update_direction
        domain.memory_count += 1
        domain.stability = clamp(domain.stability + 0.015 if decision.state in ("RECALL", "CONSOLIDATE") else domain.stability)
        vectors = self.db.list_domain_vectors(domain.id, limit=128)
        if vectors:
            domain.effective_dimension = effective_dimension_from_vectors(vectors + [signal.embedding])
        self.db.upsert_domain(domain)
        return GCLUpdateResult(
            action="anchor_update" if update_rate > 0 else "no_anchor_update",
            domain_id=domain.id,
            angular_drift=angular,
            radial_drift=radial,
            orthogonal_drift=orthogonal,
            combined_drift=combined,
            curvature=curvature,
            anchor_update_strength=update_rate,
        )

    def _create_domain(self, signal: SignalPacket, namespace: str = "global") -> DomainState:
        memory_namespace = normalize_namespace(namespace)
        name = signal.domains[0] if signal.domains else "general"
        existing = self.db.get_domain_by_name(name, namespace=memory_namespace)
        if existing is not None and existing.anchor_vector:
            existing.memory_count += 1
            self.db.upsert_domain(existing)
            return existing
        domain = DomainState(
            id=new_id("dom"),
            name=name,
            namespace=memory_namespace,
            anchor_vector=normalize(signal.embedding),
            effective_dimension=1.0,
            stability=0.0,
            memory_count=1,
        )
        self.db.upsert_domain(domain)
        return domain

    def _directional_drift(self, anchor: list[float], vec: list[float]) -> tuple[float, float, float, list[float]]:
        u = normalize(anchor)
        v = normalize(vec)
        angular = clamp(1.0 - dot(u, v), 0.0, 2.0)
        radial = abs(norm(vec) - norm(anchor))
        projection_scale = dot(vec, u)
        parallel = [projection_scale * x for x in u]
        orth_vec = [x - y for x, y in zip(vec, parallel)]
        orthogonal = norm(orth_vec) / (norm(vec) + EPS)
        update_direction = normalize([x - y for x, y in zip(vec, anchor)])
        if not any(abs(x) > EPS for x in update_direction):
            update_direction = v
        return angular, radial, clamp(orthogonal), update_direction
