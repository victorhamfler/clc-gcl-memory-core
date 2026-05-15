from __future__ import annotations

import time
from typing import Any

from core.chunking import chunk_text
from core.llm_client import LLMClientError, OpenAICompatibleLLMClient
from storage.db import normalize_namespace


VALID_MEMORY_TYPES = {"preference", "design_rule", "procedure", "semantic_note", "error_memory"}
VALID_MODES = {"dry_run", "extract_only", "extract_and_store"}
MODE_ALIASES = {"teach": "extract_and_store", "store": "extract_and_store", "store_facts": "extract_and_store"}


def learn_from_text(
    pipeline,
    text: str,
    llm_config: dict[str, Any] | None,
    namespace: str | None = None,
    agent_id: str = "default",
    session_id: str | None = None,
    source: str | None = None,
    mode: str = "dry_run",
    filters: dict[str, Any] | None = None,
    mock_facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = normalize_llm_config(llm_config)
    if not cfg.get("enabled"):
        return {"ok": False, "error": "LLM backend disabled", "mode": mode}
    learn_mode = normalize_learn_mode(mode)
    if learn_mode not in VALID_MODES:
        raise ValueError(
            f"unsupported learn mode: {mode}. Use one of dry_run, extract_only, extract_and_store; "
            "teach is accepted as an alias for extract_and_store."
        )
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("POST /learn requires JSON field 'text'")
    if mock_facts is not None:
        cfg["provider"] = "mock"
        cfg["mock_facts"] = mock_facts
    prompt = build_extraction_prompt(cleaned, cfg)
    client = OpenAICompatibleLLMClient(cfg)
    extracted = client.extract_facts(cleaned, prompt)
    candidates = normalize_candidates(extracted, cfg, filters or {})
    memory_namespace = normalize_namespace(namespace)
    results: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates):
        results.append(
            route_candidate(
                pipeline,
                candidate,
                idx=idx,
                mode=learn_mode,
                namespace=memory_namespace,
                agent_id=agent_id,
                session_id=session_id,
                source=source or f"learn:{agent_id}",
                cfg=cfg,
            )
        )
    stored = [item for item in results if item.get("action") in {"teach", "correct"} and item.get("memory_id")]
    skipped = [item for item in results if item.get("action") == "skip"]
    errors = [item for item in results if item.get("action") == "error"]
    pipeline.db.add_event(
        None,
        "learn",
        metadata={
            "agent_id": agent_id,
            "session_id": session_id,
            "namespace": memory_namespace,
            "mode": learn_mode,
            "facts_extracted": len(candidates),
            "facts_stored": len(stored),
            "facts_skipped": len(skipped),
            "facts_errors": len(errors),
            "source": source,
            "llm_usage": client.last_usage,
            "llm_model": client.last_model,
        },
    )
    return {
        "ok": not errors,
        "mode": learn_mode,
        "warning": dry_run_warning(learn_mode),
        "namespace": memory_namespace,
        "agent_id": agent_id,
        "session_id": session_id,
        "facts_extracted": len(candidates),
        "facts_stored": len(stored),
        "facts_skipped": len(skipped),
        "facts_errors": len(errors),
        "llm_usage": client.last_usage,
        "llm_model": client.last_model,
        "results": results,
    }


