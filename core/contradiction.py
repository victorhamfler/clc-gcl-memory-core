from __future__ import annotations

from core.models import RecallResult
from storage.db import MemoryDB


def store_contradiction_if_needed(db: MemoryDB, new_memory_id: str, recall: RecallResult, score: float) -> None:
    if score <= 0.75 or not recall.items:
        return
    target = recall.items[0]
    db.add_contradiction(new_memory_id, target.memory_id, score)
