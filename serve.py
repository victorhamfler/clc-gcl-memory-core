from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.agent_planner import plan_memory_actions
from core.chunking import chunk_text
from core.config import load_config, resolve_project_path
from core.consolidation import consolidation_plan, create_consolidation_summaries
from core.controller_context import build_adaptive_memory_context
from core.learning import learn_from_document, learn_from_text
from core.maintenance import improvement_plan, memory_review, record_memory_improvement, weak_memories
from core.outcome_log import OutcomeLogger
from core.adaptive_behavior import normalize_adaptive_behavior_config
from core.adaptive_residual_shadow import adaptive_residual_shadow_advisories
from core.adaptive_behavior_shadow import adaptive_behavior_shadow_advisories
from core.answer_behavior_shadow import normalize_resolver_shadow_config, resolver_shadow_actions
from core.runtime import create_pipeline, pipeline_config_view, pipeline_stats
from core.selector_runtime import (
    apply_retrieval_explanation_guard,
    build_policy_selector,
    selector_config_view,
)


ROOT = Path(__file__).resolve().parent
FEEDBACK_RATINGS = {
    "excellent": 2.0,
    "useful": 1.0,
    "good": 1.0,
    "ok": 0.25,
    "neutral": 0.0,
    "bridge_relevant": 1.0,
    "cross_domain_bridge": 1.0,
    "ogcf_bridge": 1.0,
    "ogcf_geometry": 1.0,
    "bridge_geometry": 1.0,
    "loop_overload": 1.0,
    "memory_maintenance": 1.0,
    "dedup": 1.0,
    "duplicate": 1.0,
    "bridge_maintenance": 1.0,
    "missing_source": -0.5,
    "wrong_domain": -0.75,
    "stale": -0.75,
    "ogcf_false_positive": -1.0,
    "bridge_irrelevant": -0.75,
    "ordinary_lookup": -0.75,
    "ordinary_fact": -0.75,
    "unrelated_bridge": -0.75,
    "no_ogcf_pressure": -0.75,
    "answer_correct": 1.0,
    "answer_good_citation": 1.0,
    "answer_bridge_warning_useful": 1.0,
    "answer_stale": -0.75,
    "answer_wrong_scope": -0.75,
    "answer_missing_support": -0.75,
    "answer_overconfident": -0.75,
    "answer_bad_citation": -0.75,
    "answer_conflict_not_disclosed": -1.0,
    "answer_bridge_warning_noise": -0.5,
    "wrong": -1.0,
    "bad": -1.0,
}

ANSWER_FEEDBACK_LABELS = {
    "answer_correct",
    "answer_stale",
    "answer_wrong_scope",
    "answer_missing_support",
    "answer_overconfident",
    "answer_good_citation",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_useful",
    "answer_bridge_warning_noise",
}


def label_from_rating(rating: float) -> str:
    if rating >= 1.5:
        return "excellent"
    if rating > 0.0:
        return "useful"
    if rating == 0.0:
        return "neutral"
    if rating <= -0.75:
        return "stale"
    return "negative"


def is_answer_feedback_label(label: str) -> bool:
    return label in ANSWER_FEEDBACK_LABELS or label.startswith("answer_")


