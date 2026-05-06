from __future__ import annotations

from collections import defaultdict
from typing import Any

from storage.db import MemoryDB, normalize_namespace, normalize_namespaces


PROTECTIVE_RELATIONS = {"supersedes", "corrects", "updates"}
CONSOLIDATION_RELATIONS = {"summarizes"}


def consolidation_plan(
    db: MemoryDB,
    min_domain_memories: int = 4,
    max_candidates_per_domain: int = 8,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    """Plan safe consolidation candidates without rewriting memory.

    Correction/update chains and existing summary chains are protected because
    the program depends on explicit evidence, not destructive replacement.
    """

    namespaces = namespace_scope(namespace, include_global=include_global)
    protected = protected_memory_ids(db, namespaces=namespaces)
    namespace_filter, namespace_params = sql_namespace_filter("m", namespaces)
    rows = db.conn.execute(
        f"""
        SELECT
            m.id,
            m.text,
            m.domain_id,
            COALESCE(m.namespace, 'global') AS namespace,
            d.name AS domain_name,
            COALESCE(d.namespace, 'global') AS domain_namespace,
            m.memory_type,
            m.importance,
            m.stability,
            m.created_at,
            s.source
        FROM memories m
        LEFT JOIN domains d ON d.id = m.domain_id
        LEFT JOIN memory_sources s ON s.memory_id = m.id
        WHERE m.deprecated=0
          {namespace_filter}
        ORDER BY m.domain_id, m.created_at
        """,
        namespace_params,
    ).fetchall()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        memory_id = row["id"]
        if memory_id in protected:
            continue
        if looks_like_correction(row["text"]) or looks_like_summary(row["text"]):
            protected.add(memory_id)
            continue
        domain_key = row["domain_id"] or "unknown"
        grouped[domain_key].append(
            {
                "memory_id": memory_id,
                "domain_id": row["domain_id"],
                "domain_name": row["domain_name"] or "general",
                "namespace": normalize_namespace(row["namespace"]),
                "domain_namespace": normalize_namespace(row["domain_namespace"]),
                "memory_type": row["memory_type"],
                "importance": float(row["importance"] or 0.0),
                "stability": float(row["stability"] or 0.0),
                "source": row["source"],
                "text_preview": str(row["text"] or "")[:220],
            }
        )

    groups = []
    for domain_id, candidates in grouped.items():
        if len(candidates) < max(1, int(min_domain_memories)):
            continue
        candidates = sorted(
            candidates,
            key=lambda item: (item["stability"], item["importance"], item["memory_id"]),
            reverse=True,
        )[: max(1, int(max_candidates_per_domain))]
        groups.append(
            {
                "domain_id": domain_id,
                "domain_name": candidates[0]["domain_name"],
                "namespace": candidates[0]["namespace"],
                "domain_namespace": candidates[0]["domain_namespace"],
                "candidate_count": len(candidates),
                "memory_ids": [item["memory_id"] for item in candidates],
                "candidates": candidates,
                "action": "dry_run_only",
            }
        )

    return {
        "ok": True,
        "mode": "plan",
        "namespace": normalize_namespace(namespace) if namespace is not None else None,
        "include_global": bool(include_global),
        "namespace_scope": namespaces,
        "protected_memory_ids": sorted(protected),
        "protected_count": len(protected),
        "candidate_group_count": len(groups),
        "candidate_groups": groups,
    }


def protected_memory_ids(db: MemoryDB, namespaces: list[str] | None = None) -> set[str]:
    relation_types = tuple(sorted(PROTECTIVE_RELATIONS | CONSOLIDATION_RELATIONS))
    placeholders = ",".join("?" for _ in relation_types)
    namespace_filter, namespace_params = relation_namespace_filter(namespaces)
    relation_sql = f"""
        SELECT DISTINCT r.source_memory_id, r.target_memory_id, r.relation_type
        FROM relations r
        LEFT JOIN memories sm ON sm.id = r.source_memory_id
        LEFT JOIN memories tm ON tm.id = r.target_memory_id
        WHERE r.relation_type IN ({placeholders})
          {namespace_filter}
        """
    rows = db.conn.execute(
        relation_sql,
        relation_types + tuple(namespace_params),
    ).fetchall()
    protected = set()
    for row in rows:
        protected.add(row["source_memory_id"])
        protected.add(row["target_memory_id"])

    feedback_rows = db.conn.execute(
        f"""
        SELECT f.memory_id
        FROM retrieval_feedback f
        JOIN memories m ON m.id = f.memory_id
        WHERE 1=1
          {sql_namespace_filter("m", namespaces)[0]}
        GROUP BY f.memory_id
        HAVING AVG(rating) < 0
        """,
        sql_namespace_filter("m", namespaces)[1],
    ).fetchall()
    protected.update(row["memory_id"] for row in feedback_rows)
    return {memory_id for memory_id in protected if memory_id}


def looks_like_correction(text: str | None) -> bool:
    lower = str(text or "").lower()
    return any(
        marker in lower
        for marker in (
            "correction:",
            "supersedes",
            "no longer current",
            "stale",
            "must not",
            "should not",
        )
    )


def looks_like_summary(text: str | None) -> bool:
    lower = str(text or "").lower()
    return lower.startswith("consolidated summary:") or "source memory ids:" in lower


def create_consolidation_summaries(
    pipeline: Any,
    min_domain_memories: int = 4,
    max_candidates_per_domain: int = 8,
    max_groups: int | None = None,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    plan = consolidation_plan(
        pipeline.db,
        min_domain_memories=min_domain_memories,
        max_candidates_per_domain=max_candidates_per_domain,
        namespace=namespace,
        include_global=include_global,
    )
    created = []
    groups = plan["candidate_groups"]
    if max_groups is not None:
        groups = groups[: max(0, int(max_groups))]
    for group in groups:
        summary_text = build_summary_text(group)
        source = f"consolidation:{group['domain_name']}"
        summary_namespace = normalize_namespace(group.get("namespace"))
        result = pipeline.ingest(summary_text, source=source, namespace=summary_namespace)
        summary_id = result["memory_id"]
        pipeline.db.set_memory_source(
            summary_id,
            source,
            0,
            metadata={
                "consolidation": True,
                "domain_id": group["domain_id"],
                "domain_name": group["domain_name"],
                "namespace": summary_namespace,
                "source_memory_ids": group["memory_ids"],
            },
        )
        for memory_id in group["memory_ids"]:
            pipeline.db.add_relation(summary_id, memory_id, "summarizes", 1.0)
        pipeline.db.add_event(
            summary_id,
            "consolidate",
            metadata={
                "domain_id": group["domain_id"],
                "domain_name": group["domain_name"],
                "namespace": summary_namespace,
                "source_memory_ids": group["memory_ids"],
            },
        )
        created.append(
            {
                "summary_memory_id": summary_id,
                "domain_id": group["domain_id"],
                "domain_name": group["domain_name"],
                "namespace": summary_namespace,
                "source_memory_ids": group["memory_ids"],
                "source": source,
            }
        )
    return {
        "ok": True,
        "mode": "create_summaries",
        "created": len(created),
        "created_summaries": created,
        "plan": plan,
    }


def build_summary_text(group: dict[str, Any]) -> str:
    lines = [
        f"Consolidated summary: {group['domain_name']}",
        "This summary preserves stable compatible memories without replacing the original evidence.",
        "Key memory points:",
    ]
    for item in group.get("candidates", []):
        text = str(item.get("text_preview") or "").strip()
        if not text:
            continue
        lines.append(f"- {text}")
    memory_ids = ", ".join(group.get("memory_ids", []))
    lines.append(f"Source memory ids: {memory_ids}")
    return "\n".join(lines)


def maybe_consolidate(db: MemoryDB | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Return a safe consolidation plan.

    Automatic summarization remains disabled until safety evals are stronger.
    """

    if db is None:
        return {"created": 0, "mode": "disabled", "reason": "no_database_supplied"}
    plan = consolidation_plan(db)
    if dry_run:
        return {**plan, "created": 0, "mode": "dry_run"}
    return {
        **plan,
        "mode": "disabled",
        "created": 0,
        "reason": "write_consolidation_not_enabled",
    }


def namespace_scope(namespace: str | None, include_global: bool = False) -> list[str] | None:
    if namespace is None:
        return None
    normalized = normalize_namespace(namespace)
    if include_global and normalized != "global":
        return ["global", normalized]
    return [normalized]


def sql_namespace_filter(alias: str, namespaces: list[str] | None) -> tuple[str, list[Any]]:
    normalized = normalize_namespaces(namespaces)
    if normalized is None:
        return "", []
    placeholders = ",".join("?" for _ in normalized)
    return f"AND COALESCE({alias}.namespace, 'global') IN ({placeholders})", list(normalized)


def relation_namespace_filter(namespaces: list[str] | None) -> tuple[str, list[Any]]:
    normalized = normalize_namespaces(namespaces)
    if normalized is None:
        return "", []
    placeholders = ",".join("?" for _ in normalized)
    return (
        f"""AND (
            COALESCE(sm.namespace, 'global') IN ({placeholders})
            OR COALESCE(tm.namespace, 'global') IN ({placeholders})
        )""",
        list(normalized) + list(normalized),
    )
