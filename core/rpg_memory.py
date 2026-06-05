"""Report-only RPG memory substrate diagnostics.

RPG here means Relational Projector Geometry. This module intentionally keeps
the first implementation small: it builds a mixed memory-memory relation
operator from embeddings and metadata, probes constrained projector sectors,
and reports island/activity diagnostics without mutating runtime memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RPGMemoryRecord:
    memory_id: str
    text: str
    domain: str = ""
    source: str = ""
    timestamp: str = ""
    authority: float = 0.5
    status: str = "active"
    retrieval_count: float = 0.0
    embedding: tuple[float, ...] = ()


def norm01(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    low = float(np.min(values))
    high = float(np.max(values))
    if high - low <= 1e-12:
        return np.zeros_like(values)
    return (values - low) / (high - low)


def cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    embeddings = np.asarray(embeddings, dtype=float)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    safe = embeddings / np.maximum(norms, 1e-12)
    return safe @ safe.T


def label_similarity(labels: list[str]) -> np.ndarray:
    n = len(labels)
    matrix = np.zeros((n, n), dtype=float)
    for i, label_i in enumerate(labels):
        for j, label_j in enumerate(labels):
            if label_i and label_i == label_j:
                matrix[i, j] = 1.0
    return matrix


def scalar_similarity(values: np.ndarray) -> np.ndarray:
    values = norm01(np.asarray(values, dtype=float))
    return 1.0 - np.abs(values[:, None] - values[None, :])


def text_token_jaccard_matrix(texts: list[str]) -> np.ndarray:
    token_sets = [
        {token.strip(".,:;!?()[]{}\"'").lower() for token in text.split() if token.strip()}
        for text in texts
    ]
    n = len(texts)
    matrix = np.eye(n, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            union = token_sets[i] | token_sets[j]
            score = len(token_sets[i] & token_sets[j]) / max(len(union), 1)
            matrix[i, j] = score
            matrix[j, i] = score
    return matrix


def build_relational_substrate(
    records: list[RPGMemoryRecord],
    *,
    embedding_weight: float = 0.70,
    domain_weight: float = 0.15,
    authority_weight: float = 0.10,
    retrieval_weight: float = 0.05,
) -> dict[str, Any]:
    """Build symmetric RPG substrate A from embeddings and metadata."""
    if not records:
        raise ValueError("records must not be empty")
    embeddings = np.asarray([record.embedding for record in records], dtype=float)
    if embeddings.ndim != 2 or embeddings.shape[0] != len(records) or embeddings.shape[1] == 0:
        raise ValueError("records must provide same-dimensional non-empty embeddings")

    embedding = np.clip(cosine_similarity_matrix(embeddings), -1.0, 1.0)
    embedding = (embedding + 1.0) / 2.0
    domain = label_similarity([record.domain for record in records])
    authority = scalar_similarity(np.asarray([record.authority for record in records], dtype=float))
    retrieval = scalar_similarity(np.asarray([record.retrieval_count for record in records], dtype=float))
    lexical = text_token_jaccard_matrix([record.text for record in records])

    raw = (
        embedding_weight * embedding
        + domain_weight * domain
        + authority_weight * authority
        + retrieval_weight * retrieval
    )
    # A tiny lexical tie-breaker helps exact duplicate islands in tiny fixtures
    # without turning the method into a term-based controller.
    raw = 0.97 * raw + 0.03 * lexical
    substrate = 0.5 * (raw + raw.T)
    substrate = substrate / max(float(np.linalg.norm(substrate, "fro")), 1e-12)
    return {
        "A": substrate,
        "components": {
            "embedding": embedding,
            "domain": domain,
            "authority": authority,
            "retrieval": retrieval,
            "lexical_tiebreaker": lexical,
        },
        "weights": {
            "embedding": embedding_weight,
            "domain": domain_weight,
            "authority": authority_weight,
            "retrieval": retrieval_weight,
            "lexical_tiebreaker": 0.03,
        },
    }


def diagonal_constraint(values: np.ndarray) -> np.ndarray:
    return np.diag(norm01(np.asarray(values, dtype=float)))


def build_constraints(records: list[RPGMemoryRecord]) -> dict[str, np.ndarray]:
    timestamps = [record.timestamp or "" for record in records]
    sorted_unique = {value: idx for idx, value in enumerate(sorted(set(timestamps)))}
    recency = np.asarray([sorted_unique.get(record.timestamp or "", 0) for record in records], dtype=float)
    active = np.asarray([0.0 if record.status.lower() in {"deprecated", "historical"} else 1.0 for record in records])
    deprecated = 1.0 - active
    authority = np.asarray([record.authority for record in records], dtype=float)
    retrieval = np.asarray([record.retrieval_count for record in records], dtype=float)
    duplicate = np.asarray([
        1.0 if "duplicate" in record.text.lower() or "same fact" in record.text.lower() else 0.0
        for record in records
    ])
    contradiction = np.asarray([
        1.0 if any(marker in record.text.lower() for marker in ("contradict", "stale", "old", "outdated"))
        else 0.0
        for record in records
    ])
    domains = sorted({record.domain for record in records if record.domain})
    constraints: dict[str, np.ndarray] = {
        "recency": diagonal_constraint(recency),
        "active": diagonal_constraint(active),
        "deprecated": diagonal_constraint(deprecated),
        "source_authority": diagonal_constraint(authority),
        "retrieval_frequency": diagonal_constraint(retrieval),
        "duplicate_score": diagonal_constraint(duplicate),
        "contradiction_score": diagonal_constraint(contradiction),
    }
    for domain in domains:
        constraints[f"domain:{domain}"] = diagonal_constraint(
            np.asarray([1.0 if record.domain == domain else 0.0 for record in records], dtype=float)
        )
    return constraints


def top_projector(operator: np.ndarray, rank_k: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values, vectors = np.linalg.eigh(np.asarray(operator, dtype=float))
    order = np.argsort(values)[::-1]
    selected = order[: min(int(rank_k), vectors.shape[1])]
    basis, _ = np.linalg.qr(vectors[:, selected])
    basis = basis[:, : len(selected)]
    projector = basis @ basis.T
    return projector, basis, values[order]


def constrained_projector(
    substrate: np.ndarray,
    constraint_a: np.ndarray,
    constraint_b: np.ndarray,
    *,
    a: float = 0.0,
    b: float = 0.0,
    alpha: float = 0.08,
    rank_k: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dim = substrate.shape[0]
    eta = np.eye(dim) + alpha * (a * constraint_a + b * constraint_b)
    operator = eta @ substrate @ eta
    operator = 0.5 * (operator + operator.T)
    return top_projector(operator, rank_k)


def island_ratio(substrate: np.ndarray, sector: list[int]) -> float:
    sector_set = set(int(idx) for idx in sector)
    outside = [idx for idx in range(substrate.shape[0]) if idx not in sector_set]
    if len(sector_set) < 2 or not outside:
        return 0.0
    G = np.abs(substrate)
    internal = [
        float(G[i, j])
        for i in sector_set
        for j in sector_set
        if i < j
    ]
    boundary = [float(G[i, j]) for i in sector_set for j in outside]
    return float(np.mean(internal) / max(float(np.mean(boundary)), 1e-12))


def probe_constraint_pair(
    records: list[RPGMemoryRecord],
    substrate: np.ndarray,
    constraint_a: np.ndarray,
    constraint_b: np.ndarray,
    *,
    pair_name: str,
    rank_k: int = 4,
    sector_size: int = 4,
    alpha: float = 0.08,
    delta: float = 0.05,
) -> dict[str, Any]:
    p0, _, eigenvalues = constrained_projector(
        substrate, constraint_a, constraint_b, alpha=alpha, rank_k=rank_k
    )
    p_ap, _, _ = constrained_projector(substrate, constraint_a, constraint_b, a=delta, alpha=alpha, rank_k=rank_k)
    p_am, _, _ = constrained_projector(substrate, constraint_a, constraint_b, a=-delta, alpha=alpha, rank_k=rank_k)
    p_bp, _, _ = constrained_projector(substrate, constraint_a, constraint_b, b=delta, alpha=alpha, rank_k=rank_k)
    p_bm, _, _ = constrained_projector(substrate, constraint_a, constraint_b, b=-delta, alpha=alpha, rank_k=rank_k)
    partial_a = (p_ap - p_am) / (2.0 * delta)
    partial_b = (p_bp - p_bm) / (2.0 * delta)
    omega = p0 @ (partial_a @ partial_b - partial_b @ partial_a) @ p0
    activity = np.sqrt(np.sum(omega**2, axis=1))
    score = 0.65 * norm01(np.diag(p0)) + 0.35 * norm01(activity)
    sector = [int(idx) for idx in np.argsort(score)[::-1][: min(sector_size, len(records))]]
    rank = min(int(rank_k), len(eigenvalues))
    spectral_gap = 0.0
    if len(eigenvalues) > rank:
        spectral_gap = float(eigenvalues[rank - 1] - eigenvalues[rank])
    return {
        "schema": "rpg_constraint_pair_probe/v1",
        "pair_name": pair_name,
        "rank_k": int(rank_k),
        "sector_size": int(len(sector)),
        "sector_memory_ids": [records[idx].memory_id for idx in sector],
        "sector_domains": sorted({records[idx].domain for idx in sector}),
        "sector_statuses": sorted({records[idx].status for idx in sector}),
        "omega_norm": round(float(np.linalg.norm(omega, "fro")), 12),
        "activity_max": round(float(np.max(activity)), 12),
        "island_ratio": round(island_ratio(substrate, sector), 6),
        "spectral_gap": round(spectral_gap, 12),
        "idempotence_error": round(float(np.linalg.norm(p0 @ p0 - p0, "fro")), 12),
        "symmetry_error": round(float(np.linalg.norm(p0.T - p0, "fro")), 12),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_db": False,
        "mutates_config": False,
    }


def run_rpg_memory_probe(records: list[RPGMemoryRecord], *, rank_k: int = 4) -> dict[str, Any]:
    substrate_info = build_relational_substrate(records)
    substrate = substrate_info["A"]
    constraints = build_constraints(records)
    pairs: list[tuple[str, str, str]] = [
        ("active_vs_deprecated", "active", "deprecated"),
        ("source_authority_vs_retrieval", "source_authority", "retrieval_frequency"),
        ("duplicate_vs_contradiction", "duplicate_score", "contradiction_score"),
    ]
    for key in sorted(constraints):
        if key.startswith("domain:"):
            pairs.append((f"{key}_vs_recency", key, "recency"))
            break
    pair_reports = [
        probe_constraint_pair(
            records,
            substrate,
            constraints[left],
            constraints[right],
            pair_name=name,
            rank_k=rank_k,
        )
        for name, left, right in pairs
        if left in constraints and right in constraints
    ]
    return {
        "schema": "rpg_memory_relational_substrate_probe/v1",
        "memory_count": len(records),
        "rank_k": int(rank_k),
        "substrate_fro_norm": round(float(np.linalg.norm(substrate, "fro")), 12),
        "substrate_symmetry_error": round(float(np.linalg.norm(substrate.T - substrate, "fro")), 12),
        "substrate_weights": substrate_info["weights"],
        "constraint_pair_reports": pair_reports,
        "max_island_ratio": round(max((float(item["island_ratio"]) for item in pair_reports), default=0.0), 6),
        "max_omega_norm": round(max((float(item["omega_norm"]) for item in pair_reports), default=0.0), 12),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_db": False,
        "mutates_config": False,
    }
