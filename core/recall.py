from __future__ import annotations

from core.math_utils import cosine
from core.models import DomainState, RecallResult
from storage.db import MemoryDB
from storage.vector_index import BruteForceVectorIndex


class RecallEngine:
    def __init__(self, db: MemoryDB, top_k: int = 8):
        self.db = db
        self.index = BruteForceVectorIndex(db)
        self.top_k = top_k

    def recall(self, embedding: list[float]) -> RecallResult:
        items = self.index.search(embedding, self.top_k)
        domains = self.db.list_domains()
        nearest_domain: DomainState | None = None
        nearest_score = -1.0
        for domain in domains:
            if not domain.anchor_vector:
                continue
            score = cosine(embedding, domain.anchor_vector)
            if score > nearest_score:
                nearest_domain = domain
                nearest_score = score
        return RecallResult(
            items=items,
            best_score=items[0].score if items else 0.0,
            nearest_domain=nearest_domain,
            nearest_domain_score=max(0.0, nearest_score),
        )
