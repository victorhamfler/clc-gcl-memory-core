"""OGCF-inspired memory geometry for bridge-overload and composition-instability detection.

This module is intentionally dependency-free beyond NumPy so it can be called from
the selector runtime without dragging in heavy ML frameworks.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


try:
    from sklearn.cluster import KMeans
    from sklearn.neighbors import NearestNeighbors
except Exception:  # pragma: no cover
    KMeans = None  # type: ignore[misc,assignment]
    NearestNeighbors = None  # type: ignore[misc,assignment]


@dataclass
class OGCFLoop:
    cluster_a: int
    cluster_b: int
    cluster_c: int
    holonomy_raw: float
    holonomy_rank_norm: float
    interaction_excess: float
    interaction_z: float
    local_defect_a: float
    local_defect_b: float
    local_defect_c: float
    local_defect_z_mean: float
    cluster_size_a: int
    cluster_size_b: int
    cluster_size_c: int


@dataclass(frozen=True)
class OGCFCluster:
    cluster_id: int
    size: int
    local_defect: float
    top_domain: str = ""


@dataclass
class OGCFGeometryResult:
    n_clusters: int
    rank_k: int
    neighbors: int
    labels: np.ndarray = field(repr=False)
    cluster_sizes: list[int]
    loops: list[OGCFLoop]
    clusters: list[OGCFCluster]
    local_defects: list[float]
    baseline_mean: float
    baseline_std: float
    embedding_norm_stats: dict[str, float]


class OGCFGeometryEngine:
    """Compute OGCF-inspired memory cluster geometry.

    The engine clusters memory embeddings, builds local SVD bases per cluster,
    discovers adjacency loops, and computes interaction excess / z-scores.
    """

    def __init__(
        self,
        n_clusters: int = 60,
        rank_k: int = 8,
        neighbors: int = 5,
        random_baselines: int = 20,
        seed: int = 42,
    ):
        self.n_clusters = int(n_clusters)
        self.rank_k = int(rank_k)
        self.neighbors = int(neighbors)
        self.random_baselines = int(random_baselines)
        self.seed = int(seed)

    def analyze(
        self,
        embeddings: np.ndarray,
        memory_ids: list[str] | None = None,
        db_path: str | Path | None = None,
    ) -> OGCFGeometryResult:
        """Run full OGCF geometry analysis on memory embeddings."""
        if KMeans is None:
            raise RuntimeError("scikit-learn is required for OGCF geometry")

        N, dim = embeddings.shape
        norms = np.linalg.norm(embeddings, axis=1)
        norm_stats = {
            "min": float(norms.min()),
            "mean": float(norms.mean()),
            "max": float(norms.max()),
            "std": float(norms.std()),
        }

        # KMeans clustering
        kmeans = KMeans(n_clusters=self.n_clusters, random_state=self.seed, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        cluster_sizes = [int(x) for x in np.bincount(labels, minlength=self.n_clusters)]

        # Local SVD bases
        bases: dict[int, np.ndarray] = {}
        local_defects: dict[int, float] = {}
        for c in range(self.n_clusters):
            mask = labels == c
            cluster_embs = embeddings[mask]
            U_k, defect = self._compute_local_geometry(cluster_embs, dim, self.rank_k)
            bases[c] = U_k
            local_defects[c] = defect

        # Adjacency graph from nearest neighbors
        nn = NearestNeighbors(n_neighbors=min(self.neighbors + 1, N), metric="cosine")
        nn.fit(embeddings)
        _, indices = nn.kneighbors(embeddings)

        adjacency = np.zeros((self.n_clusters, self.n_clusters))
        for i in range(N):
            c_i = labels[i]
            for j_idx in indices[i][1:]:
                c_j = labels[j_idx]
                if c_i != c_j:
                    adjacency[c_i, c_j] += 1
                    adjacency[c_j, c_i] += 1

        # Find loops (triangles)
        loops: list[tuple[int, int, int]] = []
        for a in range(self.n_clusters):
            for b in range(a + 1, self.n_clusters):
                if adjacency[a, b] == 0:
                    continue
                for c_idx in range(b + 1, self.n_clusters):
                    if adjacency[a, c_idx] > 0 and adjacency[b, c_idx] > 0:
                        loops.append((a, b, c_idx))

        # Compute loop metrics
        loop_results: list[OGCFLoop] = []
        for a, b, c in loops:
            U_a, U_b, U_c = bases[a], bases[b], bases[c]
            U_ab = self._transition_projector(U_a, U_b)
            U_bc = self._transition_projector(U_b, U_c)
            U_ac = self._transition_projector(U_a, U_c)
            U_ca = self._transition_projector(U_c, U_a)
            U_loop = U_ca @ U_bc @ U_ab
            holonomy_raw = float(np.linalg.norm(U_loop - np.eye(U_loop.shape[0]), "fro"))
            holonomy_rank_norm = holonomy_raw / np.sqrt(min(self.rank_k, U_loop.shape[0]))
            interaction_excess = float(self._interaction_excess(U_ac, U_bc, U_ab))
            loop_results.append(
                OGCFLoop(
                    cluster_a=a,
                    cluster_b=b,
                    cluster_c=c,
                    holonomy_raw=holonomy_raw,
                    holonomy_rank_norm=float(holonomy_rank_norm),
                    interaction_excess=interaction_excess,
                    interaction_z=0.0,  # filled later
                    local_defect_a=float(local_defects[a]),
                    local_defect_b=float(local_defects[b]),
                    local_defect_c=float(local_defects[c]),
                    local_defect_z_mean=0.0,  # filled later
                    cluster_size_a=cluster_sizes[a],
                    cluster_size_b=cluster_sizes[b],
                    cluster_size_c=cluster_sizes[c],
                )
            )

        # Random baselines for z-scores
        baseline_ie = self._compute_baselines(embeddings, labels, loops)
        baseline_mean = float(np.mean(baseline_ie)) if baseline_ie else 0.0
        baseline_std = float(np.std(baseline_ie)) if baseline_ie else 1.0

        # Defect stats
        all_defects = [local_defects[c] for c in range(self.n_clusters)]
        defect_mean = float(np.mean(all_defects))
        defect_std = float(np.std(all_defects))

        for lr in loop_results:
            lr.interaction_z = (lr.interaction_excess - baseline_mean) / max(baseline_std, 1e-10)
            lr.local_defect_z_mean = np.mean([
                (lr.local_defect_a - defect_mean) / max(defect_std, 1e-10),
                (lr.local_defect_b - defect_mean) / max(defect_std, 1e-10),
                (lr.local_defect_c - defect_mean) / max(defect_std, 1e-10),
            ])

        # Build cluster summaries with top domains
        clusters = []
        for c in range(self.n_clusters):
            top_domain = ""
            if db_path is not None and memory_ids is not None:
                top_domain = self._top_domain_for_cluster(c, labels, memory_ids, db_path)
            clusters.append(
                OGCFCluster(
                    cluster_id=c,
                    size=cluster_sizes[c],
                    local_defect=local_defects[c],
                    top_domain=top_domain,
                )
            )

        return OGCFGeometryResult(
            n_clusters=self.n_clusters,
            rank_k=self.rank_k,
            neighbors=self.neighbors,
            labels=labels,
            cluster_sizes=cluster_sizes,
            loops=loop_results,
            clusters=clusters,
            local_defects=[local_defects[c] for c in range(self.n_clusters)],
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            embedding_norm_stats=norm_stats,
        )

    def _compute_local_geometry(
        self, cluster_embeddings: np.ndarray, dim: int, rank_k: int
    ) -> tuple[np.ndarray, float]:
        n_points = len(cluster_embeddings)
        if n_points < 2:
            U_k = np.eye(dim)[:, : min(rank_k, dim)]
            return U_k, 1.0
        centered = cluster_embeddings - cluster_embeddings.mean(axis=0)
        U, S, Vt = np.linalg.svd(centered, full_matrices=False)
        actual_rank = min(rank_k, Vt.shape[0], n_points - 1)
        U_k = Vt.T[:, :actual_rank]
        if actual_rank < rank_k:
            padding = np.eye(dim)[:, actual_rank:rank_k]
            U_k = np.concatenate([U_k, padding], axis=1)
        if len(S) > 0:
            total_var = float(np.sum(S**2))
            explained_var = float(np.sum(S[: min(rank_k, len(S))] ** 2))
            local_defect = 1.0 - (explained_var / max(total_var, 1e-10))
        else:
            local_defect = 1.0
        return U_k, local_defect

    def _transition_projector(self, U_a: np.ndarray, U_b: np.ndarray) -> np.ndarray:
        M = U_a.T @ U_b
        U_m, _, Vt_m = np.linalg.svd(M, full_matrices=False)
        return U_m @ Vt_m

    def _interaction_excess(self, U_ac: np.ndarray, U_bc: np.ndarray, U_ab: np.ndarray) -> float:
        return float(np.linalg.norm(U_ac - U_bc @ U_ab, "fro"))

    def _compute_baselines(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        loops: list[tuple[int, int, int]],
    ) -> list[float]:
        baseline_ie: list[float] = []
        rng = np.random.default_rng(self.seed)
        for r in range(self.random_baselines):
            shuffled = rng.permutation(labels)
            shuffled_bases: dict[int, np.ndarray] = {}
            for c in range(self.n_clusters):
                mask = shuffled == c
                if mask.sum() < 2:
                    continue
                U_k, _ = self._compute_local_geometry(
                    embeddings[mask], embeddings.shape[1], self.rank_k
                )
                shuffled_bases[c] = U_k
            for a, b, c in loops[: min(len(loops), 500)]:
                if a not in shuffled_bases or b not in shuffled_bases or c not in shuffled_bases:
                    continue
                U_ab = self._transition_projector(shuffled_bases[a], shuffled_bases[b])
                U_bc = self._transition_projector(shuffled_bases[b], shuffled_bases[c])
                U_ac = self._transition_projector(shuffled_bases[a], shuffled_bases[c])
                ie = self._interaction_excess(U_ac, U_bc, U_ab)
                baseline_ie.append(ie)
        return baseline_ie

    def _top_domain_for_cluster(
        self, cluster_id: int, labels: np.ndarray, memory_ids: list[str], db_path: str | Path
    ) -> str:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        domain_counts: dict[str, int] = {}
        for i, mid in enumerate(memory_ids):
            if labels[i] == cluster_id:
                row = conn.execute(
                    "SELECT domain_id FROM memories WHERE id=?", (mid,)
                ).fetchone()
                if row:
                    dom = str(row[0] or "unknown")
                    domain_counts[dom] = domain_counts.get(dom, 0) + 1
        conn.close()
        if domain_counts:
            return max(domain_counts, key=domain_counts.get)  # type: ignore[arg-type]
        return ""


class OGCFMemoryReviewer:
    """High-level reviewer that runs OGCF geometry and produces actionable recommendations."""

    def __init__(self, engine: OGCFGeometryEngine | None = None):
        self.engine = engine or OGCFGeometryEngine()

    def review(
        self,
        embeddings: np.ndarray,
        memory_ids: list[str],
        db_path: str | Path,
    ) -> dict[str, Any]:
        """Run OGCF geometry and produce a review report."""
        geo = self.engine.analyze(embeddings, memory_ids, db_path)

        # Risk regions from loops
        risk_regions: list[dict[str, Any]] = []
        for loop in geo.loops:
            action = self._loop_action(loop)
            risk_regions.append(
                {
                    "clusters": f"{loop.cluster_a}-{loop.cluster_b}-{loop.cluster_c}",
                    "interaction_z": round(loop.interaction_z, 4),
                    "interaction_excess": round(loop.interaction_excess, 6),
                    "local_defect_z_mean": round(loop.local_defect_z_mean, 4),
                    "failure_mode": self._failure_mode(loop),
                    "recommended_action": action,
                    "cluster_sizes": f"{loop.cluster_size_a}-{loop.cluster_size_b}-{loop.cluster_size_c}",
                }
            )

        # Bridge clusters (high domain diversity within one cluster)
        bridge_clusters = self._detect_bridge_clusters(geo, memory_ids, db_path)

        # Overall signals
        max_interaction_z = max((lr.interaction_z for lr in geo.loops), default=0.0)
        bridge_overload_score = max(0.0, min(1.0, max_interaction_z / 3.0))

        return {
            "config": {
                "n_clusters": geo.n_clusters,
                "rank_k": geo.rank_k,
                "neighbors": geo.neighbors,
            },
            "embedding_norm_stats": geo.embedding_norm_stats,
            "loop_count": len(geo.loops),
            "max_interaction_z": round(max_interaction_z, 4),
            "bridge_overload_score": round(bridge_overload_score, 4),
            "risk_regions": sorted(risk_regions, key=lambda x: x["interaction_z"], reverse=True),
            "bridge_clusters": bridge_clusters,
            "cluster_summary": [
                {
                    "cluster_id": c.cluster_id,
                    "size": c.size,
                    "local_defect": round(c.local_defect, 4),
                    "top_domain": c.top_domain,
                }
                for c in geo.clusters
            ],
        }

    def _failure_mode(self, loop: OGCFLoop) -> str:
        if loop.interaction_z >= 2.0:
            return "bridge_overload"
        if loop.local_defect_z_mean >= 2.0:
            return "poor_cluster_alignment"
        return "clean"

    def _loop_action(self, loop: OGCFLoop) -> str:
        if loop.interaction_z >= 3.0:
            return "split_cluster"
        if loop.interaction_z >= 2.0:
            return "review"
        if loop.local_defect_z_mean >= 2.0:
            return "review"
        return "allow"

    def _detect_bridge_clusters(
        self, geo: OGCFGeometryResult, memory_ids: list[str], db_path: str | Path
    ) -> list[dict[str, Any]]:
        """Detect clusters with high domain diversity (bridge clusters)."""
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        bridge_clusters: list[dict[str, Any]] = []
        for c in range(geo.n_clusters):
            domain_counts: dict[str, int] = {}
            for i, mid in enumerate(memory_ids):
                if geo.labels[i] == c:
                    row = conn.execute(
                        "SELECT domain_id FROM memories WHERE id=?", (mid,)
                    ).fetchone()
                    if row:
                        dom = str(row[0] or "unknown")
                        domain_counts[dom] = domain_counts.get(dom, 0) + 1
            unique_domains = len(domain_counts)
            if unique_domains >= 5 or (unique_domains >= 3 and geo.cluster_sizes[c] >= 10):
                bridge_clusters.append(
                    {
                        "cluster_id": c,
                        "size": geo.cluster_sizes[c],
                        "unique_domains": unique_domains,
                        "domain_counts": domain_counts,
                        "local_defect": round(geo.local_defects[c], 4),
                    }
                )
        conn.close()
        return sorted(bridge_clusters, key=lambda x: x["unique_domains"], reverse=True)
