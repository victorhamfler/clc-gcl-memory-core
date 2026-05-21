from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.clc_controller import CLCController, STATE_UPDATE_STRENGTH
from core.contradiction import store_contradiction_if_needed
from core.csd import CSDLayer
from core.encoder import build_encoder
from core.gcl_memory import GCLMemoryUpdater
from core.math_utils import cosine
from core.models import CLCDecision, MemoryNode, RecallItem
from core.recall import RecallEngine
from core.resolver import compact_evidence, resolve_answer
from core.symbolic import build_signal_packet
from storage.db import MemoryDB, new_id, normalize_namespace, utc_now


DEFAULT_RETRIEVAL_WEIGHTS = {
    "vector": 0.45,
    "importance": 0.08,
    "stability": 0.08,
    "domain": 0.08,
    "text": 0.10,
    "source": 0.12,
    "feedback": 0.08,
    "domain_reliability": 0.03,
    "source_reliability": 0.03,
    "supersession": 0.10,
    "relation_supersession": 0.10,
    "summary_relation": 0.08,
    "intent": 0.12,
    "correction_chain": 0.12,
    "claim_scope": 0.14,
    "answer_type": 0.16,
}
VALID_MEMORY_TYPES = {"preference", "design_rule", "procedure", "semantic_note", "error_memory"}

DEFAULT_INTENT_LABELS = {
    "work": ("working on", "work on", "project", "building", "developing", "development"),
    "presentation": (
        "information presented",
        "presented",
        "presentation",
        "transparency",
        "honesty",
        "source clarity",
        "sources",
        "vague authority",
        "conclusions without source",
    ),
    "food_drink": ("drink", "drinks", "coffee", "espresso", "tea", "eat", "eats", "pizza", "food"),
    "preference": ("preference", "prefer", "likes", "loves", "hates", "dislikes", "values", "wants"),
}

DEFAULT_CLAIM_SCOPE_STOPWORDS = (
    "about",
    "check",
    "checks",
    "current",
    "currently",
    "does",
    "for",
    "from",
    "help",
    "helps",
    "latest",
    "prefer",
    "prefers",
    "preference",
    "remember",
    "should",
    "that",
    "the",
    "use",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "victor",
    "hermes",
    "project",
)

DEFAULT_CLAIM_SCOPE_ALIASES = {
    "drink": ("drink", "water", "sparkling", "espresso", "tea", "coffee", "beverage"),
    "pizza": ("pizza", "cheese", "mushroom", "pepperoni"),
    "method": ("method", "tool", "url", "accuweather", "radar", "checks"),
    "codename": ("codename", "cedar", "alpha"),
    "status": ("status", "stable", "blocked", "ready"),
    "backend_port": ("backend", "port", "8765"),
    "github_upload": ("github", "upload", "uploads", "confirmation", "explicitly", "requested", "requests"),
    "calendar_change": ("calendar", "schedule", "change", "changing", "meeting", "events", "manual", "approval"),
    "gcl_curvature": ("gcl", "g-cl", "domain", "geometry", "anchor", "drift", "curvature", "stability"),
    "csd": ("csd", "novelty", "contradiction", "semantic", "density", "domain shift", "detect"),
    "deadline": ("deadline", "due", "friday", "deadline_report"),
}

DEFAULT_CLAIM_SCOPE_EXCLUDED_TERMS = {
    "method": ("filename",),
    "backend_port": ("host", "remain", "127", "local", "testing"),
    "github_upload": ("calendar", "schedule", "meeting"),
    "calendar_change": ("github", "upload", "uploads"),
    "gcl_curvature": ("csd", "backend", "port", "filename", "report"),
    "csd": ("gcl", "g-cl", "backend", "port", "filename", "report"),
    "deadline": ("owner", "owns", "mina", "filename", "file"),
}

