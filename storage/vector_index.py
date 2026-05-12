from __future__ import annotations

from core.math_utils import cosine
from core.models import RecallItem
from storage.db import MemoryDB


class BruteForceVectorIndex:
    def __init__(self, db: MemoryDB):
        self.db = db

    def search(self, embedding: list[float], top_k: int = 8, namespaces: list[str] | None = None) -> list[RecallItem]:
        rows = self.db.list_memory_vectors(include_deprecated=False, namespaces=namespaces)
        scored: list[RecallItem] = []
        for row in rows:
            score = cosine(embedding, row["embedding"])
            scored.append(
                RecallItem(
                    memory_id=row["id"],
                    domain_id=row["domain_id"],
                    text=row["text"],
                    memory_type=row["memory_type"],
                    score=score,
                    importance=row["importance"],
                    stability=row["stability"],
                    csd_score=row.get("csd_score", 0.0),
                    clc_state=row.get("clc_state"),
                    namespace=row["namespace"],
                    deprecated=row["deprecated"],
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, int(top_k))]
