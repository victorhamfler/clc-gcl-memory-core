"""OGCF API integration for the memory program HTTP server.

This module provides handlers that can be wired into serve.py to expose
OGCF geometry review endpoints. It is stateless and uses the existing
MemoryDB and pipeline encoder.

Integration into serve.py:

    from core.ogcf_api import OGCFReviewAPI
    ogcf_api = OGCFReviewAPI(api.pipeline.db, api.pipeline.encoder)

    # In Handler.do_POST:
    elif path == "/ogcf_review":
        self._send_json(200, ogcf_api.review(payload))
    elif path == "/ogcf_cluster_detail":
        self._send_json(200, ogcf_api.cluster_detail(payload))
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer


class OGCFReviewAPI:
    """OGCF review endpoint logic."""

    def __init__(self, db, encoder, default_n_clusters: int = 60, default_rank_k: int = 8):
        self.db = db
        self.encoder = encoder
        self.default_n_clusters = default_n_clusters
        self.default_rank_k = default_rank_k

    def _fetch_embeddings(self, limit: int | None = None) -> tuple[list[str], np.ndarray]:
        """Load memory IDs and embeddings from the DB."""
        if limit:
            rows = self.db.conn.execute(
                """
                SELECT m.id, v.embedding
                FROM memories m
                JOIN vectors v ON v.memory_id = m.id
                WHERE m.deprecated = 0
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                """
                SELECT m.id, v.embedding
                FROM memories m
                JOIN vectors v ON v.memory_id = m.id
                WHERE m.deprecated = 0
                """
            ).fetchall()

        memory_ids = []
        embeddings = []
        for row in rows:
            vec = json.loads(row["embedding"].decode("utf-8"))
            embeddings.append(vec)
            memory_ids.append(row["id"])

        if not embeddings:
            return [], np.array([])
        return memory_ids, np.array(embeddings, dtype=np.float32)

    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /ogcf_review

        Payload:
            {
                "sample_size": 2000,      // optional, default=all
                "n_clusters": 60,         // optional
                "rank_k": 8,            // optional
                "neighbors": 5,           // optional
            }
        """
        sample_size = payload.get("sample_size")
        n_clusters = int(payload.get("n_clusters", self.default_n_clusters))
        rank_k = int(payload.get("rank_k", self.default_rank_k))
        neighbors = int(payload.get("neighbors", 5))

        memory_ids, embeddings = self._fetch_embeddings(
            limit=sample_size if sample_size else None
        )
        if len(memory_ids) < n_clusters:
            return {
                "ok": False,
                "error": f"Not enough memories ({len(memory_ids)}) for {n_clusters} clusters",
            }

        db_path = str(getattr(self.db, "db_path", "")) if getattr(self.db, "db_path", None) else None
        engine = OGCFGeometryEngine(
            n_clusters=n_clusters, rank_k=rank_k, neighbors=neighbors
        )
        reviewer = OGCFMemoryReviewer(engine)
        report = reviewer.review(embeddings, memory_ids, db_path)
        report["ok"] = True
        report["sample_size"] = len(memory_ids)
        return report

    def cluster_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /ogcf_cluster_detail

        Payload:
            {
                "cluster_id": 15,
                "sample_size": 2000,   // optional
            }
        """
        target_cluster = int(payload.get("cluster_id", -1))
        sample_size = payload.get("sample_size")
        if target_cluster < 0:
            return {"ok": False, "error": "cluster_id is required"}

        memory_ids, embeddings = self._fetch_embeddings(
            limit=sample_size if sample_size else None
        )
        if len(memory_ids) < 10:
            return {"ok": False, "error": "Not enough memories"}

        # Re-run clustering
        from sklearn.cluster import KMeans
        n_clusters = int(payload.get("n_clusters", self.default_n_clusters))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)

        cluster_memories = [
            {"memory_id": memory_ids[i], "text": self._get_text(memory_ids[i])}
            for i in range(len(memory_ids))
            if labels[i] == target_cluster
        ]

        return {
            "ok": True,
            "cluster_id": target_cluster,
            "memory_count": len(cluster_memories),
            "memories": cluster_memories,
        }

    def _get_text(self, memory_id: str) -> str:
        row = self.db.conn.execute(
            "SELECT text FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        return str(row["text"] or "") if row else ""