DEFAULT_ANSWER_TYPE_RULES = {
    "owner_relation": {
        "query_terms": (
            "owner",
            "owners",
            "owns",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "positive_terms": (
            "owner",
            "owners",
            "owns",
            "owned",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "negative_terms": (
            "deadline",
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "query_requires_any": (),
        "positive_requires_any": (),
        "negative_requires_absent": (),
        "positive_score": 1.0,
        "negative_score": -1.0,
    },
    "deadline": {
        "query_terms": ("deadline", "due"),
        "positive_terms": (
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "negative_terms": (
            "owner",
            "owners",
            "owns",
            "owned",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "query_requires_any": (),
        "positive_requires_any": (),
        "negative_requires_absent": (
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "positive_score": 1.0,
        "negative_score": -1.0,
    },
}


def configured_intent_terms(symbolic_config: dict[str, Any] | None = None) -> dict[str, tuple[str, ...]]:
    configured = _parse_intent_labels((symbolic_config or {}).get("intent_labels"))
    out = dict(DEFAULT_INTENT_LABELS)
    out.update(configured)
    return out


def _parse_intent_labels(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        return {
            str(label).strip(): tuple(str(term).strip().lower() for term in terms if str(term).strip())
            for label, terms in value.items()
            if str(label).strip() and isinstance(terms, (list, tuple, set))
        }
    out: dict[str, tuple[str, ...]] = {}
    for group in str(value or "").split(";"):
        if "=" not in group:
            continue
        label, raw_terms = group.split("=", 1)
        terms = tuple(term.strip().lower() for term in raw_terms.split("|") if term.strip())
        if label.strip() and terms:
            out[label.strip()] = terms
    return out


def _parse_term_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(term).strip().lower() for term in value if str(term).strip())
    raw = str(value or "")
    for separator in ("|", ";"):
        raw = raw.replace(separator, ",")
    return tuple(term.strip().lower() for term in raw.split(",") if term.strip())


def _parse_term_map(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        return {
            str(label).strip().lower(): _parse_term_sequence(terms)
            for label, terms in value.items()
            if str(label).strip() and _parse_term_sequence(terms)
        }
    out: dict[str, tuple[str, ...]] = {}
    for group in str(value or "").split(";"):
        if "=" not in group:
            continue
        label, raw_terms = group.split("=", 1)
        terms = _parse_term_sequence(raw_terms.replace("|", ","))
        if label.strip() and terms:
            out[label.strip().lower()] = terms
    return out


def _normalize_claim_scope_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    stopwords = set(DEFAULT_CLAIM_SCOPE_STOPWORDS)
    stopwords.update(_parse_term_sequence(cfg.get("stopwords")))

    aliases = {key: tuple(values) for key, values in DEFAULT_CLAIM_SCOPE_ALIASES.items()}
    aliases.update(_parse_term_map(cfg.get("slot_aliases") or cfg.get("aliases")))

    excluded = {key: tuple(values) for key, values in DEFAULT_CLAIM_SCOPE_EXCLUDED_TERMS.items()}
    excluded.update(_parse_term_map(cfg.get("excluded_terms") or cfg.get("exclusions")))

    return {
        "stopwords": stopwords,
        "slot_aliases": aliases,
        "excluded_terms": excluded,
    }


def _parse_answer_type_rule_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for label, raw_rule in value.items():
        if not isinstance(raw_rule, dict) or not str(label).strip():
            continue
        out[str(label).strip().lower()] = raw_rule
    return out


def _normalize_answer_type_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    configured_rules = _parse_answer_type_rule_map(cfg.get("rules") or cfg)
    rules: dict[str, dict[str, Any]] = {}
    for label, defaults in DEFAULT_ANSWER_TYPE_RULES.items():
        raw_rule = dict(defaults)
        raw_rule.update(configured_rules.pop(label, {}))
        rules[label] = _normalize_answer_type_rule(raw_rule)
    for label, raw_rule in configured_rules.items():
        normalized = _normalize_answer_type_rule(raw_rule)
        if normalized["query_terms"] and (normalized["positive_terms"] or normalized["negative_terms"]):
            rules[label] = normalized
    return {"rules": rules}


def _normalize_answer_type_rule(raw_rule: dict[str, Any]) -> dict[str, Any]:
    positive_score = raw_rule.get("positive_score", 1.0)
    negative_score = raw_rule.get("negative_score", -1.0)
    try:
        positive_score = float(positive_score)
    except (TypeError, ValueError):
        positive_score = 1.0
    try:
        negative_score = float(negative_score)
    except (TypeError, ValueError):
        negative_score = -1.0
    return {
        "query_terms": _parse_term_sequence(raw_rule.get("query_terms")),
        "positive_terms": _parse_term_sequence(raw_rule.get("positive_terms")),
        "negative_terms": _parse_term_sequence(raw_rule.get("negative_terms")),
        "query_requires_any": _parse_term_sequence(raw_rule.get("query_requires_any")),
        "query_excludes_any": _parse_term_sequence(raw_rule.get("query_excludes_any")),
        "positive_requires_any": _parse_term_sequence(raw_rule.get("positive_requires_any")),
        "negative_requires_absent": _parse_term_sequence(raw_rule.get("negative_requires_absent")),
        "positive_score": positive_score,
        "negative_score": negative_score,
    }


class MemoryPipeline:
    def __init__(
        self,
        root: Path,
        db_path: Path,
        embedding_dim: int = 128,
        top_k: int = 8,
        embedding_config: dict[str, Any] | None = None,
        retrieval_weights: dict[str, Any] | None = None,
        symbolic_config: dict[str, Any] | None = None,
        claim_scope_config: dict[str, Any] | None = None,
        answer_type_config: dict[str, Any] | None = None,
        llm_config: dict[str, Any] | None = None,
        clc_thresholds: dict[str, Any] | None = None,
    ):
        self.root = root
        self.db = MemoryDB(db_path)
        self.encoder = build_encoder(embedding_config, default_dim=embedding_dim)
        self.retrieval_weights = self._normalize_retrieval_weights(retrieval_weights)
        self.symbolic_config = dict(symbolic_config or {})
        self.claim_scope_config = _normalize_claim_scope_config(claim_scope_config)
        self.answer_type_config = _normalize_answer_type_config(answer_type_config)
        self.llm_config = dict(llm_config or {})
        self.recall_engine = RecallEngine(self.db, top_k=top_k)
        self.csd = CSDLayer(self.db)
        self.controller = CLCController(clc_thresholds)
        self.gcl = GCLMemoryUpdater(self.db)
        self.log_path = root / "logs" / "memory_events.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        close_encoder = getattr(self.encoder, "close", None)
        if callable(close_encoder):
            close_encoder()
        self.db.close()

    def ingest(
        self,
        text: str,
        source: str | None = None,
        namespace: str | None = None,
        priority: str | None = None,
        force_clc_state: str | None = None,
        domain_text: str | None = None,
        prefer_symbolic_domain: bool = False,
        domain: str | None = None,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        memory_namespace = normalize_namespace(namespace)
        cleaned = str(text or "").strip()
        analysis_text = str(domain_text or cleaned).strip() or cleaned
        memory_priority = self._normalize_priority(priority)
        embedding = self.encoder.embed(text)
        embedding_signature = self._ensure_embedding_signature(embedding)
        signal = build_signal_packet(analysis_text, embedding, self.symbolic_config)
        self._apply_explicit_classification(signal, domain=domain, memory_type=memory_type)
        self._apply_priority(signal, memory_priority)
        self._apply_source_domain_hint(signal, source)
        recall = self.recall_engine.recall(
            embedding,
            namespaces=self._namespace_scope(memory_namespace),
            domain_namespaces=[memory_namespace],
        )
        diagnostics = self.csd.diagnose(signal, recall)
        signals = self.controller.compute_signals(signal, diagnostics, recall)
        decision = self.controller.decide(diagnostics, signals)
        decision = self._apply_clc_override(decision, memory_priority, force_clc_state)
        preferred_domain = self._preferred_domain(
            signal,
            recall.nearest_domain,
            memory_namespace,
            prefer_symbolic_domain=prefer_symbolic_domain,
        )
        update = self.gcl.apply(signal, decision, preferred_domain, namespace=memory_namespace)
        assigned_domain = self.db.get_domain(update.domain_id)
        now = utc_now()
        memory = MemoryNode(
            id=new_id("mem"),
            text=cleaned,
            embedding=embedding,
            domain_id=update.domain_id,
            memory_type=signal.memory_type,
            importance=signal.importance,
            stability=0.0,
            confidence=signal.confidence,
            csd_score=diagnostics.csd_semantic,
            surprise=signals.surprise,
            recall_score=signals.recall,
            curiosity=signals.curiosity,
            focus=signals.focus,
            clc_state=decision.state,
            created_at=now,
            updated_at=now,
            namespace=memory_namespace,
        )
        self.db.insert_memory(memory)
        if source:
            self.db.set_memory_source(
                memory.id,
                source,
                0,
                metadata={"namespace": memory_namespace, "priority": memory_priority},
            )
        store_contradiction_if_needed(self.db, memory.id, recall, diagnostics.contradiction)
        self.db.add_event(
            memory.id,
            "ingest",
            diagnostics.csd_semantic,
            {
                "clc_state": decision.state,
                "decision_reason": decision.reason,
                "gcl_action": update.action,
                "domains": signal.domains,
                "memory_type": signal.memory_type,
                "priority": memory_priority,
                "force_clc_state": force_clc_state,
                "domain_text_used": analysis_text != cleaned,
                "explicit_domain": domain,
                "explicit_memory_type": memory_type,
            },
        )
        result = {
            "memory_id": memory.id,
            "domain_id": update.domain_id,
            "domain_name": assigned_domain.name if assigned_domain else (signal.domains[0] if signal.domains else "general"),
            "memory_type": signal.memory_type,
            "namespace": memory_namespace,
            "priority": memory_priority,
            "clc_state": decision.state,
            "decision_reason": decision.reason,
            "csd_score": round(diagnostics.csd_semantic, 6),
            "csd_density": round(diagnostics.csd_density, 6),
            "contradiction": round(diagnostics.contradiction, 6),
            "surprise": round(signals.surprise, 6),
            "recall": round(signals.recall, 6),
            "curiosity": round(signals.curiosity, 6),
            "focus": round(signals.focus, 6),
            "gcl_action": update.action,
            "combined_drift": round(update.combined_drift, 6),
            "orthogonal_drift": round(update.orthogonal_drift, 6),
            "curvature": round(update.curvature, 6),
            "anchor_update_strength": round(update.anchor_update_strength, 6),
            "embedding_backend": embedding_signature["backend"],
            "embedding_model": embedding_signature["model_name"],
            "embedding_dim": embedding_signature["embedding_dim"],
        }
        self._append_log(result)
        return result

    def _preferred_domain(
        self,
        signal,
        nearest_domain,
        namespace: str | None = None,
        prefer_symbolic_domain: bool = False,
    ):
        memory_namespace = normalize_namespace(namespace)
        symbolic = signal.domains[0] if signal.domains else "general"
        if prefer_symbolic_domain:
            existing = self.db.get_domain_by_name(symbolic or "general", namespace=memory_namespace)
            return existing
        if symbolic and symbolic != "general":
            existing = self.db.get_domain_by_name(symbolic, namespace=memory_namespace)
            if existing is not None:
                return existing
            if nearest_domain is None or nearest_domain.name != symbolic or nearest_domain.namespace != memory_namespace:
                return None
        if nearest_domain is not None and nearest_domain.namespace != memory_namespace:
            return None
        return nearest_domain

    def ingest_batch(
        self,
        texts: list[str],
        source: str | None = None,
        limit: int | None = None,
        namespace: str | None = None,
        priority: str | None = None,
        force_clc_state: str | None = None,
        domain: str | None = None,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        memory_namespace = normalize_namespace(namespace)
        cleaned = [str(text or "").strip() for text in texts if str(text or "").strip()]
        if limit is not None:
            cleaned = cleaned[: max(0, int(limit))]
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for idx, text in enumerate(cleaned):
            try:
                if self.db.memory_exists_text(text, namespace=memory_namespace):
                    skipped.append({"batch_index": idx, "reason": "duplicate_exact_text", "text_preview": text[:160]})
                    continue
                item = self.ingest(
                    text,
                    source=source,
                    namespace=memory_namespace,
                    priority=priority,
                    force_clc_state=force_clc_state,
                    domain=domain,
                    memory_type=memory_type,
                )
                item["batch_index"] = idx
                item["source"] = source
                self.db.set_memory_source(item["memory_id"], source, idx, metadata={"namespace": memory_namespace})
                results.append(item)
            except Exception as exc:
                errors.append({"batch_index": idx, "error": str(exc), "text_preview": text[:160]})
        summary = {
            "ok": True,
            "mode": "ingest_batch",
            "source": source,
            "namespace": memory_namespace,
            "requested": len(texts),
            "accepted": len(cleaned),
            "stored": len(results),
            "skipped": len(skipped),
            "errors": len(errors),
            "partial_errors": bool(errors),
            "results": results,
            "memories": results,
            "skipped_items": skipped,
            "error_items": errors,
        }
        self._append_log(
            {
                "event_type": "batch_ingest",
                "source": source,
                "requested": len(texts),
                "accepted": len(cleaned),
                "stored": len(results),
                "skipped": len(skipped),
                "errors": len(errors),
            }
        )
        return summary

    def retrieve(self, query: str, top_k: int = 5, namespace: str | None = None, include_global: bool = True) -> list[dict[str, Any]]:
        memory_namespace = normalize_namespace(namespace)
        embedding = self.encoder.embed(query)
        self._ensure_embedding_signature(embedding)
        candidate_k = max(int(top_k), 50)
        if self._needs_broad_lexical_scan(query):
            candidate_k = max(candidate_k, 200)
        items = self.recall_engine.index.search(
            embedding,
            top_k=candidate_k,
            namespaces=self._namespace_scope(memory_namespace, include_global=include_global),
        )
        if self._needs_broad_lexical_scan(query):
            items = self._with_lexical_backfill(
                items,
                query,
                namespaces=self._namespace_scope(memory_namespace, include_global=include_global),
                limit=max(candidate_k, 200),
            )
        query_l = str(query or "").lower()
        authority_intent = self._authority_query_intent(query_l)
        if authority_intent:
            items = self._with_authoritative_replacements(items, embedding)
        candidate_ids = [item.memory_id for item in items]
        authority_by_memory = self._authority_status_for_candidates(candidate_ids)
        contradiction_by_memory = self.db.contradiction_summary_for_memories(candidate_ids)
        feedback_by_memory = self.db.feedback_summary_for_memories(candidate_ids)
        usage_by_memory = self.db.usage_summary_for_memories(candidate_ids)
        reliability = self.db.feedback_reliability_for_candidates(candidate_ids)
        supersession_relations = self.db.supersession_summary_for_candidates(candidate_ids)
        summary_relations = self.db.summary_relation_summary_for_candidates(candidate_ids)
        source_info_by_memory = {
            item.memory_id: self.db.get_memory_source(item.memory_id)
            for item in items
        }
        latest_versions = self._latest_source_versions(source_info_by_memory.values())
        out: list[dict[str, Any]] = []
        for item in items:
            domain = self.db.get_domain(item.domain_id) if item.domain_id else None
            domain_name = domain.name if domain else None
            source_info = source_info_by_memory.get(item.memory_id)
            source = source_info["source"] if source_info else None
            domain_match = self._domain_affinity(query_l, domain_name)
            source_match = self._source_affinity(query_l, source)
            text_match = self._text_affinity(query_l, item.text)
            claim_scope_match = self._claim_scope_affinity(query_l, item.text, source)
            answer_type_match = self._answer_type_affinity(query_l, item.text, source)
            broad_generic_penalty = 0.18 if self._broad_generic_note(item.text, source) else 0.0
            identifier_match = self._identifier_affinity(query_l, item.text)
            intent_match = self._intent_affinity(query_l, item.text, item.memory_type)
            feedback = feedback_by_memory.get(item.memory_id, {})
            usage = usage_by_memory.get(item.memory_id, {})
            feedback_score = self._feedback_score(feedback)
            domain_reliability = self._feedback_score(reliability["domains"].get(item.domain_id, {}))
            source_reliability = self._feedback_score(reliability["sources"].get(source, {}))
            heuristic_supersession_score = self._supersession_score(query_l, item.text, source, latest_versions)
            relation_supersession_score = self._relation_supersession_score(
                query_l,
                supersession_relations.get(item.memory_id, {}),
            )
            authority_status = authority_by_memory.get(item.memory_id, {})
            contradiction_status = contradiction_by_memory.get(item.memory_id, {})
            authority_score = float(authority_status.get("authority_score") or 0.0) if authority_intent else 0.0
            if authority_score > 0.0 and not self._claim_scope_matches(query_l, item.text):
                authority_score = min(authority_score, 0.12)
            relation_supersession_score = max(
                -1.0,
                min(1.0, relation_supersession_score + authority_score),
            )
            summary_relation_score = self._summary_relation_score(
                query_l,
                item.text,
                summary_relations.get(item.memory_id, {}),
            )
            supersession_score = max(-1.0, min(1.0, heuristic_supersession_score + relation_supersession_score))
            correction_chain_score = self._correction_chain_score(authority_status)
            correction_relevance = self._correction_relevance(
                authority_status,
                relation_supersession_score,
                correction_chain_score,
                text_match,
                claim_scope_match,
            )
            if correction_relevance < 1.0:
                if heuristic_supersession_score > 0.0:
                    heuristic_supersession_score *= correction_relevance
                if relation_supersession_score > 0.0:
                    relation_supersession_score *= correction_relevance
                if correction_chain_score > 0.0:
                    correction_chain_score *= correction_relevance
                supersession_score = max(-1.0, min(1.0, heuristic_supersession_score + relation_supersession_score))
            w = self.retrieval_weights
            score = (
                w["vector"] * item.score
                + w["importance"] * item.importance
                + w["stability"] * item.stability
                + w["domain"] * domain_match
                + w["text"] * text_match
                + w["claim_scope"] * claim_scope_match
                + 0.18 * identifier_match
                + w["source"] * source_match
                + w["feedback"] * feedback_score
                + w["domain_reliability"] * domain_reliability
                + w["source_reliability"] * source_reliability
                + w["supersession"] * heuristic_supersession_score
                + w["relation_supersession"] * relation_supersession_score
                + w["summary_relation"] * summary_relation_score
                + w["intent"] * intent_match
                + w["correction_chain"] * correction_chain_score
                + w["answer_type"] * answer_type_match
                - broad_generic_penalty
            )
            out.append(
                {
                    "memory_id": item.memory_id,
                    "domain_id": item.domain_id,
                    "domain_name": domain_name,
                    "source": source,
                    "chunk_index": source_info["chunk_index"] if source_info else None,
                    "memory_type": item.memory_type,
                    "clc_state": item.clc_state,
                    "csd_score": round(float(item.csd_score or 0.0), 6),
                    "namespace": item.namespace,
                    "score": round(score, 6),
                    "cosine": round(item.score, 6),
                    "importance": round(item.importance, 6),
                    "stability": round(item.stability, 6),
                    "feedback_score": round(feedback_score, 6),
                    "feedback_count": int(feedback.get("count", 0)),
                    "usage_count": int(usage.get("count", 0)),
                    "last_recalled": usage.get("last_recalled"),
                    "text_match_score": round(text_match, 6),
                    "claim_scope_score": round(claim_scope_match, 6),
                    "answer_type_score": round(answer_type_match, 6),
                    "broad_generic_penalty": round(broad_generic_penalty, 6),
                    "correction_relevance_score": round(correction_relevance, 6),
                    "identifier_match_score": round(identifier_match, 6),
                    "intent_match_score": round(intent_match, 6),
                    "domain_reliability": round(domain_reliability, 6),
                    "source_reliability": round(source_reliability, 6),
                    "supersession_score": round(supersession_score, 6),
                    "relation_supersession_score": round(relation_supersession_score, 6),
                    "summary_relation_score": round(summary_relation_score, 6),
                    "correction_chain_score": round(correction_chain_score, 6),
                    "authority_state": authority_status.get("authority_state", "unknown"),
                    "authoritative_memory_ids": authority_status.get("authoritative_memory_ids", []),
                    "superseded_by_memory_ids": authority_status.get("superseded_by_memory_ids", []),
                    "supersedes_memory_ids": authority_status.get("supersedes_memory_ids", []),
                    "correction_chain_depth": authority_status.get("correction_chain_depth", 0),
                    "authority_relation_types": authority_status.get("relation_types", []),
                    "stored_contradiction_score": round(float(contradiction_status.get("contradiction_score") or 0.0), 6),
                    "stored_contradiction_memory_ids": contradiction_status.get("contradiction_memory_ids", []),
                    "stored_contradiction_statuses": contradiction_status.get("contradiction_statuses", []),
                    "text": item.text,
                }
            )
        out.sort(key=lambda row: row["score"], reverse=True)
        return out[:top_k]

    def authority(
        self,
        memory_ids: list[str] | None = None,
        query: str | None = None,
        top_k: int = 5,
        namespace: str | None = None,
        include_global: bool = True,
    ) -> dict[str, Any]:
        ids: list[str] = []
        for memory_id in memory_ids or []:
            mid = str(memory_id or "").strip()
            if mid and mid not in ids:
                ids.append(mid)
        query_results: list[dict[str, Any]] = []
        cleaned_query = str(query or "").strip()
        if cleaned_query:
            query_results = self.retrieve(
                cleaned_query,
                top_k=max(1, int(top_k)),
                namespace=namespace,
                include_global=include_global,
            )
            for item in query_results:
                mid = str(item.get("memory_id") or "").strip()
                if mid and mid not in ids:
                    ids.append(mid)
        if not ids:
            raise ValueError("authority inspection requires 'memory_id', 'memory_ids', or 'query'")

        graph = self.db.authority_graph_for_memories(ids)
        graph_ids = list(graph.get("memory_ids") or ids)
        status_by_memory = self._authority_status_for_candidates(graph_ids)
        rows = self.db.memory_vectors_by_ids(graph_ids, include_deprecated=False)
        found_ids = {str(row.get("id") or "") for row in rows if row.get("id")}
        missing_ids = [memory_id for memory_id in ids if memory_id not in found_ids]
        if missing_ids and not query_results:
            raise ValueError(f"No authority data found for memory_ids: {missing_ids}")
        query_rank_by_id = {
            str(item.get("memory_id")): idx
            for idx, item in enumerate(query_results, start=1)
            if item.get("memory_id")
        }
        query_score_by_id = {
            str(item.get("memory_id")): item.get("score")
            for item in query_results
            if item.get("memory_id")
        }
        nodes = []
        for row in rows:
            memory_id = str(row.get("id") or "")
            domain = self.db.get_domain(row.get("domain_id")) if row.get("domain_id") else None
            source = self.db.get_memory_source(memory_id)
            status = status_by_memory.get(memory_id, {})
            nodes.append(
                {
                    "memory_id": memory_id,
                    "authority_state": status.get("authority_state", "unknown"),
                    "authoritative_memory_ids": status.get("authoritative_memory_ids", []),
                    "superseded_by_memory_ids": status.get("superseded_by_memory_ids", []),
                    "supersedes_memory_ids": status.get("supersedes_memory_ids", []),
                    "correction_chain_depth": status.get("correction_chain_depth", 0),
                    "authority_relation_types": status.get("relation_types", []),
                    "query_rank": query_rank_by_id.get(memory_id),
                    "query_score": query_score_by_id.get(memory_id),
                    "domain_id": row.get("domain_id"),
                    "domain_name": domain.name if domain else None,
                    "memory_type": row.get("memory_type"),
                    "namespace": normalize_namespace(row.get("namespace")),
                    "source": source.get("source") if source else None,
                    "chunk_index": source.get("chunk_index") if source else None,
                    "text_preview": str(row.get("text") or "")[:320],
                    "text": str(row.get("text") or ""),
                }
            )
        nodes.sort(
            key=lambda item: (
                item.get("query_rank") is None,
                item.get("query_rank") or 999999,
                {"current": 0, "standalone": 1, "superseded": 2}.get(str(item.get("authority_state")), 3),
                item.get("correction_chain_depth") or 0,
                item.get("memory_id") or "",
            )
        )
        current_ids = sorted(
            {
                authoritative_id
                for status in status_by_memory.values()
                for authoritative_id in status.get("authoritative_memory_ids", [])
                if authoritative_id
            }
        )
        return {
            "ok": True,
            "mode": "authority",
            "query": cleaned_query or None,
            "requested_memory_ids": ids,
            "authoritative_memory_ids": current_ids,
            "current_memory_id": current_ids[0] if len(current_ids) == 1 else None,
            "nodes": nodes,
            "relations": graph.get("relations", []),
            "query_results": query_results,
        }

    def ask(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        agent_id: str = "default",
        store_session: bool = False,
        remember: bool = False,
        memory_text: str | None = None,
        namespace: str | None = None,
        include_global: bool = True,
    ) -> dict[str, Any]:
        memory_namespace = normalize_namespace(namespace)
        session_context = self._session_context(session_id, query=query)
        retrieval_query = self._session_retrieval_query(query, session_context)
        retrieval_top_k = max(int(top_k), 20) if session_context else int(top_k)
        retrieval_pool = self.retrieve(
            retrieval_query,
            top_k=max(retrieval_top_k, 20),
            namespace=memory_namespace,
            include_global=include_global,
        )
        results = retrieval_pool[:retrieval_top_k]
        if session_context:
            results = self._apply_session_evidence_boost(results, session_context)[: max(1, int(top_k))]
        else:
            results = results[: max(1, int(top_k))]
        resolved = resolve_answer(query, results)
        source_context = self._source_diverse_context(retrieval_pool, results, limit=max(1, int(top_k)))
        source_context = self._with_summary_source_context(source_context, results, limit=max(1, int(top_k)))
        stale_context = self._stale_companion_context(resolved["evidence"], resolved["raw_results"])
        resolved["source_context"] = source_context
        if stale_context:
            resolved["stale_context"] = stale_context
            if not resolved["stale"] and resolved["conflict"]:
                resolved["answer"] = self._append_stale_context_notice(resolved["answer"])
        else:
            resolved["stale_context"] = []
        session = None
        user_turn = None
        assistant_turn = None
        durable_memory = None
        evidence_memory_ids = [
            str(item.get("memory_id"))
            for item in resolved["evidence"]
            if item.get("memory_id")
        ]
        usage_events: list[dict[str, Any]] = []
        if store_session or session_id:
            title = self._session_title(query)
            session = self.db.ensure_session(session_id=session_id, agent_id=agent_id, title=title)
            user_turn = self.db.add_session_turn(
                session["id"],
                "user",
                query,
                metadata={
                    "top_k": int(top_k),
                    "retrieval_query": retrieval_query,
                    "session_context_used": bool(session_context),
                    "session_context": session_context,
                },
            )
            assistant_turn = self.db.add_session_turn(
                session["id"],
                "assistant",
                resolved["answer"],
                query=query,
                answer=resolved["answer"],
                confidence=resolved["confidence"],
                conflict=resolved["conflict"],
                evidence_memory_ids=evidence_memory_ids,
                metadata={
                    "top_k": int(top_k),
                    "retrieval_query": retrieval_query,
                    "session_context_used": bool(session_context),
                    "session_context": session_context,
                    "current_count": len(resolved["current"]),
                    "summary_count": len(resolved.get("summary", [])),
                    "stale_count": len(resolved["stale"]),
                    "source_context_count": len(source_context),
                    "source_context_memory_ids": [
                        item.get("memory_id")
                        for item in source_context
                        if item.get("memory_id")
                    ],
                    "stale_context_count": len(stale_context),
                    "stale_context_memory_ids": [
                        item.get("memory_id")
                        for item in stale_context
                        if item.get("memory_id")
                    ],
                    "disputed_count": len(resolved["disputed"]),
                    "live_conflict_count": len(resolved.get("live_conflicts", [])),
                },
            )
            self._update_session_memory(
                session["id"],
                role="ask",
                text=f"Question: {query}\nAnswer: {resolved['answer']}",
                evidence_memory_ids=evidence_memory_ids,
                namespace=memory_namespace,
                agent_id=session["agent_id"],
                metadata={
                    "query": query,
                    "confidence": resolved["confidence"],
                    "conflict": resolved["conflict"],
                },
            )
        usage_events = self.db.record_retrieval_use(
            resolved["evidence"],
            query=query,
            answer=resolved["answer"],
            confidence=resolved["confidence"],
            namespace=memory_namespace,
            agent_id=session["agent_id"] if session else agent_id,
            session_id=session["id"] if session else session_id,
        )
        if remember:
            durable_text = str(memory_text or "").strip()
            if not durable_text:
                durable_text = (
                    "Session memory:\n"
                    f"Question: {query}\n"
                    f"Answer: {resolved['answer']}\n"
                    f"Evidence memory ids: {', '.join(evidence_memory_ids)}"
                )
            durable_namespace = f"session:{session['id']}" if session else memory_namespace
            durable_memory = self.ingest(
                durable_text,
                source=f"session:{session['id']}" if session else "session",
                namespace=durable_namespace,
            )
            self.db.set_memory_source(
                durable_memory["memory_id"],
                f"session:{session['id']}" if session else "session",
                0,
                metadata={"remembered_from_ask": True, "query": query, "namespace": durable_namespace},
            )
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "session_context_used": bool(session_context),
            "session_context": session_context,
            "session_id": session["id"] if session else None,
            "agent_id": session["agent_id"] if session else agent_id,
            "namespace": memory_namespace,
            "user_turn_id": user_turn["id"] if user_turn else None,
            "assistant_turn_id": assistant_turn["id"] if assistant_turn else None,
            "answer": resolved["answer"],
            "confidence": resolved["confidence"],
            "conflict": resolved["conflict"],
            "durable_memory": durable_memory,
            "usage_events": usage_events,
            "evidence": resolved["evidence"],
            "source_context": resolved["source_context"],
            "summary": resolved.get("summary", []),
            "current": resolved["current"],
            "historical": resolved["historical"],
            "stale": resolved["stale"],
            "stale_context": resolved["stale_context"],
            "disputed": resolved["disputed"],
            "live_conflicts": resolved.get("live_conflicts", []),
            "raw_results": resolved["raw_results"],
        }

    def teach(
        self,
        text: str,
        source: str | None = None,
        session_id: str | None = None,
        agent_id: str = "default",
        store_session: bool = True,
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
        priority: str | None = None,
        force_clc_state: str | None = None,
        domain: str | None = None,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        memory_namespace = normalize_namespace(namespace)
        cleaned = str(text or "").strip()
        if not cleaned:
            raise ValueError("teach text is required")
        session = None
        user_turn = None
        memory_source = source or f"teach:{agent_id}"
        memory = self.ingest(
            cleaned,
            source=memory_source,
            namespace=memory_namespace,
            priority=priority,
            force_clc_state=force_clc_state,
            domain=domain,
            memory_type=memory_type,
        )
        self.db.set_memory_source(
            memory["memory_id"],
            memory_source,
            0,
            metadata={
                "agent_id": agent_id,
                "session_id": session_id,
                "namespace": memory_namespace,
                "priority": memory.get("priority"),
                "force_clc_state": force_clc_state,
                "explicit_domain": domain,
                "explicit_memory_type": memory_type,
                **(metadata or {}),
            },
        )
        if store_session or session_id:
            session = self.db.ensure_session(
                session_id=session_id,
                agent_id=agent_id,
                title=self._session_title(cleaned),
                metadata={"training_mode": "teach"},
            )
            user_turn = self.db.add_session_turn(
                session["id"],
                "teach",
                cleaned,
                evidence_memory_ids=[memory["memory_id"]],
                metadata={"source": memory_source, "memory_id": memory["memory_id"], **(metadata or {})},
            )
            self._update_session_memory(
                session["id"],
                role="teach",
                text=cleaned,
                evidence_memory_ids=[memory["memory_id"]],
                namespace=memory_namespace,
                agent_id=session["agent_id"],
                metadata={"source": memory_source, "memory_id": memory["memory_id"], **(metadata or {})},
            )
        self.db.add_event(
            memory["memory_id"],
            "teach",
            metadata={"agent_id": agent_id, "session_id": session["id"] if session else session_id, "source": memory_source},
        )
        return {
            "ok": True,
            "mode": "teach",
            "session_id": session["id"] if session else None,
            "agent_id": session["agent_id"] if session else agent_id,
            "namespace": memory_namespace,
            "turn_id": user_turn["id"] if user_turn else None,
            "memory": memory,
        }

    def correct(
        self,
        correction: str,
        target_memory_ids: list[str] | None = None,
        target_query: str | None = None,
        top_k: int = 5,
        source: str | None = None,
        session_id: str | None = None,
        agent_id: str = "default",
        store_session: bool = True,
        stale_label: str = "stale",
        stale_rating: float = -0.75,
        relation_type: str = "corrects",
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
        priority: str | None = "high",
        force_clc_state: str | None = None,
        domain: str | None = None,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        memory_namespace = normalize_namespace(namespace)
        cleaned = str(correction or "").strip()
        if not cleaned:
            raise ValueError("correction text is required")
        explicit_target_ids = self._unique_ids(target_memory_ids or [])
        invalid_explicit_ids = self._invalid_target_memory_ids(explicit_target_ids, memory_namespace)
        if invalid_explicit_ids:
            raise ValueError(f"Unknown or out-of-scope target_memory_ids: {invalid_explicit_ids}")
        target_ids = self._correction_targets(
            explicit_target_ids,
            target_query,
            cleaned,
            top_k,
            session_id=session_id,
            namespace=memory_namespace,
        )
        correction_text = cleaned if cleaned.lower().startswith("correction:") else f"Correction: {cleaned}"
        memory_source = source or f"correction:{agent_id}"
        session = None
        turn = None
        correction_memory = self.ingest(
            correction_text,
            source=memory_source,
            namespace=memory_namespace,
            priority=priority,
            force_clc_state=force_clc_state,
            domain_text=cleaned,
            prefer_symbolic_domain=True,
            domain=domain,
            memory_type=memory_type,
        )
        self.db.set_memory_source(
            correction_memory["memory_id"],
            memory_source,
            0,
            metadata={
                "agent_id": agent_id,
                "session_id": session_id,
                "target_memory_ids": target_ids,
                "target_query": target_query,
                "namespace": memory_namespace,
                "priority": correction_memory.get("priority"),
                "force_clc_state": force_clc_state,
                "explicit_domain": domain,
                "explicit_memory_type": memory_type,
                **(metadata or {}),
            },
        )

        linked = []
        feedback = []
        for target_id in target_ids:
            if target_id == correction_memory["memory_id"]:
                continue
            self.db.add_relation(correction_memory["memory_id"], target_id, relation_type, 1.0)
            linked.append({"source_memory_id": correction_memory["memory_id"], "target_memory_id": target_id, "relation_type": relation_type})
            feedback.append(
                self.db.add_retrieval_feedback(
                    target_id,
                    stale_label,
                    query=target_query or cleaned,
                    rating=stale_rating,
                    notes="Marked stale by correction workflow",
                    metadata={
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "correction_memory_id": correction_memory["memory_id"],
                        "namespace": memory_namespace,
                        **(metadata or {}),
                    },
                )
            )

        if store_session or session_id:
            session = self.db.ensure_session(
                session_id=session_id,
                agent_id=agent_id,
                title=self._session_title(cleaned),
                metadata={"training_mode": "correct"},
            )
            turn = self.db.add_session_turn(
                session["id"],
                "correct",
                correction_text,
                query=target_query,
                evidence_memory_ids=[correction_memory["memory_id"], *target_ids],
                metadata={
                    "source": memory_source,
                    "correction_memory_id": correction_memory["memory_id"],
                    "target_memory_ids": target_ids,
                    "relation_type": relation_type,
                    "feedback_ids": [item["id"] for item in feedback],
                    **(metadata or {}),
                },
            )
            self._update_session_memory(
                session["id"],
                role="correct",
                text=correction_text,
                evidence_memory_ids=[correction_memory["memory_id"], *target_ids],
                namespace=memory_namespace,
                agent_id=session["agent_id"],
                metadata={
                    "source": memory_source,
                    "correction_memory_id": correction_memory["memory_id"],
                    "target_memory_ids": target_ids,
                    "relation_type": relation_type,
                    **(metadata or {}),
                },
            )
        self.db.add_event(
            correction_memory["memory_id"],
            "correct",
            metadata={
                "agent_id": agent_id,
                "session_id": session["id"] if session else session_id,
                "target_memory_ids": target_ids,
                "relation_type": relation_type,
                "namespace": memory_namespace,
            },
        )
        return {
            "ok": True,
            "mode": "correct",
            "linked": bool(linked),
            "warning": None
            if linked
            else "No target memories found. Correction was stored but is not linked to any existing memory.",
            "namespace": memory_namespace,
            "session_id": session["id"] if session else None,
            "agent_id": session["agent_id"] if session else agent_id,
            "turn_id": turn["id"] if turn else None,
            "correction_memory": correction_memory,
            "target_memory_ids": target_ids,
            "relations": linked,
            "feedback": feedback,
        }

    def _correction_targets(
        self,
        target_memory_ids: list[str],
        target_query: str | None,
        correction_text: str | None,
        top_k: int,
        session_id: str | None = None,
        namespace: str | None = None,
    ) -> list[str]:
        out: list[str] = self._unique_ids(target_memory_ids)
        query = str(target_query or "").strip()
        if not out and not query and session_id:
            for mid in self.db.latest_assistant_evidence(session_id):
                if mid and mid not in out:
                    out.append(mid)
        if out:
            return out
        fallback_query = query or str(correction_text or "").strip()
        if not query and self._explicit_orphan_correction(fallback_query):
            return out
        if fallback_query:
            context = self._session_context(session_id, query=fallback_query)
            retrieval_query = self._session_retrieval_query(fallback_query, context)
            for item in self.retrieve(retrieval_query, top_k=max(1, int(top_k)), namespace=namespace):
                mid = str(item.get("memory_id") or "").strip()
                if not self._correction_target_candidate(fallback_query, item):
                    continue
                if mid and mid not in out:
                    out.append(mid)
        return out

    @classmethod
    def _correction_target_candidate(cls, correction_text: str, item: dict[str, Any]) -> bool:
        text_match = float(item.get("text_match_score") or 0.0)
        score = float(item.get("score") or 0.0)
        overlap = cls._token_overlap(cls._topic_tokens(correction_text), cls._topic_tokens(str(item.get("text") or "")))
        return overlap >= 0.33 or (overlap >= 0.22 and (text_match >= 0.35 or score >= 0.34))

    @staticmethod
    def _explicit_orphan_correction(correction_text: str) -> bool:
        lower = str(correction_text or "").lower()
        return "orphan" in lower or "no target" in lower or "without target" in lower

    @staticmethod
    def _unique_ids(memory_ids: list[str] | tuple[str, ...]) -> list[str]:
        out: list[str] = []
        for memory_id in memory_ids:
            mid = str(memory_id or "").strip()
            if mid and mid not in out:
                out.append(mid)
        return out

    def _invalid_target_memory_ids(self, memory_ids: list[str], namespace: str | None = None) -> list[str]:
        ids = self._unique_ids(memory_ids)
        if not ids:
            return []
        allowed_namespaces = set(self._namespace_scope(namespace, include_global=True))
        rows = self.db.memory_vectors_by_ids(ids, include_deprecated=False)
        valid_ids = {
            str(row.get("id") or "")
            for row in rows
            if normalize_namespace(row.get("namespace")) in allowed_namespaces
        }
        return [memory_id for memory_id in ids if memory_id not in valid_ids]

    @staticmethod
    def _namespace_scope(namespace: str | None, include_global: bool = True) -> list[str]:
        normalized = normalize_namespace(namespace)
        if include_global and normalized != "global":
            return ["global", normalized]
        return [normalized]

    def _session_context(
        self,
        session_id: str | None,
        query: str | None = None,
        limit: int = 10,
        max_items: int = 4,
    ) -> list[dict[str, Any]]:
        sid = str(session_id or "").strip()
        if not sid or self.db.get_session(sid) is None:
            return []
        turns = self.db.recent_session_turns(sid, limit=limit)
        active_memory = self.db.get_session_memory(sid, "active_topic")
        query_tokens = self._topic_tokens(query or "")
        prepared_turns: list[dict[str, Any]] = []
        active_evidence_ids: set[str] = set()
        active_overlap = 0.0
        active_topic_available = False
        if active_memory is not None:
            active_content = str(active_memory.get("value") or "").strip()
            active_metadata = active_memory.get("metadata") or {}
            active_evidence_ids = {
                str(memory_id).strip()
                for memory_id in active_metadata.get("evidence_memory_ids") or []
                if str(memory_id).strip()
            }
            metadata_tokens = {
                str(token).strip().lower()
                for token in active_metadata.get("topic_tokens") or []
                if str(token).strip()
            }
            active_tokens = metadata_tokens or self._topic_tokens(active_content)
            active_overlap = self._token_overlap(query_tokens, active_tokens)
            active_topic_available = bool(active_tokens)
        vague_followup = self._is_vague_followup(
            query or "",
            query_tokens,
            active_overlap=active_overlap,
            active_topic_available=active_topic_available,
        )
        if active_memory is not None:
            if vague_followup or active_overlap > 0.0:
                prepared_turns.append(
                    {
                        "turn": {
                            "role": "session_memory",
                            "content": active_content,
                            "evidence_memory_ids": active_metadata.get("evidence_memory_ids") or [],
                        },
                        "idx": len(turns),
                        "raw_content": active_content,
                        "overlap": active_overlap,
                        "is_session_memory": True,
                    }
                )
        for idx, turn in enumerate(turns):
            raw_content = str(turn.get("content") or turn.get("answer") or "").strip()
            if not raw_content:
                continue
            content_tokens = self._topic_tokens(raw_content)
            overlap = self._token_overlap(query_tokens, content_tokens)
            prepared_turns.append(
                {
                    "turn": turn,
                    "idx": idx,
                    "raw_content": raw_content,
                    "overlap": overlap,
                }
            )
        has_topic_match = any(item["overlap"] > 0.0 for item in prepared_turns)
        scored: list[dict[str, Any]] = []
        total = max(1, len(turns))
        for prepared in prepared_turns:
            turn = prepared["turn"]
            idx = prepared["idx"]
            raw_content = prepared["raw_content"]
            overlap = prepared["overlap"]
            evidence_ids = turn.get("evidence_memory_ids") or []
            role = str(turn.get("role") or "").strip().lower() or "event"
            recency = (idx + 1) / total
            evidence_bonus = 0.15 if evidence_ids and role in {"assistant", "teach", "correct"} else 0.0
            role_bonus = 0.06 if role in {"teach", "correct"} else 0.0
            evidence_matches_active = bool(active_evidence_ids & {str(mid).strip() for mid in evidence_ids if str(mid).strip()})
            if prepared.get("is_session_memory"):
                evidence_bonus = 0.20 if evidence_ids else 0.0
                role_bonus = 0.12
                recency = 1.0
            score = overlap + role_bonus + evidence_bonus
            if vague_followup and overlap > 0.0:
                score += 0.25 * recency
            elif vague_followup and not has_topic_match:
                if active_evidence_ids and not (prepared.get("is_session_memory") or evidence_matches_active):
                    score = 0.0
                else:
                    score += 0.25 * recency
            elif overlap <= 0.0:
                score = 0.0
            if score <= 0.0:
                continue
            scored.append(
                {
                    "role": role,
                    "content": self._short_context_text(raw_content),
                    "evidence_memory_ids": evidence_ids,
                    "context_score": round(score, 6),
                    "active_evidence_match": bool(prepared.get("is_session_memory") or evidence_matches_active),
                    "vague_followup": vague_followup,
                    "turn_index": idx,
                }
            )
        scored.sort(key=lambda item: (item["context_score"], item["turn_index"]), reverse=True)
        selected = sorted(scored[: max(1, int(max_items))], key=lambda item: item["turn_index"])
        for item in selected:
            item.pop("turn_index", None)
        return selected

    @staticmethod
    def _session_retrieval_query(query: str, session_context: list[dict[str, Any]]) -> str:
        if not session_context:
            return query
        if not any(bool(item.get("vague_followup")) for item in session_context):
            return query
        context_lines = [
            f"{item['role']}: {item['content']}"
            for item in session_context[-6:]
            if item.get("content")
        ]
        if not context_lines:
            return query
        return "Session context:\n" + "\n".join(context_lines) + f"\nCurrent question: {query}"

    def _update_session_memory(
        self,
        session_id: str,
        role: str,
        text: str,
        evidence_memory_ids: list[str] | None = None,
        namespace: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        cleaned = self._short_context_text(str(text or "").strip(), limit=900)
        if not cleaned:
            return None
        evidence_ids = []
        for memory_id in evidence_memory_ids or []:
            mid = str(memory_id or "").strip()
            if mid and mid not in evidence_ids:
                evidence_ids.append(mid)
        topic_tokens = sorted(self._topic_tokens(cleaned))[:24]
        value = f"Active session topic ({role}): {cleaned}"
        return self.db.upsert_session_memory(
            session_id,
            "active_topic",
            value,
            metadata={
                "role": role,
                "agent_id": agent_id,
                "namespace": normalize_namespace(namespace),
                "evidence_memory_ids": evidence_ids,
                "topic_tokens": topic_tokens,
                **(metadata or {}),
            },
        )

    @staticmethod
    def _apply_session_evidence_boost(
        results: list[dict[str, Any]],
        session_context: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        context_scores: dict[str, float] = {}
        exact_active_ids: set[str] = set()
        for item in session_context:
            if not bool(item.get("vague_followup")):
                continue
            score = float(item.get("context_score") or 0.0)
            exact_active = bool(item.get("active_evidence_match"))
            for memory_id in item.get("evidence_memory_ids") or []:
                mid = str(memory_id or "").strip()
                if mid:
                    context_scores[mid] = max(context_scores.get(mid, 0.0), score)
                    if exact_active:
                        exact_active_ids.add(mid)
        if not context_scores:
            return results
        boosted: list[dict[str, Any]] = []
        for item in results:
            row = dict(item)
            context_score = context_scores.get(str(row.get("memory_id") or ""), 0.0)
            if context_score > 0.0:
                memory_id = str(row.get("memory_id") or "")
                exact_active = memory_id in exact_active_ids
                boost = min(0.22, 0.10 + 0.18 * context_score) if exact_active else min(0.08, 0.04 + 0.08 * context_score)
                row["base_score"] = row["score"]
                row["session_evidence_score"] = round(context_score, 6)
                row["session_evidence_boost"] = round(boost, 6)
                row["session_exact_evidence"] = exact_active
                row["score"] = round(float(row["score"]) + boost, 6)
            boosted.append(row)
        boosted.sort(key=lambda row: row["score"], reverse=True)
        return boosted

    @classmethod
    def _topic_tokens(cls, text: str) -> set[str]:
        stopwords = {
            "a",
            "about",
            "again",
            "also",
            "am",
            "an",
            "and",
            "answer",
            "are",
            "as",
            "at",
            "be",
            "by",
            "can",
            "could",
            "current",
            "do",
            "does",
            "for",
            "from",
            "had",
            "has",
            "have",
            "how",
            "i",
            "in",
            "indicates",
            "is",
            "it",
            "its",
            "me",
            "memory",
            "must",
            "of",
            "on",
            "or",
            "our",
            "question",
            "remember",
            "relevant",
            "should",
            "so",
            "session",
            "that",
            "the",
            "their",
            "there",
            "this",
            "to",
            "topic",
            "was",
            "we",
            "what",
            "when",
            "where",
            "which",
            "who",
            "why",
            "with",
            "would",
            "you",
            "your",
            "victor",
            "hermes",
            "agent",
            "assistant",
        }
        tokens = {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", str(text or "").lower())
            if token not in stopwords
        }
        return tokens

    @staticmethod
    def _token_overlap(query_tokens: set[str], content_tokens: set[str]) -> float:
        if not query_tokens or not content_tokens:
            return 0.0
        matches = query_tokens & content_tokens
        if not matches:
            return 0.0
        return len(matches) / max(1, len(query_tokens))

    @staticmethod
    def _is_vague_followup(
        query: str,
        query_tokens: set[str],
        active_overlap: float = 0.0,
        active_topic_available: bool = False,
    ) -> bool:
        normalized = re.sub(r"[^\w\s]", " ", str(query or "").lower())
        compact = f" {normalized} "
        vague_markers = (
            " that ",
            " this ",
            " it ",
            " its ",
            " they ",
            " them ",
            " those ",
            " these ",
            " previous ",
            " earlier ",
            " last ",
            " above ",
        )
        if any(marker in compact for marker in vague_markers):
            return True
        return False

    @staticmethod
    def _short_context_text(text: str, limit: int = 240) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) > limit:
            compact = compact[: limit - 3].rstrip() + "..."
        return compact

    @staticmethod
    def _session_title(query: str) -> str:
        title = " ".join(str(query or "").split())
        if len(title) > 80:
            title = title[:77].rstrip() + "..."
        return title or "Memory session"

    @staticmethod
    def _apply_source_domain_hint(signal, source: str | None) -> None:
        if not source:
            return
        stem = Path(str(source)).stem.lower()
        hint = None
        if "geometry_controller" in stem or "geometry_gguf" in stem or "lcm_geometry" in stem:
            hint = "OpenClaw"
        elif "g-cl" in stem or "gcl" in stem:
            hint = "G-CL"
        elif "csd" in stem:
            hint = "CSD"
        if hint and hint not in signal.domains:
            signal.domains.insert(0, hint)
        elif hint and signal.domains and signal.domains[0] != hint:
            signal.domains.remove(hint)
            signal.domains.insert(0, hint)

    @staticmethod
    def _apply_explicit_classification(signal, domain: str | None = None, memory_type: str | None = None) -> None:
        explicit_domain = str(domain or "").strip()
        if explicit_domain:
            signal.domains = [explicit_domain, *[item for item in signal.domains if item != explicit_domain]]
        explicit_type = str(memory_type or "").strip()
        if explicit_type:
            if explicit_type not in VALID_MEMORY_TYPES:
                raise ValueError(f"unsupported memory_type override: {explicit_type}")
            signal.memory_type = explicit_type

    @staticmethod
    def _domain_affinity(query: str, domain_name: str | None) -> float:
        if not domain_name:
            return 0.0
        query_l = str(query or "").lower()
        domain_l = str(domain_name or "").lower()
        normalized_domain = domain_l.replace("_", " ").replace("-", " ")
        if domain_l in query_l or normalized_domain in query_l:
            return 1.0
        aliases = {
            "agent_memory": ("agent memory", "memory brain", "memory program"),
            "g-cl": ("gcl", "geometry controlled learning", "geometry controlled"),
            "openclaw": ("geometry controller", "lcm geometry"),
            "csd": ("constraint semantic", "contradiction novelty"),
            "clc": ("clc", "controller novelty"),
        }
        for alias in aliases.get(domain_l, ()):
            if alias in query_l:
                return 1.0
        return 0.0

    @staticmethod
    def _text_affinity(query: str, text: str) -> float:
        query_tokens = MemoryPipeline._expanded_tokens(query)
        text_tokens = MemoryPipeline._expanded_tokens(text)
        if not query_tokens or not text_tokens:
            return 0.0
        stopwords = {
            "about",
            "after",
            "does",
            "handle",
            "how",
            "should",
            "that",
            "the",
            "what",
            "when",
            "where",
            "whether",
            "which",
            "with",
            "who",
        }
        query_terms = {token for token in query_tokens if len(token) > 2 and token not in stopwords}
        if not query_terms:
            return 0.0
        hits = len(query_terms & set(text_tokens))
        return min(1.0, hits / max(1, len(query_terms)))

    def _intent_affinity(self, query: str, text: str, memory_type: str | None = None) -> float:
        query_l = str(query or "").lower()
        text_l = str(text or "").lower()
        query_intents = self._intent_labels(query_l, None)
        if not query_intents:
            return 0.0
        text_intents = self._intent_labels(text_l, memory_type)
        score = 0.0
        overlap = query_intents & text_intents
        if overlap:
            score += min(1.0, len(overlap) / max(1, len(query_intents)))
        if MemoryPipeline._query_entity_miss(query_l, text_l):
            score -= 0.45
        if "work" in query_intents and text_intents & {"food_drink", "preference"} and "work" not in text_intents:
            score -= 0.45
        if "presentation" in query_intents and text_intents & {"food_drink"} and "presentation" not in text_intents:
            score -= 0.45
        if "food_drink" in query_intents and text_intents and "food_drink" not in text_intents:
            score -= 0.25
        if "preference" in query_intents and "victor" in query_l and "victor" not in text_l:
            score -= 0.35
        return max(-1.0, min(1.0, score))

    def _claim_scope_affinity(self, query: str, text: str, source: str | None = None) -> float:
        stopwords = set(self.claim_scope_config["stopwords"])
        query_l = str(query or "").lower()
        text_l = str(text or "").lower()
        query_terms = {
            token
            for token in MemoryPipeline._expanded_tokens(query_l)
            if len(token) > 2 and token not in stopwords
        }
        if not query_terms:
            return 0.0
        text_terms = MemoryPipeline._expanded_tokens(text_l)
        source_terms = MemoryPipeline._expanded_tokens(Path(str(source or "")).stem)
        combined_terms = set(text_terms) | set(source_terms)
        for slot, aliases in self.claim_scope_config["slot_aliases"].items():
            slot_terms = MemoryPipeline._expanded_tokens(slot)
            if not slot_terms or not (query_terms & slot_terms):
                continue
            alias_terms = set(slot_terms)
            for alias in aliases:
                alias_terms.update(MemoryPipeline._expanded_tokens(alias))
            excluded_terms: set[str] = set()
            for excluded in self.claim_scope_config["excluded_terms"].get(slot, ()):
                excluded_terms.update(MemoryPipeline._expanded_tokens(excluded))
            if combined_terms & alias_terms and not (combined_terms & excluded_terms):
                combined_terms.update(slot_terms)
        hits = len(query_terms & combined_terms)
        return min(1.0, hits / max(1, len(query_terms)))

    def _answer_type_affinity(self, query: str, text: str, source: str | None = None) -> float:
        query_terms = set(MemoryPipeline._expanded_tokens(query))
        text_terms = set(MemoryPipeline._expanded_tokens(text))
        if not query_terms or not text_terms:
            return 0.0

        score = 0.0
        for rule in self.answer_type_config["rules"].values():
            query_rule_terms = self._answer_type_rule_terms(rule["query_terms"])
            if not query_rule_terms or not (query_terms & query_rule_terms):
                continue
            required_query_terms = self._answer_type_rule_terms(rule["query_requires_any"])
            if required_query_terms and not (query_terms & required_query_terms):
                continue
            excluded_query_terms = self._answer_type_rule_terms(rule["query_excludes_any"])
            if excluded_query_terms and query_terms & excluded_query_terms:
                continue

            positive_terms = self._answer_type_rule_terms(rule["positive_terms"])
            positive_required = self._answer_type_rule_terms(rule["positive_requires_any"])
            if positive_terms and text_terms & positive_terms:
                if not positive_required or text_terms & positive_required:
                    score = max(score, float(rule["positive_score"]))

            negative_terms = self._answer_type_rule_terms(rule["negative_terms"])
            negative_absent = self._answer_type_rule_terms(rule["negative_requires_absent"])
            if negative_terms and text_terms & negative_terms:
                if not negative_absent or not (text_terms & negative_absent):
                    score = min(score, float(rule["negative_score"]))
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _answer_type_rule_terms(values: tuple[str, ...]) -> set[str]:
        terms: set[str] = set()
        for value in values:
            terms.update(MemoryPipeline._expanded_tokens(value))
        return terms

    @staticmethod
    def _broad_generic_note(text: str | None, source: str | None) -> bool:
        text_l = str(text or "").strip().lower()
        source_l = str(source or "").strip().lower()
        return (
            "broad_policy" in source_l
            or "general_policy" in source_l
            or text_l.startswith("broad policy note")
            or text_l.startswith("general policy note")
        )

    @staticmethod
    def _correction_relevance(
        authority_status: dict[str, Any],
        relation_supersession_score: float,
        correction_chain_score: float,
        text_match: float,
        claim_scope_match: float,
    ) -> float:
        state = str(authority_status.get("authority_state") or "").lower()
        has_correction_signal = (
            state in {"current", "superseded", "stale"}
            or abs(float(relation_supersession_score or 0.0)) > 0.0
            or abs(float(correction_chain_score or 0.0)) > 0.0
        )
        if not has_correction_signal:
            return 1.0
        if claim_scope_match >= 0.75 or text_match >= 0.75:
            return 1.0
        return max(0.15, min(1.0, claim_scope_match))

    def _intent_labels(self, text: str, memory_type: str | None = None) -> set[str]:
        lower = str(text or "").lower()
        labels: set[str] = set()
        intent_terms = self._configured_intent_terms()
        for label, terms in intent_terms.items():
            if any(term in lower for term in terms):
                labels.add(label)
        if memory_type == "preference":
            labels.add("preference")
        return labels

    @staticmethod
    def _query_entity_miss(query: str, text: str) -> bool:
        query_tokens = MemoryPipeline._tokens(query)
        text_tokens = set(MemoryPipeline._tokens(text))
        named_queries = {"victor", "hermes", "agent", "assistant"} & set(query_tokens)
        if not named_queries:
            return False
        return not bool(named_queries & text_tokens)

    def _claim_scope_matches(self, query: str, text: str) -> bool:
        query_intents = self._intent_labels(query, None)
        if not query_intents:
            return True
        text_intents = self._intent_labels(text, None)
        if query_intents & text_intents:
            return True
        return not MemoryPipeline._query_entity_miss(query, text) and MemoryPipeline._text_affinity(query, text) >= 0.45

    def _configured_intent_terms(self) -> dict[str, tuple[str, ...]]:
        return configured_intent_terms(self.symbolic_config)

    @staticmethod
    def _parse_intent_labels(value: Any) -> dict[str, tuple[str, ...]]:
        return _parse_intent_labels(value)

    @staticmethod
    def _identifier_affinity(query: str, text: str) -> float:
        query_identifiers = {
            token
            for token in MemoryPipeline._tokens(query)
            if any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token)
        }
        if not query_identifiers:
            return 0.0
        text_tokens = MemoryPipeline._tokens(text)
        hits = len(query_identifiers & text_tokens)
        return min(1.0, hits / max(1, len(query_identifiers)))

    @staticmethod
    def _source_affinity(query: str, source: str | None) -> float:
        if not source:
            return 0.0
        query_tokens = MemoryPipeline._tokens(query)
        if not query_tokens:
            return 0.0
        source_stem = Path(str(source)).stem.lower()
        source_tokens = [token for token in MemoryPipeline._tokens(source_stem) if token not in {"md", "skill"}]
        if not source_tokens:
            return 0.0
        hits = sum(1 for token in set(source_tokens) if token in query_tokens)
        return min(1.0, hits / min(2, len(set(source_tokens))))

    @staticmethod
    def _feedback_score(summary: dict[str, Any]) -> float:
        count = int(summary.get("count") or 0)
        if count <= 0:
            return 0.0
        avg = float(summary.get("avg_rating") or 0.0)
        if avg >= 0.0:
            normalized = min(1.0, avg / 2.0)
        else:
            normalized = max(-1.0, avg)
        confidence = min(1.0, count / 3.0)
        return max(-1.0, min(1.0, normalized * confidence))

    @staticmethod
    def _latest_source_versions(source_infos) -> dict[str, int]:
        latest: dict[str, int] = {}
        for info in source_infos:
            source = info["source"] if info else None
            group, version = MemoryPipeline._source_version(source)
            if not group or version <= 0:
                continue
            latest[group] = max(latest.get(group, 0), version)
        return latest

    @staticmethod
    def _supersession_score(query: str, text: str, source: str | None, latest_versions: dict[str, int]) -> float:
        group, version = MemoryPipeline._source_version(source)
        latest = latest_versions.get(group or "", version)
        text_l = str(text or "").lower()
        current_intent = any(
            term in query
            for term in (
                "current",
                "now",
                "latest",
                "correct",
                "correction",
                "preference",
                "policy",
                "should",
                "must",
                "can",
                "priority",
                "instead",
                "change",
            )
        )
        correction_language = any(
            term in text_l
            for term in (
                "correction:",
                "now ",
                "must not",
                "only when",
                "prefer the corrected",
                "not novadesk",
                "no longer",
            )
        )
        stale_language = any(
            term in text_l
            for term in (
                "old ",
                "conflict seeds",
                "not final truth",
                "may push",
                "before memory diagnostics",
                "automatic monday",
            )
        )
        score = 0.0
        if version and latest and version < latest:
            if current_intent:
                score -= 0.65
            if stale_language:
                score -= 0.35
        elif version and latest and version == latest and latest > 1:
            if current_intent:
                score += 0.45
            if correction_language:
                score += 0.55
        elif correction_language and current_intent:
            score += 0.25
        if stale_language and current_intent:
            score -= 0.20
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _relation_supersession_score(query: str, summary: dict[str, Any]) -> float:
        outgoing = float(summary.get("outgoing_weight") or 0.0)
        incoming = float(summary.get("incoming_weight") or 0.0)
        if outgoing <= 0.0 and incoming <= 0.0:
            return 0.0
        current_intent = any(
            term in query
            for term in (
                "current",
                "now",
                "latest",
                "correct",
                "correction",
                "preference",
                "policy",
                "should",
                "must",
                "can",
                "priority",
                "instead",
                "change",
            )
        )
        scale = 1.0 if current_intent else 0.45
        outgoing_score = min(0.80, outgoing / 4.0) * scale
        incoming_score = min(0.90, incoming / 4.0) * scale
        return max(-1.0, min(1.0, outgoing_score - incoming_score))

    @staticmethod
    def _summary_relation_score(query: str, text: str, summary: dict[str, Any]) -> float:
        outgoing = float(summary.get("outgoing_weight") or 0.0)
        incoming = float(summary.get("incoming_weight") or 0.0)
        if outgoing <= 0.0 and incoming <= 0.0:
            return 0.0
        broad_intent = any(
            term in query
            for term in (
                "summary",
                "summarize",
                "overview",
                "main points",
                "main ideas",
                "all",
                "what are",
                "what should",
                "how does",
                "general",
                "overall",
                "work",
            )
        )
        text_l = str(text or "").lower()
        summary_text = text_l.startswith("consolidated summary:")
        if outgoing > 0.0 and summary_text:
            return min(1.0, outgoing / 4.0) if broad_intent else min(0.35, outgoing / 10.0)
        if incoming > 0.0:
            return 0.10 if broad_intent else 0.0
        return 0.0

    @staticmethod
    def _correction_chain_score(authority_status: dict[str, Any]) -> float:
        state = str(authority_status.get("authority_state") or "standalone").lower()
        try:
            depth = int(authority_status.get("correction_chain_depth") or 0)
        except (TypeError, ValueError):
            depth = 0
        if state == "current":
            return min(2.0, 1.0 + min(depth, 2) * 0.5)
        if state == "superseded":
            return -min(3.0, max(1.0, float(depth or 1)))
        return 0.0

    def _stale_companion_context(
        self,
        evidence: list[dict[str, Any]],
        raw_results: list[dict[str, Any]],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        evidence_ids = {
            str(item.get("memory_id"))
            for item in evidence
            if item.get("memory_id")
        }
        source_ids = [
            str(item.get("memory_id"))
            for item in evidence
            if item.get("memory_id") and item.get("memory_state") == "current"
        ]
        if not source_ids:
            source_ids = [
                str(item.get("memory_id"))
                for item in evidence
                if item.get("memory_id")
                and (
                    str(item.get("text_preview") or "").lower().startswith("correction:")
                    or float(item.get("relation_supersession_score") or 0.0) > 0.0
                    or float(item.get("supersession_score") or 0.0) > 0.0
                )
            ]
        if not source_ids:
            return []

        raw_by_id = {
            str(item.get("memory_id")): item
            for item in raw_results
            if item.get("memory_id")
        }
        companions = self.db.superseded_memories_for_sources(source_ids, limit=limit)
        companion_ids = [
            item["memory_id"]
            for item in companions
            if item.get("memory_id") and item["memory_id"] not in evidence_ids
        ]
        feedback_by_memory = self.db.feedback_summary_for_memories(companion_ids)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in companions:
            memory_id = str(item.get("memory_id") or "")
            if not memory_id or memory_id in evidence_ids or memory_id in seen:
                continue
            seen.add(memory_id)
            feedback = feedback_by_memory.get(memory_id, {})
            raw = raw_by_id.get(memory_id, {})
            relation_weight = max(0.0, float(item.get("relation_weight") or 0.0))
            row = {
                "memory_id": memory_id,
                "rank": None,
                "memory_state": "stale",
                "score": raw.get("score", round(-relation_weight, 6)),
                "source": item.get("source"),
                "chunk_index": item.get("chunk_index"),
                "domain_name": item.get("domain_name"),
                "memory_type": item.get("memory_type"),
                "feedback_score": round(self._feedback_score(feedback), 6),
                "supersession_score": raw.get("supersession_score", round(-relation_weight, 6)),
                "relation_supersession_score": raw.get("relation_supersession_score", round(-relation_weight, 6)),
                "current_memory_id": item.get("current_memory_id"),
                "relation_type": item.get("relation_type"),
                "relation_weight": round(relation_weight, 6),
                "text": item.get("text"),
            }
            compact = compact_evidence(row)
            compact.update(
                {
                    "current_memory_id": row["current_memory_id"],
                    "relation_type": row["relation_type"],
                    "relation_weight": row["relation_weight"],
                }
            )
            out.append(compact)
            if len(out) >= max(1, int(limit)):
                break
        return out

    def _with_summary_source_context(
        self,
        source_context: list[dict[str, Any]],
        primary_results: list[dict[str, Any]],
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        summary_ids = [
            str(item.get("memory_id"))
            for item in primary_results
            if item.get("memory_id") and float(item.get("summary_relation_score") or 0.0) > 0.0
        ]
        if not summary_ids:
            return source_context
        existing = {
            str(item.get("memory_id"))
            for item in [*source_context, *primary_results]
            if item.get("memory_id")
        }
        additions = []
        for row in self.db.summarized_memories_for_sources(summary_ids, limit=max(1, int(limit))):
            memory_id = str(row.get("memory_id") or "")
            if not memory_id or memory_id in existing:
                continue
            existing.add(memory_id)
            additions.append(
                {
                    "memory_id": memory_id,
                    "rank": None,
                    "memory_state": "source",
                    "score": round(float(row.get("relation_weight") or 0.0), 6),
                    "source": row.get("source"),
                    "chunk_index": row.get("chunk_index"),
                    "domain_name": row.get("domain_name"),
                    "memory_type": row.get("memory_type"),
                    "feedback_score": 0.0,
                    "supersession_score": 0.0,
                    "relation_supersession_score": 0.0,
                    "summary_relation_score": round(float(row.get("relation_weight") or 0.0), 6),
                    "summary_memory_id": row.get("summary_memory_id"),
                    "relation_type": row.get("relation_type"),
                    "text_preview": str(row.get("text") or "")[:320],
                }
            )
            if len(additions) >= max(1, int(limit)):
                break
        return [*source_context, *additions][: max(1, int(limit))]

    @staticmethod
    def _append_stale_context_notice(answer: str) -> str:
        notice = " Superseded context is available separately and should not override the current answer."
        if "superseded context is available" in answer.lower():
            return answer
        return f"{answer.rstrip()}{notice}"

    @classmethod
    def _source_diverse_context(
        cls,
        retrieval_pool: list[dict[str, Any]],
        primary_results: list[dict[str, Any]],
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        if not retrieval_pool or limit <= 0:
            return []
        primary_ids = {
            str(item.get("memory_id"))
            for item in primary_results
            if item.get("memory_id")
        }
        used_sources: set[str] = set()
        for item in primary_results:
            source_key = cls._source_diversity_key(item.get("source"))
            if source_key:
                used_sources.add(source_key)

        top_score = float(retrieval_pool[0].get("score") or 0.0)
        floor = top_score * 0.40 if top_score > 0.0 else top_score - 0.25
        out: list[dict[str, Any]] = []
        for row in retrieval_pool:
            if len(out) >= max(1, int(limit)):
                break
            memory_id = str(row.get("memory_id") or "")
            if not memory_id or memory_id in primary_ids:
                continue
            source_key = cls._source_diversity_key(row.get("source"))
            if not source_key or source_key in used_sources:
                continue
            if float(row.get("score") or 0.0) < floor:
                continue
            used_sources.add(source_key)
            compact = compact_evidence(row)
            compact["score"] = row.get("score")
            compact["text_match_score"] = row.get("text_match_score")
            out.append(compact)
        return out

    @staticmethod
    def _source_diversity_key(source: str | None) -> str:
        if not source:
            return ""
        normalized = str(source).replace("\\", "/").strip().lower()
        if not normalized:
            return ""
        return normalized.rsplit("/", 1)[-1] or normalized

    @staticmethod
    def _source_version(source: str | None) -> tuple[str | None, int]:
        if not source:
            return None, 0
        path = Path(str(source))
        lowered_parts = [part.lower() for part in path.parts]
        for index, candidate in enumerate(lowered_parts):
            parts = candidate.split("_")
            if parts and parts[-1].startswith("v") and parts[-1][1:].isdigit():
                group_root = "_".join(parts[:-1]).strip("_") or path.stem.lower()
                if index < len(lowered_parts) - 1:
                    group = f"{group_root}/{path.stem.lower()}"
                else:
                    group = group_root
                return group, int(parts[-1][1:])
        candidate = path.stem.lower()
        parts = candidate.split("_")
        if parts and parts[-1].startswith("v") and parts[-1][1:].isdigit():
            group = "_".join(parts[:-1]).strip("_") or path.stem.lower()
            return group, int(parts[-1][1:])
        return None, 0

    @staticmethod
    def _tokens(text: str) -> set[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
        return {token for token in cleaned.split() if len(token) > 1}

    @staticmethod
    def _stem_token(token: str) -> str:
        token = str(token or "").lower().strip()
        if len(token) > 5 and token.endswith("ies"):
            return token[:-3] + "y"
        if len(token) > 5 and token.endswith("ing"):
            return token[:-3]
        if len(token) > 4 and token.endswith("es"):
            return token[:-2]
        if len(token) > 3 and token.endswith("s"):
            return token[:-1]
        return token

    @staticmethod
    def _expanded_tokens(text: str) -> set[str]:
        lower = str(text or "").lower()
        tokens = {MemoryPipeline._stem_token(token) for token in MemoryPipeline._tokens(lower)}
        if "who am i" in lower or "what am i" in lower or "my identity" in lower or "my name" in lower:
            tokens.update({"identity", "name", "user", "primary", "called", "agent", "hermes", "victor"})
        if tokens & {"contradict", "contradiction", "conflict"} or "facts contradict" in lower:
            tokens.update({"contradict", "contradiction", "conflict", "protect", "protective", "correction", "stale", "csd"})
        if tokens & {"consolidation", "consolidate"} or "consolidation work" in lower:
            tokens.update({"consolidation", "consolidate", "summary", "summarize", "summarizes", "original", "preserve", "source"})
        if "previous question" in lower or "remember previous" in lower:
            tokens.update({"session", "history", "turn", "context", "previous", "question", "remember"})
        if tokens & {"maintain", "maintains"}:
            tokens.update({"maintain", "maintains"})
        return tokens

    @staticmethod
    def _needs_broad_lexical_scan(query: str) -> bool:
        lower = str(query or "").lower()
        if any(any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token) for token in MemoryPipeline._tokens(lower)):
            return True
        if any(term in lower for term in ("routing tag", "contact code", "private key", "signing key")):
            return True
        return any(
            term in lower
            for term in (
                "who am i",
                "who i am",
                "what am i",
                "my identity",
                "my name",
                "previous question",
                "remember previous",
                "session history",
                "facts contradict",
                "contradiction",
                "consolidation",
                "consolidate",
            )
        )

    @staticmethod
    def _authority_query_intent(query: str) -> bool:
        lower = str(query or "").lower()
        return any(
            term in lower
            for term in (
                "current",
                "now",
                "latest",
                "correct",
                "correction",
                "final",
                "active",
                "superseded",
                "outdated",
                "stale",
                "policy",
                "preference",
                "rule",
                "should",
                "must",
                "allowed",
                "can i",
                "can the",
                "only when",
                "instead",
                "change",
            )
        )

    def _with_lexical_backfill(
        self,
        items: list[RecallItem],
        query: str,
        namespaces: list[str] | None = None,
        limit: int = 200,
    ) -> list[RecallItem]:
        seen = {item.memory_id for item in items}
        additions: list[tuple[float, RecallItem]] = []
        for row in self.db.list_memory_vectors(include_deprecated=False, namespaces=namespaces):
            memory_id = str(row.get("id") or "")
            if not memory_id or memory_id in seen:
                continue
            affinity = self._text_affinity(query, str(row.get("text") or ""))
            if affinity < 0.45:
                continue
            additions.append(
                (
                    affinity,
                    RecallItem(
                        memory_id=memory_id,
                        domain_id=row.get("domain_id"),
                        text=str(row.get("text") or ""),
                        memory_type=str(row.get("memory_type") or "semantic_note"),
                        score=max(0.25, min(1.0, affinity)),
                        importance=float(row.get("importance") or 0.0),
                        stability=float(row.get("stability") or 0.0),
                        namespace=normalize_namespace(row.get("namespace")),
                        deprecated=bool(row.get("deprecated")),
                    ),
                )
            )
        additions.sort(key=lambda item: item[0], reverse=True)
        return [*items, *(item for _affinity, item in additions[: max(0, int(limit) - len(items))])]

    def _with_authoritative_replacements(self, items: list[RecallItem], query_embedding: list[float]) -> list[RecallItem]:
        seed_ids = [item.memory_id for item in items if item.memory_id]
        if not seed_ids:
            return items
        authority = self._authority_status_for_candidates(seed_ids)
        authoritative_ids: list[str] = []
        for item in authority.values():
            for memory_id in item.get("authoritative_memory_ids") or []:
                if memory_id not in authoritative_ids:
                    authoritative_ids.append(memory_id)
        existing = {item.memory_id for item in items}
        missing = [memory_id for memory_id in authoritative_ids if memory_id not in existing]
        if not missing:
            return items
        additions: list[RecallItem] = []
        for row in self.db.memory_vectors_by_ids(missing, include_deprecated=False):
            additions.append(
                RecallItem(
                    memory_id=row["id"],
                    domain_id=row.get("domain_id"),
                    text=str(row.get("text") or ""),
                    memory_type=str(row.get("memory_type") or "semantic_note"),
                    score=cosine(query_embedding, row["embedding"]),
                    importance=float(row.get("importance") or 0.0),
                    stability=float(row.get("stability") or 0.0),
                    namespace=normalize_namespace(row.get("namespace")),
                    deprecated=bool(row.get("deprecated")),
                )
            )
        return [*items, *additions]

    def _authority_status_for_candidates(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [str(memory_id).strip() for memory_id in memory_ids if str(memory_id or "").strip()]
        if not ids:
            return {}
        graph = self.db.authority_graph_for_memories(ids)
        incoming: dict[str, list[dict[str, Any]]] = {}
        outgoing: dict[str, list[dict[str, Any]]] = {}
        relation_types_by_id: dict[str, set[str]] = {}
        for relation in graph.get("relations") or []:
            source_id = str(relation.get("source_memory_id") or "")
            target_id = str(relation.get("target_memory_id") or "")
            relation_type = str(relation.get("relation_type") or "")
            if not source_id or not target_id:
                continue
            incoming.setdefault(target_id, []).append(relation)
            outgoing.setdefault(source_id, []).append(relation)
            relation_types_by_id.setdefault(source_id, set()).add(relation_type)
            relation_types_by_id.setdefault(target_id, set()).add(relation_type)

        def latest(memory_id: str, visiting: set[str] | None = None) -> tuple[set[str], int]:
            visiting = set(visiting or set())
            if memory_id in visiting:
                return {memory_id}, 0
            visiting.add(memory_id)
            replacers = [
                relation
                for relation in incoming.get(memory_id) or []
                if str(relation.get("relation_type") or "") in {"supersedes", "corrects"}
            ]
            if not replacers:
                return {memory_id}, 0
            latest_ids: set[str] = set()
            max_depth = 0
            for relation in replacers:
                source_id = str(relation.get("source_memory_id") or "")
                if not source_id:
                    continue
                source_latest, depth = latest(source_id, visiting)
                latest_ids.update(source_latest)
                max_depth = max(max_depth, depth + 1)
            return latest_ids or {memory_id}, max_depth

        out: dict[str, dict[str, Any]] = {}
        for memory_id in ids:
            authoritative_ids, depth = latest(memory_id)
            superseded_by = sorted(item for item in authoritative_ids if item != memory_id)
            supersedes = sorted(
                {
                    str(relation.get("target_memory_id"))
                    for relation in outgoing.get(memory_id, [])
                    if relation.get("target_memory_id")
                    and str(relation.get("relation_type") or "") in {"supersedes", "corrects"}
                }
            )
            if superseded_by:
                state = "superseded"
                authority_score = -0.75
            elif supersedes:
                state = "current"
                authority_score = 0.45
            else:
                state = "standalone"
                authority_score = 0.0
            out[memory_id] = {
                "authority_state": state,
                "authoritative_memory_ids": sorted(authoritative_ids),
                "superseded_by_memory_ids": superseded_by,
                "supersedes_memory_ids": supersedes,
                "correction_chain_depth": int(depth),
                "relation_types": sorted(relation_types_by_id.get(memory_id, set())),
                "authority_score": authority_score,
            }
        return out

    @staticmethod
    def _normalize_priority(priority: str | None) -> str:
        value = str(priority or "normal").strip().lower()
        aliases = {
            "": "normal",
            "default": "normal",
            "medium": "normal",
            "important": "high",
            "urgent": "critical",
        }
        value = aliases.get(value, value)
        return value if value in {"low", "normal", "high", "critical"} else "normal"

    @staticmethod
    def _apply_priority(signal, priority: str) -> None:
        if priority == "low":
            signal.importance = min(signal.importance, 0.35)
            return
        if priority == "high":
            signal.importance = max(signal.importance, 0.8)
            signal.confidence = max(signal.confidence, 0.75)
            signal.user_instruction = max(signal.user_instruction, 0.7)
        elif priority == "critical":
            signal.importance = max(signal.importance, 0.95)
            signal.confidence = max(signal.confidence, 0.9)
            signal.user_instruction = 1.0

    @staticmethod
    def _apply_clc_override(decision: CLCDecision, priority: str, force_clc_state: str | None) -> CLCDecision:
        forced = str(force_clc_state or "").strip().upper()
        if forced:
            if forced not in STATE_UPDATE_STRENGTH:
                raise ValueError(f"Unsupported force_clc_state: {force_clc_state}")
            return CLCDecision(forced, STATE_UPDATE_STRENGTH[forced], "forced_by_request")
        if priority in {"high", "critical"} and decision.state == "IGNORE":
            return CLCDecision("FOCUS", STATE_UPDATE_STRENGTH["FOCUS"], f"priority_{priority}_override")
        return decision

    @staticmethod
    def _normalize_retrieval_weights(weights: dict[str, Any] | None) -> dict[str, float]:
        normalized = dict(DEFAULT_RETRIEVAL_WEIGHTS)
        for key, value in (weights or {}).items():
            if key not in normalized:
                continue
            try:
                normalized[key] = float(value)
            except (TypeError, ValueError):
                continue
        return normalized

    def _append_log(self, payload: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")

    def _ensure_embedding_signature(self, embedding: list[float]) -> dict[str, Any]:
        descriptor = self._canonical_embedding_signature(self.encoder.descriptor())
        descriptor["embedding_dim"] = len(embedding)
        existing = self.db.get_runtime_state("embedding_signature")
        dims = self.db.vector_dimensions()
        if existing is None:
            if dims and any(dim != len(embedding) for dim in dims):
                raise RuntimeError(
                    "Existing memory DB contains vectors with dimensions "
                    f"{dims}, but current encoder produces {len(embedding)}d vectors. "
                    "Use a fresh DB before changing embedding models."
                )
            self.db.set_runtime_state("embedding_signature", descriptor)
            return descriptor
        existing_c = self._canonical_embedding_signature(existing)
        if not self._embedding_signatures_compatible(existing_c, descriptor):
            raise RuntimeError(
                "Embedding runtime signature mismatch detected. "
                f"Existing={existing_c}; current={descriptor}. "
                "Use a fresh DB before changing embedding models."
            )
        return descriptor

    @staticmethod
    def _canonical_embedding_signature(signature: dict[str, Any]) -> dict[str, Any]:
        out = dict(signature or {})
        backend = str(out.get("backend") or "").strip().lower().replace("-", "_")
        if backend in ("gguf", "llama"):
            backend = "llama_cpp"
        out["backend"] = backend
        out["model_name"] = Path(str(out.get("model_name") or "")).name
        model_path = out.get("model_path")
        if model_path:
            out["model_path"] = str(model_path).replace("\\", "/")
        else:
            out["model_path"] = None
        out["embedding_dim"] = int(out.get("embedding_dim") or 0)
        return out

    @staticmethod
    def _embedding_signatures_compatible(existing: dict[str, Any], current: dict[str, Any]) -> bool:
        if int(existing.get("embedding_dim") or 0) != int(current.get("embedding_dim") or 0):
            return False
        if str(existing.get("model_name") or "") != str(current.get("model_name") or ""):
            return False
        existing_backend = str(existing.get("backend") or "")
        current_backend = str(current.get("backend") or "")
        gguf_backends = {"llama_cpp", "wsl_llama_cpp"}
        if existing_backend in gguf_backends and current_backend in gguf_backends:
            return True
        if existing_backend != current_backend:
            return False
        return existing.get("model_path") == current.get("model_path")
