"""Canonical memory view construction.

This module builds non-destructive canonical claim groups from existing memory
rows. It is deliberately a view layer: repeated rows remain available as
support/provenance instead of being blindly deleted.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFLICT_MARKERS = (
    "not",
    "no",
    "never",
    "without",
    "false",
    "wrong",
    "drops",
    "drop",
    "excludes",
    "rejects",
    "avoids",
    "stopped",
    "removed",
    "deprecated",
    "outdated",
)
UPDATE_MARKERS = (
    "correction",
    "current",
    "latest",
    "changed",
    "replace",
    "instead",
    "anymore",
    "no longer",
    "previous",
    "old",
    "legacy",
)


@dataclass(frozen=True)
class CanonicalClaim:
    id: str
    canonical_text: str
    keeper_memory_id: str
    support_count: int
    support_memory_ids: list[str]
    duplicate_memory_ids: list[str]
    domain_counts: dict[str, int]
    namespace_counts: dict[str, int]
    source_counts: dict[str, int]
    first_seen: str
    last_seen: str
    confidence: float
    importance: float
    status: str
    warnings: list[str]
    examples: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canonical_text": self.canonical_text,
            "keeper_memory_id": self.keeper_memory_id,
            "support_count": self.support_count,
            "support_memory_ids": self.support_memory_ids,
            "duplicate_memory_ids": self.duplicate_memory_ids,
            "domain_counts": self.domain_counts,
            "namespace_counts": self.namespace_counts,
            "source_counts": self.source_counts,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "confidence": self.confidence,
            "importance": self.importance,
            "status": self.status,
            "warnings": self.warnings,
            "examples": self.examples,
        }


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def parse_embedding(value: Any) -> list[float]:
    raw = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value or "")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [float(x) for x in loaded] if isinstance(loaded, list) else []


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return dot / (left_norm * right_norm)


def tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return {part for part in cleaned.split() if part}


def jaccard(left: str, right: str) -> float:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def marker_hits(text: str, markers: tuple[str, ...]) -> set[str]:
    lowered = normalize_text(text)
    return {marker for marker in markers if marker in lowered}


def possible_conflict_or_update(left: str, right: str) -> bool:
    left_conflict = marker_hits(left, CONFLICT_MARKERS)
    right_conflict = marker_hits(right, CONFLICT_MARKERS)
    left_update = marker_hits(left, UPDATE_MARKERS)
    right_update = marker_hits(right, UPDATE_MARKERS)
    return left_conflict != right_conflict or left_update != right_update


def quality(row: dict[str, Any]) -> tuple[float, str, str]:
    return (
        float(row.get("confidence") or 0.0) * float(row.get("importance") or 0.0),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def load_memory_rows(db_path: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT m.id, m.text, m.domain_id, m.namespace, m.memory_type,
               m.importance, m.confidence, m.created_at, m.updated_at,
               COALESCE(m.deprecated, 0) AS deprecated,
               s.source, s.chunk_index, s.metadata AS source_metadata,
               v.embedding
        FROM memories m
        JOIN vectors v ON v.memory_id = m.id
        LEFT JOIN memory_sources s ON s.memory_id = m.id
        WHERE COALESCE(m.deprecated, 0) = 0
        ORDER BY m.created_at ASC, m.id ASC
    """
    params: list[Any] = []
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    conn.close()
    for row in rows:
        row["normalized_text"] = normalize_text(row.get("text"))
        row["embedding"] = parse_embedding(row.get("embedding"))
        row["namespace"] = str(row.get("namespace") or "global")
        row["domain_id"] = str(row.get("domain_id") or "")
        row["source"] = str(row.get("source") or "")
    return rows


def exact_claim_groups(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["normalized_text"]].append(row)
    return [group for _, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))]