class MemoryApi:
    def __init__(self, root: Path, db_path: Path | None = None):
        self.root = root
        self.root_config = load_config(root)
        self.pipeline = create_pipeline(root, db_path=db_path)
        self.outcome_logger = OutcomeLogger(root, self.root_config)

    def close(self) -> None:
        self.pipeline.close()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "database": str(self.pipeline.db.db_path),
            "embedding": self.pipeline.encoder.descriptor(),
        }

    def stats(self) -> dict[str, Any]:
        return pipeline_stats(self.pipeline)

    def config(self) -> dict[str, Any]:
        return {
            **pipeline_config_view(self.pipeline),
            "selector": selector_config_view(self.root, self.root_config),
            "resolver_shadow": normalize_resolver_shadow_config(self.root_config.get("resolver_shadow")),
            "adaptive_behavior": normalize_adaptive_behavior_config(self.root_config.get("adaptive_behavior")),
        }

    def _record_outcome(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        linked_operation_id: str | None = None,
    ) -> dict[str, Any]:
        return self.outcome_logger.record(event_type, payload, linked_operation_id=linked_operation_id)

    @staticmethod
    def _evidence_brief(rows: list[dict[str, Any]] | None, limit: int = 10) -> list[dict[str, Any]]:
        out = []
        for row in list(rows or [])[:limit]:
            out.append(
                {
                    "memory_id": row.get("memory_id"),
                    "rank": row.get("rank"),
                    "namespace": row.get("namespace"),
                    "source": row.get("source"),
                    "domain_name": row.get("domain_name"),
                    "memory_type": row.get("memory_type"),
                    "score": row.get("score"),
                    "cosine": row.get("cosine"),
                    "feedback_score": row.get("feedback_score"),
                    "usage_count": row.get("usage_count"),
                    "text_match_score": row.get("text_match_score"),
                    "intent_match_score": row.get("intent_match_score"),
                    "answer_type_score": row.get("answer_type_score"),
                    "authority_state": row.get("authority_state") or row.get("memory_state"),
                    "claim_scope_score": row.get("claim_scope_score"),
                    "identifier_match_score": row.get("identifier_match_score"),
                    "broad_generic_penalty": row.get("broad_generic_penalty"),
                    "scope_deflection_penalty": row.get("scope_deflection_penalty"),
                    "correction_relevance_score": row.get("correction_relevance_score"),
                    "correction_chain_score": row.get("correction_chain_score"),
                    "supersession_score": row.get("supersession_score"),
                    "relation_supersession_score": row.get("relation_supersession_score"),
                    "summary_relation_score": row.get("summary_relation_score"),
                    "stored_contradiction_score": row.get("stored_contradiction_score"),
                    "text": row.get("text") or row.get("text_preview"),
                }
            )
        return out

    def _selector_snapshot_from_rows(self, rows: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
        return build_adaptive_memory_context(
            root=self.root,
            config=self.root_config,
            payload=payload,
            retrieval_rows=rows,
            include_decision=True,
        ).selector_snapshot()

    def _adaptive_context_log_payload(self, adaptive_context, *, limit: int = 10) -> dict[str, Any]:
        snapshot = adaptive_context.selector_snapshot()
        return {
            "schema": "adaptive_memory_context/v1",
            "ok": bool(adaptive_context.ok),
            "selector_snapshot": snapshot,
            "features": adaptive_context.feature_dict() if adaptive_context.ok else {},
            "diagnostics": adaptive_context.diagnostics if adaptive_context.ok else {},
            "retrieval_context": self._evidence_brief(adaptive_context.retrieval_context, limit=limit),
            "ogcf_meta_present": bool(adaptive_context.ogcf_meta_present),
        }

    def _adaptive_context_from_payload(self, payload: dict[str, Any]):
        retrieval_rows = payload.get("retrieval_context")
        if not isinstance(retrieval_rows, list) and payload.get("query"):
            retrieval_rows = self.pipeline.retrieve(
                str(payload.get("query") or ""),
                top_k=max(1, int(payload.get("top_k") or 5)),
                namespace=str(payload.get("namespace") or "").strip() or None,
                include_global=bool(payload.get("include_global", True)),
            )
        return build_adaptive_memory_context(
            root=self.root,
            config=self.root_config,
            payload=payload,
            retrieval_rows=retrieval_rows if isinstance(retrieval_rows, list) else None,
            include_decision=True,
        )

    def _resolver_shadow_config(self) -> dict[str, Any]:
        raw = self.root_config.get("resolver_shadow")
        return normalize_resolver_shadow_config(raw if isinstance(raw, dict) else None)

    def _include_resolver_shadow(self, payload: dict[str, Any], cfg: dict[str, Any]) -> bool:
        if "include_resolver_shadow" in payload:
            return bool(payload.get("include_resolver_shadow"))
        return bool(cfg.get("enabled"))

    def _resolver_shadow_payload(
        self,
        *,
        query: str,
        asked: dict[str, Any],
        selector_snapshot: dict[str, Any],
        cfg: dict[str, Any],
    ) -> dict[str, Any]:
        return resolver_shadow_actions(
            query=query,
            answer=str(asked.get("answer") or ""),
            evidence=asked.get("evidence") or [],
            stale_context=asked.get("stale_context") or [],
            selector_snapshot=selector_snapshot,
            conflict=bool(asked.get("conflict")),
            config=cfg,
        )

    def _adaptive_behavior_shadow_config(self) -> dict[str, Any]:
        raw = self.root_config.get("adaptive_behavior")
        return normalize_adaptive_behavior_config(raw if isinstance(raw, dict) else None)

    def _include_adaptive_behavior_shadow(self, payload: dict[str, Any], cfg: dict[str, Any]) -> bool:
        if "include_adaptive_behavior_shadow" in payload:
            return bool(payload.get("include_adaptive_behavior_shadow"))
        return bool((cfg.get("shadow") or {}).get("enabled"))

    def _log_adaptive_behavior_shadow(self, payload: dict[str, Any], cfg: dict[str, Any]) -> bool:
        if "log_adaptive_behavior_shadow" in payload:
            return bool(payload.get("log_adaptive_behavior_shadow"))
        return bool((cfg.get("shadow") or {}).get("include_in_outcome_log"))

    def _adaptive_behavior_shadow_payload(
        self,
        *,
        query: str,
        asked: dict[str, Any],
        adaptive_context,
        resolver_shadow: dict[str, Any] | None,
        cfg: dict[str, Any],
    ) -> dict[str, Any]:
        return adaptive_behavior_shadow_advisories(
            query=query,
            answer=str(asked.get("answer") or ""),
            evidence=asked.get("evidence") or [],
            stale_context=asked.get("stale_context") or [],
            adaptive_context=adaptive_context,
            resolver_shadow=resolver_shadow,
            config=cfg,
        )

    def _include_adaptive_residual_shadow(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("include_adaptive_residual_shadow"))

    def _log_adaptive_residual_shadow(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("log_adaptive_residual_shadow"))

    def _adaptive_residual_shadow_payload(
        self,
        *,
        query: str,
        asked: dict[str, Any],
        adaptive_behavior_shadow: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return adaptive_residual_shadow_advisories(
            root=self.root,
            query=query,
            answer=str(asked.get("answer") or ""),
            adaptive_behavior_shadow=adaptive_behavior_shadow,
        )

    def selector_decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        adaptive_context = self._adaptive_context_from_payload(payload)
        if not adaptive_context.ok:
            return adaptive_context.selector_snapshot()
        decision = adaptive_context.decision
        response = {
            "ok": True,
            "selector": selector_config_view(self.root, self.root_config),
            "decision": {
                "policy": decision.policy,
                "action": decision.action,
                "reason": decision.reason,
                "confidence": decision.confidence,
            },
        }
        if adaptive_context.retrieval_context:
            response["selector_context"] = adaptive_context.selector_context()
        return response

    def selector_explain(self, payload: dict[str, Any]) -> dict[str, Any]:
        selector = build_policy_selector(self.root, self.root_config)
        adaptive_context = self._adaptive_context_from_payload(payload)
        if not adaptive_context.ok:
            return adaptive_context.selector_snapshot()
        top_k = payload.get("top_k")
        explanation = selector.explain(adaptive_context.features, top_k=None if top_k is None else int(top_k))
        if adaptive_context.retrieval_context:
            explanation = apply_retrieval_explanation_guard(
                explanation,
                adaptive_context.features,
                adaptive_context.diagnostics,
            )
        response = {
            "ok": True,
            "selector": selector_config_view(self.root, self.root_config),
            "explanation": explanation,
        }
        if adaptive_context.retrieval_context:
            response["selector_context"] = adaptive_context.selector_context()
        log_status = self._record_outcome(
            "selector_explain",
            {
                "request": {
                    "query": payload.get("query"),
                    "namespace": payload.get("namespace"),
                    "include_global": payload.get("include_global", True),
                    "condition_name": payload.get("condition_name"),
                    "top_k": payload.get("top_k"),
                },
                "selector": response.get("selector"),
                "explanation": explanation,
                "selector_context": self._adaptive_context_log_payload(adaptive_context, limit=10),
            },
        )
        response["operation_id"] = log_status["operation_id"]
        response["outcome_log_logged"] = bool(log_status["logged"])
        return response

    def memory_usage(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "memory_usage": self.pipeline.db.memory_usage(
                limit=max(1, int(payload.get("limit") or 20)),
                namespace=str(payload.get("namespace") or "").strip() or None,
                include_global=bool(payload.get("include_global", True)),
                memory_id=str(payload.get("memory_id") or "").strip() or None,
            ),
        }

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        return {
            "ok": True,
            "session": self.pipeline.db.create_session(
                agent_id=str(payload.get("agent_id") or "default").strip() or "default",
                title=str(payload.get("title") or "").strip() or None,
                metadata=metadata,
                session_id=str(payload.get("session_id") or "").strip() or None,
            ),
        }

    def sessions(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(payload.get("agent_id") or "").strip() or None
        limit = max(1, int(payload.get("limit") or 20))
        return {"ok": True, "sessions": self.pipeline.db.list_sessions(agent_id=agent_id, limit=limit)}

    def session_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("POST /session_history requires JSON field 'session_id'")
        limit = max(1, int(payload.get("limit") or 50))
        session = self.pipeline.db.get_session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return {
            "ok": True,
            "session": session,
            "turns": self.pipeline.db.session_history(session_id, limit=limit),
            "session_memory": self.pipeline.db.list_session_memory(session_id),
        }

    def session_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("POST /session_memory requires JSON field 'session_id'")
        session = self.pipeline.db.get_session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        if "key" in payload or "value" in payload:
            key = str(payload.get("key") or "").strip()
            value = str(payload.get("value") or "").strip()
            if not key:
                raise ValueError("POST /session_memory write requires JSON field 'key'")
            if not value:
                raise ValueError("POST /session_memory write requires JSON field 'value'")
            metadata = payload.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                raise ValueError("'metadata' must be a JSON object when provided")
            memory = self.pipeline.db.upsert_session_memory(session_id, key, value, metadata=metadata)
            return {
                "ok": True,
                "mode": "session_memory_write",
                "session": session,
                "memory": memory,
                "session_memory": self.pipeline.db.list_session_memory(
                    session_id, limit=max(1, int(payload.get("limit") or 20))
                ),
            }
        return {
            "ok": True,
            "mode": "session_memory_read",
            "session": session,
            "session_memory": self.pipeline.db.list_session_memory(session_id, limit=max(1, int(payload.get("limit") or 20))),
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or payload.get("content") or "").strip()
        if not text:
            raise ValueError("POST /ingest requires JSON field 'text' or 'content'")
        memory = self.pipeline.ingest(
            text,
            source=str(payload.get("source") or "").strip() or None,
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "").strip() or None,
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
            domain=str(payload.get("domain") or payload.get("domain_name") or "").strip() or None,
            memory_type=str(payload.get("memory_type") or "").strip() or None,
        )
        return {"ok": True, "mode": "ingest", "memory": memory, **memory}

    def teach(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or payload.get("content") or "").strip()
        if not text:
            raise ValueError("POST /teach requires JSON field 'text' or 'content'")
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        return self.pipeline.teach(
            text,
            source=str(payload.get("source") or "").strip() or None,
            session_id=str(payload.get("session_id") or "").strip() or None,
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            store_session=bool(payload.get("store_session", True)),
            metadata=metadata,
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "").strip() or None,
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
            domain=str(payload.get("domain") or payload.get("domain_name") or "").strip() or None,
            memory_type=str(payload.get("memory_type") or "").strip() or None,
        )

    def correct(self, payload: dict[str, Any]) -> dict[str, Any]:
        correction = str(payload.get("correction") or payload.get("corrected_text") or payload.get("text") or "").strip()
        if not correction:
            raise ValueError("POST /correct requires JSON field 'correction', 'corrected_text', or 'text'")
        target_memory_ids = payload.get("target_memory_ids")
        if target_memory_ids is None:
            target_memory_ids = payload.get("memory_ids")
        if target_memory_ids is None:
            for alias in ("target_memory_id", "memory_id"):
                if payload.get(alias) is not None:
                    target_memory_ids = [payload.get(alias)]
                    break
        if target_memory_ids is None:
            target_memory_ids = []
        if isinstance(target_memory_ids, str):
            target_memory_ids = [target_memory_ids]
        if not isinstance(target_memory_ids, list):
            raise ValueError("'target_memory_ids' or 'memory_ids' must be a JSON list when provided")
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        return self.pipeline.correct(
            correction,
            target_memory_ids=[str(item) for item in target_memory_ids],
            target_query=str(payload.get("target_query") or payload.get("query") or "").strip() or None,
            top_k=max(1, int(payload.get("top_k") or 5)),
            source=str(payload.get("source") or "").strip() or None,
            session_id=str(payload.get("session_id") or "").strip() or None,
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            store_session=bool(payload.get("store_session", True)),
            stale_label=str(payload.get("stale_label") or "stale").strip().lower() or "stale",
            stale_rating=float(payload.get("stale_rating") if payload.get("stale_rating") is not None else -0.75),
            relation_type=str(payload.get("relation_type") or "corrects").strip().lower() or "corrects",
            metadata=metadata,
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "high").strip() or "high",
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
            domain=str(payload.get("domain") or payload.get("domain_name") or "").strip() or None,
            memory_type=str(payload.get("memory_type") or "").strip() or None,
        )

    def ingest_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        structured_items = payload.get("items")
        if structured_items is None:
            structured_items = payload.get("memories")
        if structured_items is not None:
            return self._ingest_batch_items(payload, structured_items)
        raw_texts = payload.get("texts")
        source = str(payload.get("source") or "").strip() or None
        if raw_texts is None and payload.get("text") is not None:
            raw_texts = chunk_text(
                str(payload.get("text") or ""),
                max_words=int(payload.get("max_words") or 120),
                overlap_words=int(payload.get("overlap_words") or 20),
            )
        if not isinstance(raw_texts, list):
            raise ValueError("POST /ingest_batch requires JSON field 'texts', 'items', 'memories', or chunkable 'text'")
        if raw_texts and all(isinstance(item, dict) for item in raw_texts):
            return self._ingest_batch_items(payload, raw_texts)
        texts = [str(item or "") for item in raw_texts]
        return self.pipeline.ingest_batch(
            texts,
            source=source,
            limit=payload.get("limit"),
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "").strip() or None,
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
        )

    def _ingest_batch_items(self, payload: dict[str, Any], raw_items: Any) -> dict[str, Any]:
        if not isinstance(raw_items, list):
            raise ValueError("'items' or 'memories' must be a JSON list")
        limit = payload.get("limit")
        items = raw_items[: max(0, int(limit))] if limit is not None else raw_items
        default_namespace = str(payload.get("namespace") or "global").strip() or "global"
        default_source = str(payload.get("source") or "").strip() or None
        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        namespaces: dict[str, int] = {}
        for idx, item in enumerate(items):
            if isinstance(item, str):
                row = {"text": item}
            elif isinstance(item, dict):
                row = item
            else:
                errors.append({"batch_index": idx, "error": "item must be an object or string"})
                continue
            text = str(row.get("text") or row.get("content") or "").strip()
            if not text:
                skipped.append({"batch_index": idx, "reason": "empty_text"})
                continue
            namespace = str(row.get("namespace") or default_namespace).strip() or "global"
            source = str(row.get("source") or default_source or "").strip() or None
            try:
                if self.pipeline.db.memory_exists_text(text, namespace=namespace):
                    skipped.append({"batch_index": idx, "namespace": namespace, "reason": "duplicate_exact_text", "text_preview": text[:160]})
                    continue
                memory = self.pipeline.ingest(
                    text,
                    source=source,
                    namespace=namespace,
                    priority=str(row.get("priority") or payload.get("priority") or "").strip() or None,
                    force_clc_state=str(row.get("force_clc_state") or row.get("clc_state") or payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
                    domain=str(row.get("domain") or row.get("domain_name") or payload.get("domain") or payload.get("domain_name") or "").strip() or None,
                    memory_type=str(row.get("memory_type") or payload.get("memory_type") or "").strip() or None,
                )
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                self.pipeline.db.set_memory_source(
                    memory["memory_id"],
                    source,
                    int(row.get("chunk_index") if row.get("chunk_index") is not None else idx),
                    metadata={"namespace": namespace, "batch_index": idx, **metadata},
                )
                memory["batch_index"] = idx
                memory["source"] = source
                results.append(memory)
                namespaces[namespace] = namespaces.get(namespace, 0) + 1
            except Exception as exc:
                errors.append({"batch_index": idx, "namespace": namespace, "error": str(exc), "text_preview": text[:160]})
        self.pipeline.db.add_event(
            None,
            "batch_ingest",
            metadata={
                "source": default_source,
                "requested": len(raw_items),
                "accepted": len(items),
                "stored": len(results),
                "skipped": len(skipped),
                "errors": len(errors),
                "structured_items": True,
                "namespaces": namespaces,
            },
        )
        return {
            "ok": True,
            "mode": "ingest_batch",
            "structured_items": True,
            "requested": len(raw_items),
            "accepted": len(items),
            "stored": len(results),
            "skipped": len(skipped),
            "errors": len(errors),
            "partial_errors": bool(errors),
            "namespaces": namespaces,
            "results": results,
            "memories": results,
            "skipped_items": skipped,
            "error_items": errors,
        }

    def learn(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or payload.get("content") or "").strip()
        if not text:
            raise ValueError("POST /learn requires JSON field 'text' or 'content'")
        filters = payload.get("filters") or {}
        if not isinstance(filters, dict):
            raise ValueError("'filters' must be a JSON object when provided")
        filters = self._classification_filters(payload, filters)
        mock_facts = payload.get("mock_facts")
        if mock_facts is not None and not isinstance(mock_facts, list):
            raise ValueError("'mock_facts' must be a JSON list when provided")
        return learn_from_text(
            self.pipeline,
            text,
            self.root_config.get("llm") if isinstance(self.root_config.get("llm"), dict) else {},
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            session_id=str(payload.get("session_id") or "").strip() or None,
            source=str(payload.get("source") or "").strip() or None,
            mode=str(payload.get("mode") or "dry_run").strip() or "dry_run",
            filters=filters,
            mock_facts=mock_facts,
        )

    def learn_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or payload.get("text") or "").strip()
        if not content:
            raise ValueError("POST /learn/document requires JSON field 'content'")
        filters = payload.get("filters") or {}
        if not isinstance(filters, dict):
            raise ValueError("'filters' must be a JSON object when provided")
        filters = self._classification_filters(payload, filters)
        return learn_from_document(
            self.pipeline,
            title=str(payload.get("title") or "").strip(),
            content=content,
            llm_config=self.root_config.get("llm") if isinstance(self.root_config.get("llm"), dict) else {},
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            session_id=str(payload.get("session_id") or "").strip() or None,
            source=str(payload.get("source") or "").strip() or None,
            mode=str(payload.get("mode") or "dry_run").strip() or "dry_run",
            filters=filters,
            max_words=int(payload.get("max_words") or 350),
            overlap_words=int(payload.get("overlap_words") or 40),
            limit=payload.get("limit"),
        )

    def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or payload.get("question") or payload.get("q") or "").strip()
        if not query:
            raise ValueError("POST /retrieve requires JSON field 'query', 'question', or 'q'")
        top_k = max(1, int(payload.get("top_k") or 5))
        namespace = str(payload.get("namespace") or "global").strip() or "global"
        include_global = bool(payload.get("include_global", True))
        results = self.pipeline.retrieve(
            query,
            top_k=top_k,
            namespace=namespace,
            include_global=include_global,
        )
        return {
            "results": results,
            "namespace_warning": self._namespace_warning(results, namespace=namespace, include_global=include_global),
        }

    def authority(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_ids = payload.get("memory_ids")
        if raw_ids is None:
            raw_ids = payload.get("memory_id")
        if raw_ids is None:
            memory_ids = []
        elif isinstance(raw_ids, list):
            memory_ids = [str(item) for item in raw_ids]
        else:
            memory_ids = [str(raw_ids)]
        return self.pipeline.authority(
            memory_ids=memory_ids,
            query=str(payload.get("query") or "").strip() or None,
            top_k=max(1, int(payload.get("top_k") or 5)),
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            include_global=bool(payload.get("include_global", True)),
        )

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or payload.get("question") or payload.get("q") or "").strip()
        if not query:
            raise ValueError("POST /ask requires JSON field 'query', 'question', or 'q'")
        top_k = max(1, int(payload.get("top_k") or 5))
        namespace = str(payload.get("namespace") or "global").strip() or "global"
        include_global = bool(payload.get("include_global", True))
        asked = self.pipeline.ask(
            query,
            top_k=top_k,
            session_id=str(payload.get("session_id") or "").strip() or None,
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            store_session=bool(payload.get("store_session", True)),
            remember=bool(payload.get("remember", False)),
            memory_text=str(payload.get("memory_text") or "").strip() or None,
            namespace=namespace,
            include_global=include_global,
        )
        namespace_warning = self._namespace_warning(asked.get("evidence") or [], namespace=namespace, include_global=include_global)
        response = {
            "ok": True,
            **asked,
            "namespace_warning": namespace_warning,
        }
        adaptive_context = build_adaptive_memory_context(
            root=self.root,
            config=self.root_config,
            payload={**payload, "query": query},
            retrieval_rows=asked.get("raw_results") or [],
            include_decision=True,
        )
        selector_snapshot = adaptive_context.selector_snapshot()
        resolver_shadow_cfg = self._resolver_shadow_config()
        resolver_shadow = None
        if self._include_resolver_shadow(payload, resolver_shadow_cfg):
            resolver_shadow = self._resolver_shadow_payload(
                query=query,
                asked=asked,
                selector_snapshot=selector_snapshot,
                cfg={**resolver_shadow_cfg, "enabled": True},
            )
            response["resolver_shadow"] = resolver_shadow
        adaptive_behavior_cfg = self._adaptive_behavior_shadow_config()
        adaptive_behavior_shadow = None
        if self._include_adaptive_behavior_shadow(payload, adaptive_behavior_cfg):
            adaptive_behavior_shadow = self._adaptive_behavior_shadow_payload(
                query=query,
                asked=asked,
                adaptive_context=adaptive_context,
                resolver_shadow=resolver_shadow,
                cfg=adaptive_behavior_cfg,
            )
            response["adaptive_behavior_shadow"] = adaptive_behavior_shadow
        adaptive_residual_shadow = None
        if self._include_adaptive_residual_shadow(payload):
            if adaptive_behavior_shadow is None:
                adaptive_behavior_shadow = self._adaptive_behavior_shadow_payload(
                    query=query,
                    asked=asked,
                    adaptive_context=adaptive_context,
                    resolver_shadow=resolver_shadow,
                    cfg=adaptive_behavior_cfg,
                )
            adaptive_residual_shadow = self._adaptive_residual_shadow_payload(
                query=query,
                asked=asked,
                adaptive_behavior_shadow=adaptive_behavior_shadow,
            )
            response["adaptive_residual_shadow"] = adaptive_residual_shadow
        logged_selector_snapshot = selector_snapshot
        log_resolver_shadow = resolver_shadow if resolver_shadow_cfg.get("include_in_outcome_log") else None
        log_adaptive_behavior_shadow = (
            adaptive_behavior_shadow
            if adaptive_behavior_shadow and self._log_adaptive_behavior_shadow(payload, adaptive_behavior_cfg)
            else None
        )
        log_adaptive_residual_shadow = (
            adaptive_residual_shadow
            if adaptive_residual_shadow and self._log_adaptive_residual_shadow(payload)
            else None
        )
        log_status = self._record_outcome(
            "ask",
            {
                "request": {
                    "query": query,
                    "top_k": top_k,
                    "namespace": namespace,
                    "include_global": include_global,
                    "agent_id": payload.get("agent_id") or "default",
                    "session_id": payload.get("session_id"),
                    "store_session": payload.get("store_session", True),
                    "condition_name": payload.get("condition_name") or "hard_budget144",
                },
                "response": {
                    "answer": asked.get("answer"),
                    "confidence": asked.get("confidence"),
                    "conflict": asked.get("conflict"),
                    "session_id": asked.get("session_id"),
                    "agent_id": asked.get("agent_id"),
                    "namespace": asked.get("namespace"),
                    "namespace_warning": namespace_warning,
                    "evidence": self._evidence_brief(asked.get("evidence") or [], limit=10),
                    "raw_results": self._evidence_brief(asked.get("raw_results") or [], limit=10),
                    "source_context": self._evidence_brief(asked.get("source_context") or [], limit=10),
                    "stale_context": self._evidence_brief(asked.get("stale_context") or [], limit=10),
                },
                "selector_snapshot": logged_selector_snapshot,
                "adaptive_memory_context": self._adaptive_context_log_payload(adaptive_context, limit=10),
                **({"resolver_shadow": log_resolver_shadow} if log_resolver_shadow else {}),
                **({"adaptive_behavior_shadow": log_adaptive_behavior_shadow} if log_adaptive_behavior_shadow else {}),
                **({"adaptive_residual_shadow": log_adaptive_residual_shadow} if log_adaptive_residual_shadow else {}),
            },
        )
        response["operation_id"] = log_status["operation_id"]
        response["outcome_log_logged"] = bool(log_status["logged"])
        if bool(payload.get("include_selector_snapshot")):
            response["selector_snapshot"] = selector_snapshot
        return response

    @staticmethod
    def _classification_filters(payload: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        out = dict(filters)
        for key in ("memory_type", "domain", "domain_name"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                out[key] = str(value).strip()
        return out

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(payload.get("memory_id") or "").strip()
        label = str(payload.get("label") or "").strip().lower()
        rating = payload.get("rating")
        if not label and rating is None:
            raise ValueError("POST /feedback requires JSON field 'label' or numeric 'rating'")
        if not label:
            label = label_from_rating(float(rating))
        if rating is None:
            rating = FEEDBACK_RATINGS.get(label, 0.0)
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        linked_operation_id = str(
            payload.get("linked_operation_id") or payload.get("operation_id") or payload.get("outcome_id") or ""
        ).strip() or None
        requested_scope = str(
            payload.get("feedback_scope") or payload.get("target_type") or payload.get("scope") or ""
        ).strip().lower()
        answer_level = requested_scope in {"answer", "response"} or is_answer_feedback_label(label)
        if not memory_id and not answer_level:
            raise ValueError("POST /feedback requires JSON field 'memory_id' for memory-level feedback")
        if answer_level and not linked_operation_id:
            raise ValueError("POST /feedback answer-level feedback requires linked operation_id")
        feedback_metadata = dict(metadata or {})
        if linked_operation_id:
            feedback_metadata["linked_operation_id"] = linked_operation_id
        feedback_scope = "answer" if answer_level and not memory_id else "memory"
        if feedback_scope == "memory":
            feedback = self.pipeline.db.add_retrieval_feedback(
                memory_id=memory_id,
                label=label,
                query=str(payload.get("query") or "").strip() or None,
                rating=float(rating),
                rank=payload.get("rank"),
                retrieval_score=payload.get("retrieval_score"),
                notes=str(payload.get("notes") or "").strip() or None,
                metadata=feedback_metadata,
            )
            feedback["feedback_scope"] = "memory"
        else:
            selected_memory_ids = payload.get("selected_memory_ids")
            if selected_memory_ids is not None and not isinstance(selected_memory_ids, list):
                raise ValueError("'selected_memory_ids' must be a JSON array when provided")
            feedback = {
                "id": None,
                "memory_id": None,
                "feedback_scope": "answer",
                "label": label,
                "query": str(payload.get("query") or "").strip() or None,
                "rating": float(rating),
                "rank": None,
                "retrieval_score": None,
                "notes": str(payload.get("notes") or "").strip() or None,
                "metadata": feedback_metadata,
                "selected_memory_ids": selected_memory_ids or [],
            }
        log_status = self._record_outcome(
            "feedback",
            {
                "request": {
                    "memory_id": memory_id,
                    "feedback_scope": feedback_scope,
                    "label": label,
                    "rating": float(rating),
                    "query": payload.get("query"),
                    "rank": payload.get("rank"),
                    "retrieval_score": payload.get("retrieval_score"),
                    "notes": payload.get("notes"),
                    "linked_operation_id": linked_operation_id,
                    "selected_memory_ids": payload.get("selected_memory_ids"),
                    "answer": payload.get("answer"),
                    "answer_summary": payload.get("answer_summary"),
                },
                "feedback": feedback,
            },
            linked_operation_id=linked_operation_id,
        )
        if feedback_scope == "answer":
            feedback["id"] = log_status["operation_id"]
        return {
            "ok": True,
            "operation_id": log_status["operation_id"],
            "linked_operation_id": linked_operation_id,
            "outcome_log_logged": bool(log_status["logged"]),
            "feedback": feedback,
        }

    def feedback_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_rating = payload.get("max_rating")
        return {
            "ok": True,
            "feedback": self.pipeline.db.recent_feedback(
                limit=max(1, int(payload.get("limit") or 50)),
                label=str(payload.get("label") or "").strip().lower() or None,
                memory_id=str(payload.get("memory_id") or "").strip() or None,
                max_rating=None if max_rating is None or str(max_rating).strip() == "" else float(max_rating),
            ),
        }

    def consolidation_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        return consolidation_plan(
            self.pipeline.db,
            min_domain_memories=max(1, int(payload.get("min_domain_memories") or payload.get("min") or 4)),
            max_candidates_per_domain=max(1, int(payload.get("max_candidates_per_domain") or payload.get("max") or 8)),
            namespace=str(payload.get("namespace") or "").strip() or None,
            include_global=bool(payload.get("include_global", False)),
        )

    def consolidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_groups = payload.get("max_groups", payload.get("groups"))
        dry_run = bool(payload.get("dry_run") or str(payload.get("mode") or "").strip().lower() in {"dry_run", "plan"})
        if dry_run:
            plan = consolidation_plan(
                self.pipeline.db,
                min_domain_memories=max(1, int(payload.get("min_domain_memories") or payload.get("min") or 4)),
                max_candidates_per_domain=max(1, int(payload.get("max_candidates_per_domain") or payload.get("max") or 8)),
                namespace=str(payload.get("namespace") or "").strip() or None,
                include_global=bool(payload.get("include_global", False)),
            )
            return {**plan, "mode": "dry_run", "dry_run": True, "created": 0}
        return create_consolidation_summaries(
            self.pipeline,
            min_domain_memories=max(1, int(payload.get("min_domain_memories") or payload.get("min") or 4)),
            max_candidates_per_domain=max(1, int(payload.get("max_candidates_per_domain") or payload.get("max") or 8)),
            max_groups=None if max_groups is None else max(0, int(max_groups)),
            namespace=str(payload.get("namespace") or "").strip() or None,
            include_global=bool(payload.get("include_global", False)),
        )

    def consolidation_sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary_memory_id = str(payload.get("summary_memory_id") or payload.get("memory_id") or "").strip()
        if not summary_memory_id:
            raise ValueError("POST /consolidation_sources requires JSON field 'summary_memory_id'")
        return {
            "ok": True,
            "summary_memory_id": summary_memory_id,
            "sources": self.pipeline.db.summarized_memories_for_sources(
                [summary_memory_id],
                limit=max(1, int(payload.get("limit") or 20)),
            ),
        }

    def memory_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return memory_review(
            self.pipeline.db,
            weak_limit=max(1, int(payload.get("weak_limit") or payload.get("limit") or 8)),
            namespace=str(payload.get("namespace") or "").strip() or None,
            include_global=bool(payload.get("include_global", False)),
        )

    def memory_weak(self, payload: dict[str, Any]) -> dict[str, Any]:
        include_resolved = bool(payload.get("include_resolved") or payload.get("resolved") or payload.get("all"))
        resolved_only = bool(payload.get("resolved_only"))
        rows = weak_memories(
            self.pipeline.db,
            limit=max(1, int(payload.get("limit") or 10)),
            include_resolved=include_resolved or resolved_only,
            namespace=str(payload.get("namespace") or "").strip() or None,
            include_global=bool(payload.get("include_global", False)),
        )
        if resolved_only:
            rows = [item for item in rows if item.get("resolved")]
        return {
            "ok": True,
            "include_resolved": include_resolved or resolved_only,
            "resolved_only": resolved_only,
            "weak_memories": rows,
        }

    def memory_improve(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(payload.get("memory_id") or "").strip()
        note = str(payload.get("note") or payload.get("text") or "").strip()
        if not memory_id:
            return improvement_plan(
                self.pipeline.db,
                limit=max(1, int(payload.get("limit") or 5)),
                namespace=str(payload.get("namespace") or "").strip() or None,
                include_global=bool(payload.get("include_global", False)),
            )
        if not note:
            return improvement_plan(
                self.pipeline.db,
                memory_id=memory_id,
                limit=1,
                namespace=str(payload.get("namespace") or "").strip() or None,
                include_global=bool(payload.get("include_global", False)),
            )
        return record_memory_improvement(
            self.pipeline,
            memory_id,
            note,
            agent_id=str(payload.get("agent_id") or "default").strip() or "default",
            session_id=str(payload.get("session_id") or "").strip() or None,
            namespace=str(payload.get("namespace") or "global").strip() or "global",
        )

    def migration_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        namespace = str(payload.get("namespace") or "global").strip() or "global"
        include_global = bool(payload.get("include_global", True))
        top_k = max(1, int(payload.get("top_k") or 3))
        stats = self.stats()
        smoke = None
        if query:
            results = self.pipeline.retrieve(query, top_k=top_k, namespace=namespace, include_global=include_global)
            smoke = {
                "query": query,
                "namespace": namespace,
                "include_global": include_global,
                "result_count": len(results),
                "top_memory_ids": [item.get("memory_id") for item in results[:top_k]],
                "namespace_warning": self._namespace_warning(results, namespace=namespace, include_global=include_global),
            }
        return {
            "ok": True,
            "mode": "migration_validate",
            "database": stats.get("database"),
            "memories": stats.get("memories"),
            "domains": stats.get("domains"),
            "vector_dimensions": stats.get("vector_dimensions"),
            "embedding_signature": stats.get("embedding_signature"),
            "namespaces_detail": stats.get("namespaces_detail"),
            "smoke": smoke,
        }

    def agent_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        instruction = str(payload.get("instruction") or payload.get("text") or "").strip()
        mock_plan = payload.get("mock_plan")
        llm_config = self.root_config.get("llm") if isinstance(self.root_config.get("llm"), dict) else {}
        if mock_plan is not None:
            llm_config = {**llm_config, "enabled": True, "provider": "mock", "mock_plan": mock_plan}
        return plan_memory_actions(
            instruction,
            llm_config,
            stats=self.stats(),
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            context=payload.get("context") if isinstance(payload.get("context"), dict) else None,
        )

    def _namespace_warning(self, results: list[dict[str, Any]], namespace: str, include_global: bool) -> dict[str, Any] | None:
        if results:
            return None
        counts = self.pipeline.db.namespace_counts()
        if not counts:
            return None
        searched = self._namespace_scope(namespace, include_global=include_global)
        outside = [item for item in counts if item.get("namespace") not in searched and int(item.get("count") or 0) > 0]
        searched_count = sum(int(item.get("count") or 0) for item in counts if item.get("namespace") in searched)
        if not outside or searched_count > 0:
            return None
        return {
            "warning": "No evidence found in the searched namespace scope, but other namespaces contain memories.",
            "searched_namespaces": searched,
            "available_namespaces": outside,
            "hint": "Pass the correct namespace, set namespace='global' after migration, or run /migration_validate.",
        }

    @staticmethod
    def _namespace_scope(namespace: str, include_global: bool) -> list[str]:
        normalized = str(namespace or "global").strip() or "global"
        if include_global and normalized != "global":
            return ["global", normalized]
        return [normalized]


def make_handler(api: MemoryApi):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CLCGCLMemory/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/health":
                    self._send_json(200, api.health())
                elif path == "/stats":
                    self._send_json(200, api.stats())
                elif path == "/config":
                    self._send_json(200, api.config())
                elif path == "/sessions":
                    self._send_json(200, api.sessions(self._query_payload(parsed.query)))
                elif path == "/memory_usage":
                    self._send_json(200, api.memory_usage(self._query_payload(parsed.query)))
                elif path == "/feedback":
                    self._send_json(200, api.feedback_list(self._query_payload(parsed.query)))
                elif path == "/migration_validate":
                    self._send_json(200, api.migration_validate(self._query_payload(parsed.query)))
                else:
                    self._send_json(404, self._unknown_endpoint(path))
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/ingest":
                    self._send_json(200, api.ingest(payload))
                elif path == "/ingest_batch":
                    self._send_json(200, api.ingest_batch(payload))
                elif path == "/teach":
                    self._send_json(200, api.teach(payload))
                elif path == "/correct":
                    self._send_json(200, api.correct(payload))
                elif path in {"/retrieve", "/query"}:
                    self._send_json(200, api.retrieve(payload))
                elif path == "/learn":
                    self._send_json(200, api.learn(payload))
                elif path == "/learn/document":
                    self._send_json(200, api.learn_document(payload))
                elif path == "/agent_plan":
                    self._send_json(200, api.agent_plan(payload))
                elif path == "/selector_decide":
                    self._send_json(200, api.selector_decide(payload))
                elif path == "/selector_explain":
                    self._send_json(200, api.selector_explain(payload))
                elif path == "/authority":
                    self._send_json(200, api.authority(payload))
                elif path == "/ask":
                    self._send_json(200, api.ask(payload))
                elif path == "/sessions":
                    self._send_json(200, api.sessions(payload))
                elif path == "/session":
                    self._send_json(200, api.create_session(payload))
                elif path == "/session_history":
                    self._send_json(200, api.session_history(payload))
                elif path == "/session_memory":
                    self._send_json(200, api.session_memory(payload))
                elif path == "/feedback":
                    self._send_json(200, api.feedback(payload))
                elif path == "/consolidation_plan":
                    self._send_json(200, api.consolidation_plan(payload))
                elif path == "/consolidate":
                    self._send_json(200, api.consolidate(payload))
                elif path == "/consolidation_sources":
                    self._send_json(200, api.consolidation_sources(payload))
                elif path == "/memory_review":
                    self._send_json(200, api.memory_review(payload))
                elif path == "/memory_weak":
                    self._send_json(200, api.memory_weak(payload))
                elif path == "/memory_improve":
                    self._send_json(200, api.memory_improve(payload))
                elif path == "/memory_usage":
                    self._send_json(200, api.memory_usage(payload))
                elif path == "/migration_validate":
                    self._send_json(200, api.migration_validate(payload))
                elif path == "/shutdown":
                    self._send_json(200, {"ok": True, "shutdown": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._send_json(404, self._unknown_endpoint(path))
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            obj = json.loads(raw or "{}")
            if not isinstance(obj, dict):
                raise ValueError("request body must be a JSON object")
            return obj

        @staticmethod
        def _query_payload(query: str) -> dict[str, Any]:
            parsed = parse_qs(query, keep_blank_values=False)
            payload: dict[str, Any] = {}
            for key, values in parsed.items():
                if not values:
                    continue
                value = values[-1]
                if value.lower() in {"true", "false"}:
                    payload[key] = value.lower() == "true"
                else:
                    payload[key] = value
            return payload

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _unknown_endpoint(path: str) -> dict[str, Any]:
            suggestions = {
                "/query": "Use POST /retrieve or POST /query for semantic search.",
                "/learn_document": "Use POST /learn/document.",
                "/history": "Use POST /session_history.",
            }
            return {"error": "unknown endpoint", "path": path, "suggestion": suggestions.get(path)}

    return Handler


def build_server(root: Path, host: str, port: int, db_path: Path | None = None) -> tuple[HTTPServer, MemoryApi]:
    api = MemoryApi(root, db_path=db_path)
    server = HTTPServer((host, int(port)), make_handler(api))
    return server, api


def main() -> None:
    config = load_config(ROOT)
    server_cfg = config.get("server") if isinstance(config.get("server"), dict) else {}
    parser = argparse.ArgumentParser(description="Long-running CLC-CSD-GCL memory HTTP API")
    parser.add_argument("--host", default=str(server_cfg.get("host") or "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(server_cfg.get("port") or 8765))
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()

    db_path = resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else None
    server, api = build_server(ROOT, args.host, args.port, db_path=db_path)
    host, port = server.server_address
    print(
        json.dumps(
            {
                "ok": True,
                "url": f"http://{host}:{port}",
                "endpoints": [
                    "/health",
                    "/stats",
                    "/config",
                    "/ingest",
                    "/ingest_batch",
                    "/teach",
                    "/correct",
                    "/retrieve",
                    "/query",
                    "/learn",
                    "/learn/document",
                    "/agent_plan",
                    "/selector_decide",
                    "/selector_explain",
                    "/ask",
                    "/session",
                    "/sessions",
                    "/session_history",
                    "/session_memory",
                    "/feedback",
                    "GET /feedback",
                    "/consolidation_plan",
                    "/consolidate",
                    "/consolidation_sources",
                    "/memory_review",
                    "/memory_weak",
                    "/memory_improve",
                    "/memory_usage",
                    "/migration_validate",
                ],
            },
            indent=2,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        api.close()
        server.server_close()


if __name__ == "__main__":
    main()