def learn_from_document(
    pipeline,
    title: str,
    content: str,
    llm_config: dict[str, Any] | None,
    namespace: str | None = None,
    agent_id: str = "default",
    session_id: str | None = None,
    source: str | None = None,
    mode: str = "dry_run",
    filters: dict[str, Any] | None = None,
    max_words: int = 350,
    overlap_words: int = 40,
    limit: int | None = None,
) -> dict[str, Any]:
    cfg = normalize_llm_config(llm_config)
    cleaned = str(content or "").strip()
    if not cleaned:
        raise ValueError("POST /learn/document requires JSON field 'content'")
    chunks = chunk_text(cleaned, max_words=max(20, int(max_words)), overlap_words=max(0, int(overlap_words)))
    if limit is not None:
        chunks = chunks[: max(0, int(limit))]
    document_source = source or f"learn_document:{str(title or 'document').strip() or 'document'}"
    results: list[dict[str, Any]] = []
    usage: list[dict[str, Any]] = []
    models_used: list[str | None] = []
    provider = str(cfg.get("provider") or "custom").strip().lower()
    chunk_delay = _float_config(cfg, "chunk_delay", 0.0 if provider == "mock" else 1.5)
    continue_on_error = _bool_config(cfg, "continue_on_error", True)
    for idx, chunk in enumerate(chunks):
        if idx > 0 and chunk_delay > 0:
            time.sleep(chunk_delay)
        try:
            learned = learn_from_text(
                pipeline,
                chunk,
                cfg,
                namespace=namespace,
                agent_id=agent_id,
                session_id=session_id,
                source=document_source,
                mode=mode,
                filters=filters,
            )
        except LLMClientError as exc:
            results.append(
                {
                    "index": 0,
                    "chunk_index": idx,
                    "fact": None,
                    "memory_type": None,
                    "confidence": None,
                    "correction": False,
                    "entities": [],
                    "action": "error",
                    "reason": str(exc),
                }
            )
            usage.append({})
            models_used.append(None)
            if continue_on_error:
                continue
            break
        usage.append(learned.get("llm_usage") or {})
        models_used.append(learned.get("llm_model"))
        for item in learned.get("results") or []:
            row = dict(item)
            row["chunk_index"] = idx
            results.append(row)
    stored = [item for item in results if item.get("action") in {"teach", "correct"} and item.get("memory_id")]
    skipped = [item for item in results if item.get("action") == "skip"]
    errors = [item for item in results if item.get("action") == "error"]
    return {
        "ok": not errors,
        "mode": normalize_learn_mode(mode),
        "warning": dry_run_warning(normalize_learn_mode(mode)),
        "title": str(title or "").strip() or None,
        "source": document_source,
        "namespace": normalize_namespace(namespace),
        "agent_id": agent_id,
        "session_id": session_id,
        "chunks_processed": len(chunks),
        "chunk_delay_sec": chunk_delay,
        "continue_on_error": continue_on_error,
        "facts_extracted": len(results),
        "facts_stored": len(stored),
        "facts_skipped": len(skipped),
        "facts_errors": len(errors),
        "llm_usage_by_chunk": usage,
        "llm_models_by_chunk": models_used,
        "results": results,
    }


