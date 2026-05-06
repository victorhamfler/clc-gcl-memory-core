from __future__ import annotations

from typing import Any

from core.consolidation import consolidation_plan, namespace_scope, sql_namespace_filter
from storage.db import normalize_namespace


def memory_review(
    db: Any,
    weak_limit: int = 8,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    stats = db.stats()
    namespaces = namespace_scope(namespace, include_global=include_global)
    domain_health = domain_health_report(db, namespace=namespace, include_global=include_global)
    domains = domain_health["domains"]
    weak = weak_memories(db, limit=weak_limit, namespace=namespace, include_global=include_global)
    consolidation = consolidation_plan(db, namespace=namespace, include_global=include_global)
    recommendations = review_recommendations(stats, domains, weak, consolidation)
    return {
        "ok": True,
        "namespace": normalize_namespace(namespace) if namespace is not None else None,
        "include_global": bool(include_global),
        "namespace_scope": namespaces,
        "stats": stats,
        "domains": domains,
        "domain_health": domain_health,
        "weak_memories": weak,
        "consolidation": {
            "candidate_group_count": consolidation["candidate_group_count"],
            "protected_count": consolidation["protected_count"],
            "candidate_groups": consolidation["candidate_groups"][:5],
        },
        "recommendations": recommendations,
    }


def weak_memories(
    db: Any,
    limit: int = 10,
    include_resolved: bool = False,
    namespace: str | None = None,
    include_global: bool = False,
) -> list[dict[str, Any]]:
    namespaces = namespace_scope(namespace, include_global=include_global)
    namespace_filter, namespace_params = sql_namespace_filter("m", namespaces)
    rows = db.conn.execute(
        f"""
        SELECT
            m.id,
            m.text,
            m.domain_id,
            COALESCE(m.namespace, 'global') AS namespace,
            d.name AS domain_name,
            m.memory_type,
            m.importance,
            m.stability,
            m.confidence,
            m.csd_score,
            m.surprise,
            m.recall_score,
            m.clc_state,
            m.created_at,
            s.source,
            COALESCE(f.count, 0) AS feedback_count,
            COALESCE(f.avg_rating, 0.0) AS avg_feedback,
            COALESCE(f.negative, 0) AS negative_feedback,
            COALESCE(r.relation_count, 0) AS relation_count,
            COALESCE(res.resolution_count, 0) AS resolution_count,
            COALESCE(outres.outgoing_resolution_count, 0) AS outgoing_resolution_count,
            COALESCE(c.contradiction_count, 0) AS contradiction_count
        FROM memories m
        LEFT JOIN domains d ON d.id = m.domain_id
        LEFT JOIN memory_sources s ON s.memory_id = m.id
        LEFT JOIN (
            SELECT memory_id, COUNT(*) AS count, AVG(rating) AS avg_rating,
                   SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) AS negative
            FROM retrieval_feedback
            GROUP BY memory_id
        ) f ON f.memory_id = m.id
        LEFT JOIN (
            SELECT memory_id, COUNT(*) AS relation_count
            FROM (
                SELECT source_memory_id AS memory_id FROM relations
                UNION ALL
                SELECT target_memory_id AS memory_id FROM relations
            )
            GROUP BY memory_id
        ) r ON r.memory_id = m.id
        LEFT JOIN (
            SELECT target_memory_id AS memory_id, COUNT(*) AS resolution_count
            FROM relations
            WHERE relation_type IN ('updates', 'corrects', 'supersedes')
            GROUP BY target_memory_id
        ) res ON res.memory_id = m.id
        LEFT JOIN (
            SELECT source_memory_id AS memory_id, COUNT(*) AS outgoing_resolution_count
            FROM relations
            WHERE relation_type IN ('updates', 'corrects', 'supersedes')
            GROUP BY source_memory_id
        ) outres ON outres.memory_id = m.id
        LEFT JOIN (
            SELECT memory_id, COUNT(*) AS contradiction_count
            FROM (
                SELECT new_memory_id AS memory_id FROM contradictions
                UNION ALL
                SELECT old_memory_id AS memory_id FROM contradictions
            )
            GROUP BY memory_id
        ) c ON c.memory_id = m.id
        WHERE m.deprecated=0
          {namespace_filter}
        ORDER BY m.created_at DESC
        """,
        namespace_params,
    ).fetchall()
    ranked = []
    for row in rows:
        item = memory_weakness(row)
        if item["resolved"] and not include_resolved:
            continue
        if item["weakness_score"] > 0.0:
            ranked.append(item)
    ranked.sort(key=lambda item: (item["weakness_score"], item["created_at"] or ""), reverse=True)
    return ranked[: max(1, int(limit))]


def memory_weakness(row: Any) -> dict[str, Any]:
    confidence = float(row["confidence"] or 0.0)
    stability = float(row["stability"] or 0.0)
    csd_score = float(row["csd_score"] or 0.0)
    surprise = float(row["surprise"] or 0.0)
    recall = float(row["recall_score"] or 0.0)
    avg_feedback = float(row["avg_feedback"] or 0.0)
    negative_feedback = int(row["negative_feedback"] or 0)
    relation_count = int(row["relation_count"] or 0)
    resolution_count = int(row["resolution_count"] or 0)
    outgoing_resolution_count = int(row["outgoing_resolution_count"] or 0)
    contradiction_count = int(row["contradiction_count"] or 0)
    reasons = []
    score = 0.0
    if not row["source"]:
        score += 0.20
        reasons.append("missing_source")
    if confidence < 0.45:
        score += 0.20
        reasons.append("low_confidence")
    if stability < 0.05 and recall < 0.40:
        score += 0.12
        reasons.append("low_stability_low_recall")
    if csd_score > 0.85 or surprise > 0.85:
        score += 0.18
        reasons.append("high_novelty_or_surprise")
    if negative_feedback > 0 or avg_feedback < -0.2:
        score += 0.30
        reasons.append("negative_feedback")
    if contradiction_count > 0:
        score += 0.25
        reasons.append("contradiction_chain")
    if relation_count == 0 and str(row["clc_state"] or "") in {"PROTECT", "SPLIT_DOMAIN"}:
        score += 0.12
        reasons.append("unlinked_important_state")
    resolved = resolution_count > 0
    if resolved:
        reasons.append("resolved_by_update")
        score = min(score, 0.05)
    linked_resolution = outgoing_resolution_count > 0
    if (
        linked_resolution
        and row["source"]
        and negative_feedback <= 0
        and not resolved
    ):
        reasons.append("linked_resolution_update")
        score = 0.0
    return {
        "memory_id": row["id"],
        "namespace": normalize_namespace(row["namespace"]),
        "domain_name": row["domain_name"],
        "memory_type": row["memory_type"],
        "source": row["source"],
        "clc_state": row["clc_state"],
        "confidence": round(confidence, 6),
        "stability": round(stability, 6),
        "csd_score": round(csd_score, 6),
        "surprise": round(surprise, 6),
        "recall": round(recall, 6),
        "feedback_count": int(row["feedback_count"] or 0),
        "avg_feedback": round(avg_feedback, 6),
        "relation_count": relation_count,
        "resolution_count": resolution_count,
        "outgoing_resolution_count": outgoing_resolution_count,
        "contradiction_count": contradiction_count,
        "weakness_score": round(min(1.0, score), 6),
        "reasons": reasons,
        "resolved": resolved,
        "recommended_action": recommended_action(reasons),
        "text_preview": str(row["text"] or "")[:260],
        "created_at": row["created_at"],
    }


def recommended_action(reasons: list[str]) -> str:
    if "negative_feedback" in reasons or "contradiction_chain" in reasons:
        return "review_or_correct"
    if "missing_source" in reasons:
        return "attach_source_or_reteach"
    if "high_novelty_or_surprise" in reasons:
        return "verify_domain_and_examples"
    if "unlinked_important_state" in reasons:
        return "link_with_correction_or_summary"
    return "monitor"


def domain_health_flags(domain: Any) -> list[str]:
    flags = []
    if int(domain.memory_count or 0) <= 1:
        flags.append("sparse")
    if float(domain.curvature_ema or 0.0) > 0.35:
        flags.append("high_curvature")
    if float(domain.drift_ema or 0.0) > 0.25:
        flags.append("high_drift")
    if float(domain.effective_dimension or 1.0) > 64.0 and int(domain.memory_count or 0) < 8:
        flags.append("high_dimension_low_samples")
    return flags


def domain_health_report(
    db: Any,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    namespaces = namespace_scope(namespace, include_global=include_global)
    domains = [domain_health_entry(db, domain) for domain in db.list_domains(namespaces=namespaces)]
    actions: dict[str, int] = {}
    for domain in domains:
        action = domain["recommended_action"]
        actions[action] = actions.get(action, 0) + 1
    return {
        "ok": True,
        "namespace": normalize_namespace(namespace) if namespace is not None else None,
        "include_global": bool(include_global),
        "namespace_scope": namespaces,
        "domain_count": len(domains),
        "actions": actions,
        "domains": domains,
        "recommendations": domain_health_recommendations(domains),
    }


def domain_health_entry(db: Any, domain: Any) -> dict[str, Any]:
    counters = domain_counters(db, domain.id)
    flags = domain_health_flags(domain)
    action = domain_health_action(domain, counters, flags)
    return {
        "id": domain.id,
        "name": domain.name,
        "namespace": domain.namespace,
        "memory_count": int(domain.memory_count or 0),
        "effective_dimension": round(float(domain.effective_dimension or 0.0), 4),
        "drift_ema": round(float(domain.drift_ema or 0.0), 6),
        "curvature_ema": round(float(domain.curvature_ema or 0.0), 6),
        "stability": round(float(domain.stability or 0.0), 6),
        "health_flags": flags,
        "protected_count": counters["protected_count"],
        "contradiction_count": counters["contradiction_count"],
        "correction_relation_count": counters["correction_relation_count"],
        "update_relation_count": counters["update_relation_count"],
        "namespace_count": counters["namespace_count"],
        "recommended_action": action,
        "recommendation": domain_action_text(action),
    }


def domain_counters(db: Any, domain_id: str | None) -> dict[str, int]:
    if not domain_id:
        return {
            "protected_count": 0,
            "contradiction_count": 0,
            "correction_relation_count": 0,
            "update_relation_count": 0,
            "namespace_count": 0,
        }
    row = db.conn.execute(
        """
        SELECT
            SUM(CASE WHEN clc_state='PROTECT' THEN 1 ELSE 0 END) AS protected_count,
            COUNT(DISTINCT namespace) AS namespace_count
        FROM memories
        WHERE deprecated=0 AND domain_id=?
        """,
        (domain_id,),
    ).fetchone()
    contradiction_row = db.conn.execute(
        """
        SELECT COUNT(DISTINCT c.id) AS count
        FROM contradictions c
        JOIN memories m ON m.id IN (c.new_memory_id, c.old_memory_id)
        WHERE m.domain_id=? AND m.deprecated=0
        """,
        (domain_id,),
    ).fetchone()
    relation_row = db.conn.execute(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN relation_type='corrects' THEN r.id END) AS correction_count,
            COUNT(DISTINCT CASE WHEN relation_type='updates' THEN r.id END) AS update_count
        FROM relations r
        JOIN memories m ON m.id=r.source_memory_id OR m.id=r.target_memory_id
        WHERE m.domain_id=? AND m.deprecated=0
        """,
        (domain_id,),
    ).fetchone()
    return {
        "protected_count": int((row["protected_count"] if row else 0) or 0),
        "namespace_count": int((row["namespace_count"] if row else 0) or 0),
        "contradiction_count": int((contradiction_row["count"] if contradiction_row else 0) or 0),
        "correction_relation_count": int((relation_row["correction_count"] if relation_row else 0) or 0),
        "update_relation_count": int((relation_row["update_count"] if relation_row else 0) or 0),
    }


def domain_health_action(domain: Any, counters: dict[str, int], flags: list[str]) -> str:
    memory_count = int(domain.memory_count or 0)
    drift = float(domain.drift_ema or 0.0)
    curvature = float(domain.curvature_ema or 0.0)
    stability = float(domain.stability or 0.0)
    if counters["contradiction_count"] > 0 or counters["protected_count"] > 0:
        return "protect_and_review"
    if "sparse" in flags:
        return "seed_or_merge"
    if curvature > 0.35 or drift > 0.25:
        return "split_or_reanchor"
    if memory_count >= 6 and stability >= 0.08 and curvature < 0.25 and drift < 0.20:
        return "consolidate"
    if "high_dimension_low_samples" in flags:
        return "add_examples"
    return "monitor"


def domain_action_text(action: str) -> str:
    if action == "protect_and_review":
        return "Review protected/corrected memories before letting anchor updates reshape this domain."
    if action == "seed_or_merge":
        return "Add more examples or merge this sparse domain with a better-supported neighbor."
    if action == "split_or_reanchor":
        return "Inspect high drift or curvature; split mixed topics or rebuild the anchor from current memories."
    if action == "consolidate":
        return "Create a source-linked summary because this domain is stable enough to compress."
    if action == "add_examples":
        return "Add representative examples before trusting high-dimensional geometry."
    return "Keep monitoring this domain."


def domain_health_recommendations(domains: list[dict[str, Any]]) -> list[str]:
    if not domains:
        return ["seed_initial_domains"]
    actions = {domain["recommended_action"] for domain in domains}
    out = []
    for action in ("protect_and_review", "split_or_reanchor", "consolidate", "seed_or_merge", "add_examples"):
        if action in actions:
            out.append(action)
    if not out:
        out.append("domain_health_ok")
    return out


def review_recommendations(
    stats: dict[str, Any],
    domains: list[dict[str, Any]],
    weak: list[dict[str, Any]],
    consolidation: dict[str, Any],
) -> list[str]:
    out = []
    if weak:
        out.append("review_weak_memories")
    if consolidation.get("candidate_group_count", 0) > 0:
        out.append("consider_safe_consolidation")
    if any(domain["health_flags"] for domain in domains):
        out.append("inspect_domain_health")
    if any(int(domain.get("contradiction_count") or 0) > 0 for domain in domains):
        out.append("verify_protected_contradictions")
    if not out:
        out.append("memory_health_ok")
    return out


def improvement_plan(
    db: Any,
    memory_id: str | None = None,
    limit: int = 5,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    weak = weak_memories(db, limit=max(1, int(limit)), namespace=namespace, include_global=include_global)
    if memory_id:
        selected = [item for item in weak if item["memory_id"] == memory_id]
        if not selected:
            selected = [describe_memory_for_improvement(db, memory_id, namespace=namespace, include_global=include_global)]
    else:
        selected = weak[: max(1, int(limit))]
    return {
        "ok": True,
        "mode": "plan",
        "namespace": normalize_namespace(namespace) if namespace is not None else None,
        "include_global": bool(include_global),
        "items": selected,
        "suggested_next_steps": [suggested_improvement_text(item) for item in selected if item],
    }


def describe_memory_for_improvement(
    db: Any,
    memory_id: str,
    namespace: str | None = None,
    include_global: bool = False,
) -> dict[str, Any]:
    namespaces = namespace_scope(namespace, include_global=include_global)
    namespace_filter, namespace_params = sql_namespace_filter("m", namespaces)
    row = db.conn.execute(
        f"""
        SELECT m.*, COALESCE(m.namespace, 'global') AS namespace, d.name AS domain_name, s.source
        FROM memories m
        LEFT JOIN domains d ON d.id = m.domain_id
        LEFT JOIN memory_sources s ON s.memory_id = m.id
        WHERE m.id=? AND m.deprecated=0
          {namespace_filter}
        """,
        [memory_id, *namespace_params],
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown memory_id: {memory_id}")
    return {
        "memory_id": row["id"],
        "namespace": normalize_namespace(row["namespace"]),
        "domain_name": row["domain_name"],
        "memory_type": row["memory_type"],
        "source": row["source"],
        "clc_state": row["clc_state"],
        "weakness_score": 0.0,
        "reasons": [],
        "recommended_action": "add_clarifying_update",
        "text_preview": str(row["text"] or "")[:260],
        "created_at": row["created_at"],
    }


def suggested_improvement_text(item: dict[str, Any]) -> str:
    memory_id = item.get("memory_id")
    action = item.get("recommended_action")
    if action == "review_or_correct":
        return f"{memory_id}: verify whether this memory is current; add /correct if stale."
    if action == "attach_source_or_reteach":
        return f"{memory_id}: reteach with a clear source label or provenance note."
    if action == "verify_domain_and_examples":
        return f"{memory_id}: add examples or a domain-specific clarification."
    if action == "link_with_correction_or_summary":
        return f"{memory_id}: link it through correction/update or include it in consolidation."
    return f"{memory_id}: monitor or add clarifying context if retrieval is weak."


def record_memory_improvement(
    pipeline: Any,
    memory_id: str,
    note: str,
    agent_id: str = "default",
    session_id: str | None = None,
    namespace: str | None = None,
) -> dict[str, Any]:
    target = describe_memory_for_improvement(pipeline.db, memory_id, namespace=namespace)
    cleaned = str(note or "").strip()
    if not cleaned:
        raise ValueError("improvement note is required")
    text = (
        f"Memory improvement for {memory_id}: {cleaned}\n"
        f"Original memory preview: {target['text_preview']}"
    )
    result = pipeline.teach(
        text,
        source=f"maintenance:{agent_id}",
        session_id=session_id,
        agent_id=agent_id,
        store_session=bool(session_id),
        metadata={"maintenance": True, "target_memory_id": memory_id},
        namespace=namespace,
    )
    improvement_id = result["memory"]["memory_id"]
    pipeline.db.add_relation(improvement_id, memory_id, "updates", 1.0)
    pipeline.db.add_event(
        improvement_id,
        "memory_improvement",
        metadata={"target_memory_id": memory_id, "agent_id": agent_id, "session_id": session_id},
    )
    return {
        "ok": True,
        "mode": "improve",
        "target_memory": target,
        "improvement_memory": result["memory"],
        "relation": {
            "source_memory_id": improvement_id,
            "target_memory_id": memory_id,
            "relation_type": "updates",
        },
    }
