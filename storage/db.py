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


def normalize_namespace(namespace: str | None) -> str:
    cleaned = str(namespace or "").strip()
    return cleaned or "global"


def normalize_namespaces(namespaces: list[str] | tuple[str, ...] | set[str] | None) -> list[str] | None:
    if namespaces is None:
        return None
    out = []
    seen = set()
    for namespace in namespaces:
        normalized = normalize_namespace(namespace)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out or ["global"]


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
        try:
            self.conn.executescript(sql)
        except sqlite3.OperationalError as exc:
            if "no such column: namespace" not in str(exc):
                raise
            self._ensure_migrations()
            self.conn.executescript(sql)
        self._ensure_migrations()
        self.conn.commit()

    def _ensure_migrations(self) -> None:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(memories)").fetchall()}
        if "namespace" not in columns:
            self.conn.execute("ALTER TABLE memories ADD COLUMN namespace TEXT DEFAULT 'global'")
            self.conn.execute("UPDATE memories SET namespace='global' WHERE namespace IS NULL OR namespace=''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace)")
        domain_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(domains)").fetchall()}
        if "namespace" not in domain_columns:
            self.conn.execute("ALTER TABLE domains ADD COLUMN namespace TEXT DEFAULT 'global'")
            self.conn.execute("UPDATE domains SET namespace='global' WHERE namespace IS NULL OR namespace=''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_domains_namespace_name ON domains(namespace, name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_memory (
                session_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY(session_id, key),
                FOREIGN KEY(session_id) REFERENCES agent_sessions(id)
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_session_memory_session ON session_memory(session_id)")

    def upsert_domain(self, domain: DomainState) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO domains (
                id, name, namespace, anchor_vector, effective_dimension, drift_ema,
                drift_var, curvature_ema, stability, memory_count,
                previous_update_direction, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                namespace=excluded.namespace,
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
                normalize_namespace(domain.namespace),
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

    def get_domain_by_name(self, name: str, namespace: str | None = None) -> DomainState | None:
        normalized_namespace = normalize_namespace(namespace)
        row = self.conn.execute(
            """
            SELECT *
            FROM domains
            WHERE name=? AND COALESCE(namespace, 'global')=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (name, normalized_namespace),
        ).fetchone()
        return self._domain_from_row(row) if row else None

    def memory_exists_text(self, text: str, namespace: str | None = None) -> bool:
        normalized_namespace = normalize_namespace(namespace)
        row = self.conn.execute(
            """
            SELECT 1
            FROM memories
            WHERE text=? AND deprecated=0
              AND (? IS NULL OR namespace=?)
            LIMIT 1
            """,
            (str(text or "").strip(), normalized_namespace, normalized_namespace),
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

    def memory_ids_for_source(self, source: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT m.id
            FROM memories m
            JOIN memory_sources s ON s.memory_id = m.id
            WHERE s.source=? AND m.deprecated=0
            ORDER BY s.chunk_index ASC, m.created_at ASC
            """,
            (source,),
        ).fetchall()
        return [row["id"] for row in rows]

    def create_session(
        self,
        agent_id: str = "default",
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        normalized_agent_id = str(agent_id or "default").strip() or "default"
        sid = str(session_id or "").strip() or new_id("sess")
        self.conn.execute(
            """
            INSERT INTO agent_sessions (id, agent_id, title, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent_id=excluded.agent_id,
                title=COALESCE(excluded.title, agent_sessions.title),
                metadata=excluded.metadata,
                updated_at=excluded.updated_at
            """,
            (
                sid,
                normalized_agent_id,
                title,
                json.dumps(metadata or {}, separators=(",", ":")),
                now,
                now,
            ),
        )
        self.conn.commit()
        return {
            "id": sid,
            "agent_id": normalized_agent_id,
            "title": title,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "title": row["title"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def ensure_session(
        self,
        session_id: str | None = None,
        agent_id: str = "default",
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if sid:
            existing = self.get_session(sid)
            if existing is not None:
                return existing
            return self.create_session(agent_id=agent_id, title=title, metadata=metadata, session_id=sid)
        return self.create_session(agent_id=agent_id, title=title, metadata=metadata)

    def add_session_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        query: str | None = None,
        answer: str | None = None,
        confidence: float | None = None,
        conflict: bool = False,
        evidence_memory_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.get_session(session_id) is None:
            raise ValueError(f"unknown session_id: {session_id}")
        turn_id = new_id("turn")
        created_at = utc_now()
        self.conn.execute(
            """
            INSERT INTO session_turns (
                id, session_id, role, content, query, answer, confidence,
                conflict, evidence_memory_ids, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                str(role or "").strip().lower() or "event",
                content,
                query,
                answer,
                None if confidence is None else float(confidence),
                1 if conflict else 0,
                json.dumps(evidence_memory_ids or [], separators=(",", ":")),
                json.dumps(metadata or {}, separators=(",", ":")),
                created_at,
            ),
        )
        self.conn.execute(
            "UPDATE agent_sessions SET updated_at=? WHERE id=?",
            (created_at, session_id),
        )
        self.conn.commit()
        return {
            "id": turn_id,
            "session_id": session_id,
            "role": str(role or "").strip().lower() or "event",
            "created_at": created_at,
        }

    def session_history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM session_turns
            WHERE session_id=?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, int(limit)),
        ).fetchall()
        return [self._session_turn_from_row(row) for row in rows]

    def recent_session_turns(self, session_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM session_turns
            WHERE session_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, int(limit)),
        ).fetchall()
        turns = [self._session_turn_from_row(row) for row in rows]
        return list(reversed(turns))

    def latest_assistant_evidence(self, session_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT evidence_memory_ids
            FROM session_turns
            WHERE session_id=? AND role='assistant'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchall()
        if not rows:
            return []
        return [str(item) for item in json.loads(rows[0]["evidence_memory_ids"] or "[]") if str(item or "").strip()]

    def upsert_session_memory(
        self,
        session_id: str,
        key: str,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.get_session(session_id) is None:
            raise ValueError(f"unknown session_id: {session_id}")
        normalized_key = str(key or "").strip().lower()
        cleaned = str(value or "").strip()
        if not normalized_key:
            raise ValueError("session memory key is required")
        if not cleaned:
            raise ValueError("session memory value is required")
        now = utc_now()
        existing = self.conn.execute(
            "SELECT created_at FROM session_memory WHERE session_id=? AND key=?",
            (session_id, normalized_key),
        ).fetchone()
        created_at = existing["created_at"] if existing is not None else now
        self.conn.execute(
            """
            INSERT INTO session_memory (session_id, key, value, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, key) DO UPDATE SET
                value=excluded.value,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at
            """,
            (
                session_id,
                normalized_key,
                cleaned,
                json.dumps(metadata or {}, separators=(",", ":")),
                created_at,
                now,
            ),
        )
        self.conn.execute("UPDATE agent_sessions SET updated_at=? WHERE id=?", (now, session_id))
        self.conn.commit()
        return {
            "session_id": session_id,
            "key": normalized_key,
            "value": cleaned,
            "metadata": metadata or {},
            "created_at": created_at,
            "updated_at": now,
        }

    def get_session_memory(self, session_id: str, key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM session_memory WHERE session_id=? AND key=?",
            (session_id, str(key or "").strip().lower()),
        ).fetchone()
        if row is None:
            return None
        return self._session_memory_from_row(row)

    def list_session_memory(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM session_memory
            WHERE session_id=?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (session_id, int(limit)),
        ).fetchall()
        return [self._session_memory_from_row(row) for row in rows]

    def list_sessions(self, agent_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if agent_id:
            rows = self.conn.execute(
                """
                SELECT s.*, COUNT(t.id) AS turn_count
                FROM agent_sessions s
                LEFT JOIN session_turns t ON t.session_id = s.id
                WHERE s.agent_id=?
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (agent_id, int(limit)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT s.*, COUNT(t.id) AS turn_count
                FROM agent_sessions s
                LEFT JOIN session_turns t ON t.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "agent_id": row["agent_id"],
                "title": row["title"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "turn_count": int(row["turn_count"] or 0),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
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

    def feedback_summary_for_memories(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [str(memory_id) for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT memory_id, COUNT(*) AS count, AVG(rating) AS avg_rating,
                   SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) AS positive,
                   SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) AS negative
            FROM retrieval_feedback
            WHERE memory_id IN ({placeholders})
            GROUP BY memory_id
            """,
            ids,
        ).fetchall()
        return {
            row["memory_id"]: {
                "count": int(row["count"] or 0),
                "avg_rating": 0.0 if row["avg_rating"] is None else float(row["avg_rating"]),
                "positive": int(row["positive"] or 0),
                "negative": int(row["negative"] or 0),
            }
            for row in rows
        }

    def usage_summary_for_memories(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [str(memory_id) for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT memory_id, COUNT(*) AS count, MAX(created_at) AS last_recalled
            FROM events
            WHERE event_type='retrieval_use'
              AND memory_id IN ({placeholders})
            GROUP BY memory_id
            """,
            ids,
        ).fetchall()
        return {
            row["memory_id"]: {
                "count": int(row["count"] or 0),
                "last_recalled": row["last_recalled"],
            }
            for row in rows
        }

    def feedback_reliability_for_candidates(self, memory_ids: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
        ids = [str(memory_id) for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return {"domains": {}, "sources": {}}
        placeholders = ",".join("?" for _ in ids)
        domain_rows = self.conn.execute(
            f"""
            SELECT m.domain_id AS key, COUNT(f.id) AS count, AVG(f.rating) AS avg_rating
            FROM retrieval_feedback f
            JOIN memories m ON m.id = f.memory_id
            WHERE m.domain_id IN (
                SELECT DISTINCT domain_id
                FROM memories
                WHERE id IN ({placeholders}) AND domain_id IS NOT NULL
            )
            GROUP BY m.domain_id
            """,
            ids,
        ).fetchall()
        source_rows = self.conn.execute(
            f"""
            SELECT s.source AS key, COUNT(f.id) AS count, AVG(f.rating) AS avg_rating
            FROM retrieval_feedback f
            JOIN memory_sources s ON s.memory_id = f.memory_id
            WHERE s.source IN (
                SELECT DISTINCT source
                FROM memory_sources
                WHERE memory_id IN ({placeholders}) AND source IS NOT NULL
            )
            GROUP BY s.source
            """,
            ids,
        ).fetchall()
        return {
            "domains": self._feedback_reliability_map(domain_rows),
            "sources": self._feedback_reliability_map(source_rows),
        }

    @staticmethod
    def _feedback_reliability_map(rows: list[sqlite3.Row]) -> dict[str, dict[str, Any]]:
        return {
            row["key"]: {
                "count": int(row["count"] or 0),
                "avg_rating": 0.0 if row["avg_rating"] is None else float(row["avg_rating"]),
            }
            for row in rows
            if row["key"] is not None
        }

    def list_domains(self, namespaces: list[str] | None = None) -> list[DomainState]:
        normalized_namespaces = normalize_namespaces(namespaces)
        params: list[Any] = []
        where = ""
        if normalized_namespaces is not None:
            placeholders = ",".join("?" for _ in normalized_namespaces)
            where = f"WHERE COALESCE(namespace, 'global') IN ({placeholders})"
            params.extend(normalized_namespaces)
        rows = self.conn.execute(
            f"SELECT * FROM domains {where} ORDER BY memory_count DESC, updated_at DESC",
            params,
        ).fetchall()
        return [self._domain_from_row(row) for row in rows]

    def insert_memory(self, memory: MemoryNode) -> None:
        namespace = normalize_namespace(memory.namespace)
        self.conn.execute(
            """
            INSERT INTO memories (
                id, text, summary, domain_id, memory_type, importance,
                stability, confidence, csd_score, surprise, recall_score,
                curiosity, focus, clc_state, namespace, created_at, updated_at,
                deprecated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                namespace,
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

    def list_memory_vectors(
        self,
        include_deprecated: bool = False,
        namespaces: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if not include_deprecated:
            clauses.append("m.deprecated=0")
        normalized_namespaces = normalize_namespaces(namespaces)
        if normalized_namespaces is not None:
            placeholders = ",".join("?" for _ in normalized_namespaces)
            clauses.append(f"COALESCE(m.namespace, 'global') IN ({placeholders})")
            params.extend(normalized_namespaces)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT m.id, m.text, m.domain_id, m.memory_type, m.importance,
                   m.stability, COALESCE(m.namespace, 'global') AS namespace, m.deprecated, v.embedding
            FROM memories m
            JOIN vectors v ON v.memory_id = m.id
            {where}
            """,
            params,
        ).fetchall()
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "domain_id": row["domain_id"],
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "namespace": normalize_namespace(row["namespace"]),
                "deprecated": bool(row["deprecated"]),
                "embedding": decode_vector(row["embedding"]),
            }
            for row in rows
        ]

    def memory_vectors_by_ids(
        self,
        memory_ids: list[str],
        include_deprecated: bool = False,
    ) -> list[dict[str, Any]]:
        ids = [str(memory_id).strip() for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        clauses = [f"m.id IN ({placeholders})"]
        params: list[Any] = list(ids)
        if not include_deprecated:
            clauses.append("m.deprecated=0")
        rows = self.conn.execute(
            f"""
            SELECT m.id, m.text, m.domain_id, m.memory_type, m.importance,
                   m.stability, COALESCE(m.namespace, 'global') AS namespace, m.deprecated, v.embedding
            FROM memories m
            JOIN vectors v ON v.memory_id = m.id
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchall()
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "domain_id": row["domain_id"],
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "namespace": normalize_namespace(row["namespace"]),
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
        existing = self.conn.execute(
            """
            SELECT 1
            FROM relations
            WHERE source_memory_id=? AND target_memory_id=? AND relation_type=?
            LIMIT 1
            """,
            (source, target, relation_type),
        ).fetchone()
        if existing is not None:
            return
        self.conn.execute(
            """
            INSERT INTO relations (id, source_memory_id, target_memory_id, relation_type, weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id("rel"), source, target, relation_type, float(weight), utc_now()),
        )
        self.conn.commit()

    def authority_graph_for_memories(
        self,
        memory_ids: list[str],
        relation_types: tuple[str, ...] = ("supersedes", "corrects", "updates"),
        max_depth: int = 8,
    ) -> dict[str, Any]:
        seeds = {str(memory_id).strip() for memory_id in memory_ids if str(memory_id or "").strip()}
        types = [str(relation_type).strip() for relation_type in relation_types if str(relation_type or "").strip()]
        if not seeds or not types:
            return {"seeds": sorted(seeds), "memory_ids": sorted(seeds), "relations": []}
        type_placeholders = ",".join("?" for _ in types)
        seen_nodes = set(seeds)
        frontier = set(seeds)
        relations: dict[tuple[str, str, str], dict[str, Any]] = {}
        for _depth in range(max(1, int(max_depth))):
            if not frontier:
                break
            id_placeholders = ",".join("?" for _ in frontier)
            rows = self.conn.execute(
                f"""
                SELECT r.source_memory_id, r.target_memory_id, r.relation_type, r.weight, r.created_at
                FROM relations r
                JOIN memories sm ON sm.id = r.source_memory_id AND sm.deprecated=0
                JOIN memories tm ON tm.id = r.target_memory_id AND tm.deprecated=0
                WHERE r.relation_type IN ({type_placeholders})
                  AND (r.source_memory_id IN ({id_placeholders}) OR r.target_memory_id IN ({id_placeholders}))
                """,
                types + list(frontier) + list(frontier),
            ).fetchall()
            next_frontier: set[str] = set()
            for row in rows:
                source_id = row["source_memory_id"]
                target_id = row["target_memory_id"]
                key = (source_id, target_id, row["relation_type"])
                if key not in relations:
                    relations[key] = {
                        "source_memory_id": source_id,
                        "target_memory_id": target_id,
                        "relation_type": row["relation_type"],
                        "weight": float(row["weight"] or 0.0),
                        "created_at": row["created_at"],
                    }
                for memory_id in (source_id, target_id):
                    if memory_id and memory_id not in seen_nodes:
                        seen_nodes.add(memory_id)
                        next_frontier.add(memory_id)
            frontier = next_frontier
        return {
            "seeds": sorted(seeds),
            "memory_ids": sorted(seen_nodes),
            "relations": list(relations.values()),
        }

    def supersession_summary_for_candidates(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [str(memory_id) for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT source_memory_id, target_memory_id, relation_type, weight
            FROM relations
            WHERE relation_type IN ('supersedes', 'corrects', 'updates')
              AND (source_memory_id IN ({placeholders}) OR target_memory_id IN ({placeholders}))
            """,
            ids + ids,
        ).fetchall()
        summary: dict[str, dict[str, Any]] = {
            memory_id: {
                "outgoing_count": 0,
                "incoming_count": 0,
                "outgoing_weight": 0.0,
                "incoming_weight": 0.0,
                "relation_types": [],
            }
            for memory_id in ids
        }
        for row in rows:
            source_id = row["source_memory_id"]
            target_id = row["target_memory_id"]
            relation_type = row["relation_type"]
            weight = float(row["weight"] or 0.0)
            if source_id in summary:
                item = summary[source_id]
                item["outgoing_count"] += 1
                item["outgoing_weight"] += weight
                item["relation_types"].append(relation_type)
            if target_id in summary:
                item = summary[target_id]
                item["incoming_count"] += 1
                item["incoming_weight"] += weight
                item["relation_types"].append(relation_type)
        return summary

    def summary_relation_summary_for_candidates(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        return self._relation_summary_for_candidates(memory_ids, ("summarizes",))

    def _relation_summary_for_candidates(
        self,
        memory_ids: list[str],
        relation_types: tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        ids = [str(memory_id) for memory_id in memory_ids if str(memory_id or "").strip()]
        types = [str(relation_type) for relation_type in relation_types if str(relation_type or "").strip()]
        if not ids or not types:
            return {}
        id_placeholders = ",".join("?" for _ in ids)
        type_placeholders = ",".join("?" for _ in types)
        rows = self.conn.execute(
            f"""
            SELECT source_memory_id, target_memory_id, relation_type, weight
            FROM relations
            WHERE relation_type IN ({type_placeholders})
              AND (source_memory_id IN ({id_placeholders}) OR target_memory_id IN ({id_placeholders}))
            """,
            types + ids + ids,
        ).fetchall()
        summary: dict[str, dict[str, Any]] = {
            memory_id: {
                "outgoing_count": 0,
                "incoming_count": 0,
                "outgoing_weight": 0.0,
                "incoming_weight": 0.0,
                "relation_types": [],
            }
            for memory_id in ids
        }
        for row in rows:
            source_id = row["source_memory_id"]
            target_id = row["target_memory_id"]
            relation_type = row["relation_type"]
            weight = float(row["weight"] or 0.0)
            if source_id in summary:
                item = summary[source_id]
                item["outgoing_count"] += 1
                item["outgoing_weight"] += weight
                item["relation_types"].append(relation_type)
            if target_id in summary:
                item = summary[target_id]
                item["incoming_count"] += 1
                item["incoming_weight"] += weight
                item["relation_types"].append(relation_type)
        return summary

    def superseded_memories_for_sources(self, source_memory_ids: list[str], limit: int = 5) -> list[dict[str, Any]]:
        ids = [str(memory_id) for memory_id in source_memory_ids if str(memory_id or "").strip()]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT
                r.source_memory_id AS current_memory_id,
                r.target_memory_id AS memory_id,
                r.relation_type,
                r.weight AS relation_weight,
                m.text,
                m.domain_id,
                d.name AS domain_name,
                m.memory_type,
                m.importance,
                m.stability,
                s.source,
                s.chunk_index
            FROM relations r
            JOIN memories m ON m.id = r.target_memory_id
            LEFT JOIN domains d ON d.id = m.domain_id
            LEFT JOIN memory_sources s ON s.memory_id = m.id
            WHERE r.relation_type IN ('supersedes', 'corrects', 'updates')
              AND r.source_memory_id IN ({placeholders})
              AND m.deprecated=0
            ORDER BY r.weight DESC, m.updated_at DESC
            LIMIT ?
            """,
            ids + [max(1, int(limit))],
        ).fetchall()
        return [
            {
                "current_memory_id": row["current_memory_id"],
                "memory_id": row["memory_id"],
                "relation_type": row["relation_type"],
                "relation_weight": float(row["relation_weight"] or 0.0),
                "text": row["text"],
                "domain_id": row["domain_id"],
                "domain_name": row["domain_name"],
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "source": row["source"],
                "chunk_index": None if row["chunk_index"] is None else int(row["chunk_index"]),
            }
            for row in rows
        ]

    def summarized_memories_for_sources(self, summary_memory_ids: list[str], limit: int = 8) -> list[dict[str, Any]]:
        ids = [str(memory_id) for memory_id in summary_memory_ids if str(memory_id or "").strip()]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT
                r.source_memory_id AS summary_memory_id,
                r.target_memory_id AS memory_id,
                r.relation_type,
                r.weight AS relation_weight,
                m.text,
                m.domain_id,
                d.name AS domain_name,
                m.memory_type,
                m.importance,
                m.stability,
                s.source,
                s.chunk_index
            FROM relations r
            JOIN memories m ON m.id = r.target_memory_id
            LEFT JOIN domains d ON d.id = m.domain_id
            LEFT JOIN memory_sources s ON s.memory_id = m.id
            WHERE r.relation_type='summarizes'
              AND r.source_memory_id IN ({placeholders})
              AND m.deprecated=0
            ORDER BY r.weight DESC, m.updated_at DESC
            LIMIT ?
            """,
            ids + [max(1, int(limit))],
        ).fetchall()
        return [
            {
                "summary_memory_id": row["summary_memory_id"],
                "memory_id": row["memory_id"],
                "relation_type": row["relation_type"],
                "relation_weight": float(row["relation_weight"] or 0.0),
                "text": row["text"],
                "domain_id": row["domain_id"],
                "domain_name": row["domain_name"],
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "source": row["source"],
                "chunk_index": None if row["chunk_index"] is None else int(row["chunk_index"]),
            }
            for row in rows
        ]

    def relation_counts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT relation_type, COUNT(*) AS count, AVG(weight) AS avg_weight
            FROM relations
            GROUP BY relation_type
            ORDER BY count DESC, relation_type
            """
        ).fetchall()
        return [
            {
                "relation_type": row["relation_type"],
                "count": int(row["count"] or 0),
                "avg_weight": None if row["avg_weight"] is None else round(float(row["avg_weight"]), 4),
            }
            for row in rows
        ]

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

    def record_retrieval_use(
        self,
        evidence: list[dict[str, Any]],
        query: str,
        answer: str | None = None,
        confidence: float | None = None,
        namespace: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        now = utc_now()
        seen: set[str] = set()
        for index, item in enumerate(evidence, start=1):
            memory_id = str(item.get("memory_id") or "").strip()
            if not memory_id or memory_id in seen:
                continue
            seen.add(memory_id)
            event_id = new_id("evt")
            value = float(item.get("score") or 0.0)
            metadata = {
                "query": query,
                "answer_preview": str(answer or "")[:320],
                "confidence": confidence,
                "rank": item.get("rank") or index,
                "memory_state": item.get("memory_state"),
                "namespace": normalize_namespace(namespace),
                "agent_id": agent_id,
                "session_id": session_id,
                "retrieval_score": item.get("score"),
                "domain_name": item.get("domain_name"),
                "source": item.get("source"),
            }
            self.conn.execute(
                """
                INSERT INTO events (id, memory_id, event_type, value, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    memory_id,
                    "retrieval_use",
                    value,
                    json.dumps(metadata, separators=(",", ":")),
                    now,
                ),
            )
            self.conn.execute("UPDATE memories SET last_recalled=?, updated_at=? WHERE id=?", (now, now, memory_id))
            rows.append({"id": event_id, "memory_id": memory_id, "rank": metadata["rank"], "score": value, "created_at": now})
        self.conn.commit()
        return rows

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
        retrieval_uses = self.conn.execute("SELECT COUNT(*) FROM events WHERE event_type='retrieval_use'").fetchone()[0]
        relations = self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        sessions = self.conn.execute("SELECT COUNT(*) FROM agent_sessions").fetchone()[0]
        session_turns = self.conn.execute("SELECT COUNT(*) FROM session_turns").fetchone()[0]
        session_memory = self.conn.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
        return {
            "memories": memories,
            "domains": domains,
            "contradictions": contradictions,
            "retrieval_feedback": feedback,
            "retrieval_uses": retrieval_uses,
            "relations": relations,
            "sessions": sessions,
            "session_turns": session_turns,
            "session_memory": session_memory,
            "vector_dimensions": self.vector_dimensions(),
            "embedding_signature": self.get_runtime_state("embedding_signature"),
        }

    def namespace_counts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT COALESCE(namespace, 'global') AS namespace, COUNT(*) AS count
            FROM memories
            WHERE deprecated=0
            GROUP BY COALESCE(namespace, 'global')
            ORDER BY count DESC, namespace
            """
        ).fetchall()
        return [{"namespace": normalize_namespace(row["namespace"]), "count": int(row["count"] or 0)} for row in rows]

    def memory_usage(
        self,
        limit: int = 20,
        namespace: str | None = None,
        include_global: bool = True,
        memory_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["e.event_type='retrieval_use'", "m.deprecated=0"]
        params: list[Any] = []
        if memory_id:
            clauses.append("e.memory_id=?")
            params.append(str(memory_id))
        normalized = normalize_namespace(namespace)
        if namespace is not None:
            namespaces = [normalized]
            if include_global and normalized != "global":
                namespaces.insert(0, "global")
            placeholders = ",".join("?" for _ in namespaces)
            clauses.append(f"COALESCE(m.namespace, 'global') IN ({placeholders})")
            params.extend(namespaces)
        where = " AND ".join(clauses)
        rows = self.conn.execute(
            f"""
            SELECT
                e.memory_id,
                COUNT(*) AS use_count,
                MAX(e.created_at) AS last_recalled,
                AVG(e.value) AS avg_retrieval_score,
                m.text,
                COALESCE(m.namespace, 'global') AS namespace,
                m.memory_type,
                d.name AS domain_name,
                s.source
            FROM events e
            JOIN memories m ON m.id=e.memory_id
            LEFT JOIN domains d ON d.id=m.domain_id
            LEFT JOIN memory_sources s ON s.memory_id=m.id
            WHERE {where}
            GROUP BY e.memory_id
            ORDER BY use_count DESC, last_recalled DESC
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
        return [
            {
                "memory_id": row["memory_id"],
                "use_count": int(row["use_count"] or 0),
                "last_recalled": row["last_recalled"],
                "avg_retrieval_score": 0.0 if row["avg_retrieval_score"] is None else round(float(row["avg_retrieval_score"]), 6),
                "namespace": normalize_namespace(row["namespace"]),
                "domain_name": row["domain_name"],
                "memory_type": row["memory_type"],
                "source": row["source"],
                "text_preview": str(row["text"] or "")[:320],
            }
            for row in rows
        ]

    @staticmethod
    def _session_turn_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "query": row["query"],
            "answer": row["answer"],
            "confidence": None if row["confidence"] is None else float(row["confidence"]),
            "conflict": bool(row["conflict"]),
            "evidence_memory_ids": json.loads(row["evidence_memory_ids"] or "[]"),
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _session_memory_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "key": row["key"],
            "value": row["value"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _domain_from_row(self, row: sqlite3.Row) -> DomainState:
        return DomainState(
            id=row["id"],
            name=row["name"],
            anchor_vector=decode_vector(row["anchor_vector"]),
            namespace=normalize_namespace(row["namespace"] if "namespace" in row.keys() else None),
            effective_dimension=float(row["effective_dimension"] or 1.0),
            drift_ema=float(row["drift_ema"] or 0.0),
            drift_var=float(row["drift_var"] or 0.0),
            curvature_ema=float(row["curvature_ema"] or 0.0),
            stability=float(row["stability"] or 0.0),
            memory_count=int(row["memory_count"] or 0),
            previous_update_direction=decode_vector(row["previous_update_direction"]) if row["previous_update_direction"] else None,
        )
