from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import DomainState, MemoryNode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def encode_vector(vec: list[float] | None) -> bytes | None:
    if vec is None:
        return None
    return json.dumps([float(x) for x in vec], separators=(",", ":")).encode("utf-8")


def decode_vector(blob: bytes | str | None) -> list[float]:
    if blob is None:
        return []
    if isinstance(blob, bytes):
        raw = blob.decode("utf-8")
    else:
        raw = blob
    return [float(x) for x in json.loads(raw)]


class MemoryDB:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self, schema_path: str | os.PathLike[str]) -> None:
        sql = Path(schema_path).read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def upsert_domain(self, domain: DomainState) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO domains (
                id, name, anchor_vector, effective_dimension, drift_ema,
                drift_var, curvature_ema, stability, memory_count,
                previous_update_direction, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                anchor_vector=excluded.anchor_vector,
                effective_dimension=excluded.effective_dimension,
                drift_ema=excluded.drift_ema,
                drift_var=excluded.drift_var,
                curvature_ema=excluded.curvature_ema,
                stability=excluded.stability,
                memory_count=excluded.memory_count,
                previous_update_direction=excluded.previous_update_direction,
                updated_at=excluded.updated_at
            """,
            (
                domain.id,
                domain.name,
                encode_vector(domain.anchor_vector),
                domain.effective_dimension,
                domain.drift_ema,
                domain.drift_var,
                domain.curvature_ema,
                domain.stability,
                domain.memory_count,
                encode_vector(domain.previous_update_direction),
                now,
                now,
            ),
        )
        self.conn.commit()

    def get_domain(self, domain_id: str) -> DomainState | None:
        row = self.conn.execute("SELECT * FROM domains WHERE id=?", (domain_id,)).fetchone()
        return self._domain_from_row(row) if row else None

    def get_domain_by_name(self, name: str) -> DomainState | None:
        row = self.conn.execute("SELECT * FROM domains WHERE name=?", (name,)).fetchone()
        return self._domain_from_row(row) if row else None

    def memory_exists_text(self, text: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM memories WHERE text=? AND deprecated=0 LIMIT 1",
            (str(text or "").strip(),),
        ).fetchone()
        return row is not None

    def set_memory_source(
        self,
        memory_id: str,
        source: str | None,
        chunk_index: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_sources (memory_id, source, chunk_index, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                source=excluded.source,
                chunk_index=excluded.chunk_index,
                metadata=excluded.metadata
            """,
            (
                memory_id,
                source,
                int(chunk_index),
                json.dumps(metadata or {}, separators=(",", ":")),
                utc_now(),
            ),
        )
        self.conn.commit()

    def get_memory_source(self, memory_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM memory_sources WHERE memory_id=?", (memory_id,)).fetchone()
        if row is None:
            return None
        return {
            "source": row["source"],
            "chunk_index": int(row["chunk_index"] or 0),
            "metadata": json.loads(row["metadata"] or "{}"),
        }

    def source_counts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT source, COUNT(*) AS count, MIN(chunk_index) AS first_chunk, MAX(chunk_index) AS last_chunk
            FROM memory_sources
            GROUP BY source
            ORDER BY count DESC, source
            """
        ).fetchall()
        return [
            {
                "source": row["source"],
                "count": int(row["count"] or 0),
                "first_chunk": int(row["first_chunk"] or 0),
                "last_chunk": int(row["last_chunk"] or 0),
            }
            for row in rows
        ]

    def add_retrieval_feedback(
        self,
        memory_id: str,
        label: str,
        query: str | None = None,
        rating: float | None = None,
        rank: int | None = None,
        retrieval_score: float | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.memory_exists_id(memory_id):
            raise ValueError(f"unknown memory_id: {memory_id}")
        normalized_label = str(label or "").strip().lower()
        if not normalized_label:
            raise ValueError("feedback label is required")
        feedback_id = new_id("fb")
        created_at = utc_now()
        self.conn.execute(
            """
            INSERT INTO retrieval_feedback (
                id, query, memory_id, label, rating, rank,
                retrieval_score, notes, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                query,
                memory_id,
                normalized_label,
                None if rating is None else float(rating),
                None if rank is None else int(rank),
                None if retrieval_score is None else float(retrieval_score),
                notes,
                json.dumps(metadata or {}, separators=(",", ":")),
                created_at,
            ),
        )
        self.add_event(
            memory_id,
            "retrieval_feedback",
            rating,
            {
                "feedback_id": feedback_id,
                "label": normalized_label,
                "query": query,
                "rank": rank,
                "retrieval_score": retrieval_score,
            },
        )
        return {
            "id": feedback_id,
            "memory_id": memory_id,
            "label": normalized_label,
            "rating": rating,
            "created_at": created_at,
        }

    def memory_exists_id(self, memory_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM memories WHERE id=? AND deprecated=0 LIMIT 1",
            (memory_id,),
        ).fetchone()
        return row is not None

    def feedback_counts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT label, COUNT(*) AS count, AVG(rating) AS avg_rating
            FROM retrieval_feedback
            GROUP BY label
            ORDER BY count DESC, label
            """
        ).fetchall()
        return [
            {
                "label": row["label"],
                "count": int(row["count"] or 0),
                "avg_rating": None if row["avg_rating"] is None else round(float(row["avg_rating"]), 4),
            }
            for row in rows
        ]

    def recent_feedback(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, query, memory_id, label, rating, rank, retrieval_score, notes, metadata, created_at
            FROM retrieval_feedback
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "query": row["query"],
                "memory_id": row["memory_id"],
                "label": row["label"],
                "rating": None if row["rating"] is None else float(row["rating"]),
                "rank": None if row["rank"] is None else int(row["rank"]),
                "retrieval_score": None if row["retrieval_score"] is None else float(row["retrieval_score"]),
                "notes": row["notes"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_domains(self) -> list[DomainState]:
        rows = self.conn.execute("SELECT * FROM domains ORDER BY memory_count DESC, updated_at DESC").fetchall()
        return [self._domain_from_row(row) for row in rows]

    def insert_memory(self, memory: MemoryNode) -> None:
        self.conn.execute(
            """
            INSERT INTO memories (
                id, text, summary, domain_id, memory_type, importance,
                stability, confidence, csd_score, surprise, recall_score,
                curiosity, focus, clc_state, created_at, updated_at,
                deprecated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.text,
                None,
                memory.domain_id,
                memory.memory_type,
                memory.importance,
                memory.stability,
                memory.confidence,
                memory.csd_score,
                memory.surprise,
                memory.recall_score,
                memory.curiosity,
                memory.focus,
                memory.clc_state,
                memory.created_at,
                memory.updated_at,
                memory.deprecated,
            ),
        )
        self.conn.execute(
            "INSERT INTO vectors (memory_id, embedding, dim) VALUES (?, ?, ?)",
            (memory.id, encode_vector(memory.embedding), len(memory.embedding)),
        )
        self.conn.commit()

    def list_memory_vectors(self, include_deprecated: bool = False) -> list[dict[str, Any]]:
        where = "" if include_deprecated else "WHERE m.deprecated=0"
        rows = self.conn.execute(
            f"""
            SELECT m.id, m.text, m.domain_id, m.memory_type, m.importance,
                   m.stability, m.deprecated, v.embedding
            FROM memories m
            JOIN vectors v ON v.memory_id = m.id
            {where}
            """
        ).fetchall()
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "domain_id": row["domain_id"],
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "deprecated": bool(row["deprecated"]),
                "embedding": decode_vector(row["embedding"]),
            }
            for row in rows
        ]

    def list_domain_vectors(self, domain_id: str, limit: int = 256) -> list[list[float]]:
        rows = self.conn.execute(
            """
            SELECT v.embedding
            FROM vectors v
            JOIN memories m ON m.id = v.memory_id
            WHERE m.domain_id=? AND m.deprecated=0
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (domain_id, int(limit)),
        ).fetchall()
        return [decode_vector(row["embedding"]) for row in rows]

    def add_relation(self, source: str, target: str, relation_type: str, weight: float = 1.0) -> None:
        self.conn.execute(
            """
            INSERT INTO relations (id, source_memory_id, target_memory_id, relation_type, weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id("rel"), source, target, relation_type, float(weight), utc_now()),
        )
        self.conn.commit()

    def add_contradiction(self, new_memory_id: str, old_memory_id: str, score: float) -> None:
        self.conn.execute(
            """
            INSERT INTO contradictions (id, new_memory_id, old_memory_id, contradiction_score, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id("contra"), new_memory_id, old_memory_id, float(score), "unresolved", utc_now()),
        )
        self.conn.commit()

    def add_event(self, memory_id: str | None, event_type: str, value: float | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO events (id, memory_id, event_type, value, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("evt"),
                memory_id,
                event_type,
                None if value is None else float(value),
                json.dumps(metadata or {}, separators=(",", ":")),
                utc_now(),
            ),
        )
        self.conn.commit()

    def get_runtime_state(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT value FROM runtime_state WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def set_runtime_state(self, key: str, value: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO runtime_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, sort_keys=True, separators=(",", ":")), utc_now()),
        )
        self.conn.commit()

    def vector_dimensions(self) -> list[int]:
        rows = self.conn.execute("SELECT DISTINCT dim FROM vectors ORDER BY dim").fetchall()
        return [int(row[0]) for row in rows]

    def stats(self) -> dict[str, Any]:
        memories = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        domains = self.conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        contradictions = self.conn.execute("SELECT COUNT(*) FROM contradictions").fetchone()[0]
        feedback = self.conn.execute("SELECT COUNT(*) FROM retrieval_feedback").fetchone()[0]
        return {
            "memories": memories,
            "domains": domains,
            "contradictions": contradictions,
            "retrieval_feedback": feedback,
            "vector_dimensions": self.vector_dimensions(),
            "embedding_signature": self.get_runtime_state("embedding_signature"),
        }

    def _domain_from_row(self, row: sqlite3.Row) -> DomainState:
        return DomainState(
            id=row["id"],
            name=row["name"],
            anchor_vector=decode_vector(row["anchor_vector"]),
            effective_dimension=float(row["effective_dimension"] or 1.0),
            drift_ema=float(row["drift_ema"] or 0.0),
            drift_var=float(row["drift_var"] or 0.0),
            curvature_ema=float(row["curvature_ema"] or 0.0),
            stability=float(row["stability"] or 0.0),
            memory_count=int(row["memory_count"] or 0),
            previous_update_direction=decode_vector(row["previous_update_direction"]) if row["previous_update_direction"] else None,
        )