def normalize_llm_config(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(config or {})
    cfg.setdefault("enabled", False)
    cfg.setdefault("provider", "custom")
    cfg.setdefault("temperature", 0.1)
    cfg.setdefault("max_tokens", 2048)
    cfg.setdefault("timeout", 30)
    cfg.setdefault("user_agent", "CLC-GCL-Memory/1.0")
    cfg.setdefault("max_retries", 2)
    cfg.setdefault("retry_backoff", 1.5)
    cfg.setdefault("chunk_delay", 1.5)
    cfg.setdefault("continue_on_error", True)
    cfg.setdefault("max_facts_per_call", 5)
    cfg.setdefault("min_fact_length", 15)
    cfg.setdefault("duplicate_threshold", 0.85)
    cfg.setdefault("correction_threshold", 0.60)
    cfg.setdefault("min_confidence", 0.70)
    return cfg


def normalize_learn_mode(mode: str | None) -> str:
    raw = str(mode or "dry_run").strip().lower() or "dry_run"
    return MODE_ALIASES.get(raw, raw)


def dry_run_warning(mode: str) -> str | None:
    if mode == "dry_run":
        return "mode=dry_run: extracted facts were previewed only. Set mode='extract_and_store' to persist them."
    if mode == "extract_only":
        return "mode=extract_only: extracted facts were routed for inspection only. Set mode='extract_and_store' to persist them."
    return None


def build_extraction_prompt(text: str, cfg: dict[str, Any]) -> str:
    max_facts = int(cfg.get("max_facts_per_call") or 5)
    return (
        "You are a precise fact extraction engine for an AI agent memory system.\n"
        "Extract only concrete long-term facts, preferences, procedures, and durable rules.\n"
        "Do not extract filler, jokes, hypotheticals, temporary states, or raw tool output.\n"
        "Classify each fact as one of: preference, design_rule, procedure, semantic_note, error_memory.\n"
        f"Return at most {max_facts} items.\n"
        "Return only valid JSON in this exact shape:\n"
        "[{\"fact\":\"...\",\"type\":\"preference|design_rule|procedure|semantic_note|error_memory\","
        "\"confidence\":0.0,\"correction\":false,\"entities\":[\"...\"]}]\n\n"
        "Text to analyze:\n---\n"
        f"{text}\n"
        "---"
    )


def normalize_candidates(
    facts: list[dict[str, Any]],
    cfg: dict[str, Any],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    max_facts = max(1, int(cfg.get("max_facts_per_call") or 5))
    min_length = max(0, int(cfg.get("min_fact_length") or 15))
    min_confidence = float(filters.get("min_confidence") if filters.get("min_confidence") is not None else cfg.get("min_confidence"))
    allowed = filters.get("memory_types")
    allowed_types = {str(item).strip() for item in allowed} if isinstance(allowed, list) else None
    override_type = str(filters.get("memory_type") or "").strip()
    if override_type and override_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"unsupported memory_type override: {override_type}")
    override_domain = str(filters.get("domain") or filters.get("domain_name") or "").strip()
    out: list[dict[str, Any]] = []
    for item in facts:
        fact = str(item.get("fact") or item.get("text") or "").strip()
        if len(fact) < min_length:
            continue
        memory_type = override_type or str(item.get("type") or item.get("memory_type") or "semantic_note").strip()
        if memory_type == "fact":
            memory_type = "semantic_note"
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "semantic_note"
        if allowed_types and memory_type not in allowed_types:
            continue
        try:
            confidence = float(item.get("confidence") if item.get("confidence") is not None else 0.75)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < min_confidence:
            continue
        out.append(
            {
                "fact": fact,
                "memory_type": memory_type,
                "confidence": max(0.0, min(1.0, confidence)),
                "correction": bool(item.get("correction", False)),
                "entities": item.get("entities") if isinstance(item.get("entities"), list) else [],
                "domain": override_domain or str(item.get("domain") or item.get("domain_name") or "").strip() or None,
            }
        )
        if len(out) >= max_facts:
            break
    return out


def route_candidate(
    pipeline,
    candidate: dict[str, Any],
    idx: int,
    mode: str,
    namespace: str,
    agent_id: str,
    session_id: str | None,
    source: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    fact = str(candidate.get("fact") or "").strip()
    result: dict[str, Any] = {
        "index": idx,
        "fact": fact,
        "memory_type": candidate.get("memory_type"),
        "confidence": candidate.get("confidence"),
        "correction": candidate.get("correction"),
        "entities": candidate.get("entities") or [],
        "domain": candidate.get("domain"),
    }
    similar = pipeline.retrieve(fact, top_k=3, namespace=namespace, include_global=False)
    best = similar[0] if similar else None
    best_similarity = float(best.get("cosine") or 0.0) if best else 0.0
    result["similar_memory_id"] = best.get("memory_id") if best else None
    result["similarity"] = round(best_similarity, 6)
    result["similar_text_preview"] = str(best.get("text") or "")[:180] if best else None
    duplicate_threshold = _float_config(cfg, "duplicate_threshold", 0.85)
    correction_threshold = _float_config(cfg, "correction_threshold", 0.60)
    if best and best_similarity >= duplicate_threshold:
        result.update({"action": "skip", "reason": "near_duplicate"})
        return result
    should_correct = bool(candidate.get("correction")) and bool(best) and best_similarity >= correction_threshold
    if mode in {"dry_run", "extract_only"}:
        result.update(
            {
                "action": "correct" if should_correct else "teach",
                "dry_run": mode == "dry_run",
                "reason": "would_route_to_correct" if should_correct else "would_store_new_fact",
                "memory_id": None,
            }
        )
        return result
    try:
        metadata = {
            "learn": True,
            "llm_confidence": candidate.get("confidence"),
            "llm_memory_type": candidate.get("memory_type"),
            "llm_entities": candidate.get("entities") or [],
            "llm_domain": candidate.get("domain"),
            "similar_memory_id": best.get("memory_id") if best else None,
            "similarity": best_similarity,
        }
        if should_correct:
            stored = pipeline.correct(
                fact,
                target_memory_ids=[str(best["memory_id"])],
                target_query=fact,
                source=source,
                session_id=session_id,
                agent_id=agent_id,
                metadata=metadata,
                namespace=namespace,
                priority="high",
                domain=str(candidate.get("domain") or "").strip() or None,
                memory_type=str(candidate.get("memory_type") or "").strip() or None,
            )
            result.update(
                {
                    "action": "correct",
                    "memory_id": stored["correction_memory"]["memory_id"],
                    "linked_to": stored.get("target_memory_ids", []),
                    "reason": "llm_flagged_correction",
                }
            )
            return result
        stored = pipeline.teach(
            fact,
            source=source,
            session_id=session_id,
            agent_id=agent_id,
            metadata=metadata,
            namespace=namespace,
            priority="normal",
            domain=str(candidate.get("domain") or "").strip() or None,
            memory_type=str(candidate.get("memory_type") or "").strip() or None,
        )
        result.update(
            {
                "action": "teach",
                "memory_id": stored["memory"]["memory_id"],
                "reason": "new_fact",
            }
        )
        return result
    except Exception as exc:
        result.update({"action": "error", "reason": str(exc)})
        return result


def _float_config(cfg: dict[str, Any], key: str, default: float) -> float:
    value = cfg.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_config(cfg: dict[str, Any], key: str, default: bool) -> bool:
    value = cfg.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)