def build_exact_canonical_claims(rows: list[dict[str, Any]]) -> list[CanonicalClaim]:
    claims = []
    for index, group in enumerate(exact_claim_groups(rows), start=1):
        keeper = max(group, key=quality)
        support_ids = [str(row["id"]) for row in group]
        duplicate_ids = [memory_id for memory_id in support_ids if memory_id != keeper["id"]]
        domain_counts = Counter(str(row.get("domain_id") or "") for row in group)
        namespace_counts = Counter(str(row.get("namespace") or "global") for row in group)
        source_counts = Counter(str(row.get("source") or "") for row in group if str(row.get("source") or ""))
        warnings = []
        if len(domain_counts) > 1:
            warnings.append("cross_domain_support")
        if len(namespace_counts) > 1:
            warnings.append("cross_namespace_support")
        claims.append(
            CanonicalClaim(
                id=f"canonical_exact:{index:05d}",
                canonical_text=str(keeper["text"]),
                keeper_memory_id=str(keeper["id"]),
                support_count=len(group),
                support_memory_ids=support_ids,
                duplicate_memory_ids=duplicate_ids,
                domain_counts=dict(domain_counts.most_common()),
                namespace_counts=dict(namespace_counts.most_common()),
                source_counts=dict(source_counts.most_common()),
                first_seen=min(str(row.get("created_at") or "") for row in group),
                last_seen=max(str(row.get("created_at") or "") for row in group),
                confidence=float(keeper.get("confidence") or 0.0),
                importance=float(keeper.get("importance") or 0.0),
                status="exact_canonical",
                warnings=warnings,
                examples=[
                    {
                        "memory_id": str(row["id"]),
                        "domain_id": row.get("domain_id"),
                        "namespace": row.get("namespace"),
                        "created_at": row.get("created_at"),
                    }
                    for row in group[:6]
                ],
            )
        )
    return claims


def semantic_edges(
    claims: list[CanonicalClaim],
    row_by_id: dict[str, dict[str, Any]],
    *,
    similarity_threshold: float = 0.90,
    jaccard_min: float = 0.35,
    max_pairs: int = 50000,
) -> list[dict[str, Any]]:
    edges = []
    pairs = 0
    for i, left_claim in enumerate(claims):
        left = row_by_id.get(left_claim.keeper_memory_id)
        if not left:
            continue
        for right_claim in claims[i + 1 :]:
            pairs += 1
            if pairs > max_pairs:
                return edges
            right = row_by_id.get(right_claim.keeper_memory_id)
            if not right:
                continue
            if left.get("domain_id") and right.get("domain_id") and left.get("domain_id") != right.get("domain_id"):
                continue
            sim = cosine(left.get("embedding") or [], right.get("embedding") or [])
            jac = jaccard(left_claim.canonical_text, right_claim.canonical_text)
            if sim >= similarity_threshold and jac >= jaccard_min:
                edges.append(
                    {
                        "left_claim_id": left_claim.id,
                        "right_claim_id": right_claim.id,
                        "left_memory_id": left_claim.keeper_memory_id,
                        "right_memory_id": right_claim.keeper_memory_id,
                        "cosine": round(sim, 6),
                        "jaccard": round(jac, 6),
                        "possible_conflict_or_update": possible_conflict_or_update(
                            left_claim.canonical_text,
                            right_claim.canonical_text,
                        ),
                        "left_text": left_claim.canonical_text[:240],
                        "right_text": right_claim.canonical_text[:240],
                    }
                )
    return edges


def build_canonical_view(
    db_path: str | Path,
    *,
    limit: int | None = None,
    similarity_threshold: float = 0.90,
    jaccard_min: float = 0.35,
    max_pairs: int = 50000,
) -> dict[str, Any]:
    rows = load_memory_rows(db_path, limit=limit)
    row_by_id = {str(row["id"]): row for row in rows}
    exact_claims = build_exact_canonical_claims(rows)
    semantic = semantic_edges(
        exact_claims,
        row_by_id,
        similarity_threshold=similarity_threshold,
        jaccard_min=jaccard_min,
        max_pairs=max_pairs,
    )
    semantic_counts = Counter(
        "conflict_or_update" if edge["possible_conflict_or_update"] else "clean_paraphrase"
        for edge in semantic
    )
    duplicate_claims = [claim for claim in exact_claims if claim.support_count > 1]
    return {
        "schema": "canonical_memory_view/v1",
        "mutates_db": False,
        "db_path": str(db_path),
        "row_count": len(rows),
        "canonical_claim_count": len(exact_claims),
        "exact_duplicate_claim_count": len(duplicate_claims),
        "exact_duplicate_extra_row_count": sum(claim.support_count - 1 for claim in duplicate_claims),
        "semantic_edge_count": len(semantic),
        "semantic_edge_counts": dict(sorted(semantic_counts.items())),
        "config": {
            "limit": limit,
            "similarity_threshold": similarity_threshold,
            "jaccard_min": jaccard_min,
            "max_pairs": max_pairs,
        },
        "canonical_claims": [claim.to_dict() for claim in exact_claims],
        "semantic_edges": semantic,
    }
