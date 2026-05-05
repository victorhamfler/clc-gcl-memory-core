from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.clc_controller import CLCController
from core.contradiction import store_contradiction_if_needed
from core.csd import CSDLayer
from core.encoder import build_encoder
from core.gcl_memory import GCLMemoryUpdater
from core.models import MemoryNode
from core.recall import RecallEngine
from core.resolver import resolve_answer
from core.symbolic import build_signal_packet
from storage.db import MemoryDB, new_id, utc_now


class MemoryPipeline:
    def __init__(
        self,
        root: Path,
        db_path: Path,
        embedding_dim: int = 128,
        top_k: int = 8,
        embedding_config: dict[str, Any] | None = None,
    ):
        self.root = root
        self.db = MemoryDB(db_path)
        self.encoder = build_encoder(embedding_config, default_dim=embedding_dim)
        self.recall_engine = RecallEngine(self.db, top_k=top_k)
        self.csd = CSDLayer(self.db)
        self.controller = CLCController()
        self.gcl = GCLMemoryUpdater(self.db)
        self.log_path = root / "logs" / "memory_events.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        close_encoder = getattr(self.encoder, "close", None)
        if callable(close_encoder):
            close_encoder()
        self.db.close()

    def ingest(self, text: str, source: str | None = None) -> dict[str, Any]:
        embedding = self.encoder.embed(text)
        embedding_signature = self._ensure_embedding_signature(embedding)
        signal = build_signal_packet(text, embedding)
        self._apply_source_domain_hint(signal, source)
        recall = self.recall_engine.recall(embedding)
        diagnostics = self.csd.diagnose(signal, recall)
        signals = self.controller.compute_signals(signal, diagnostics, recall)
        decision = self.controller.decide(diagnostics, signals)
        preferred_domain = self._preferred_domain(signal, recall.nearest_domain)
        update = self.gcl.apply(signal, decision, preferred_domain)
        assigned_domain = self.db.get_domain(update.domain_id)
        now = utc_now()
        memory = MemoryNode(
            id=new_id("mem"),
            text=text,
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
        )
        self.db.insert_memory(memory)
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
            },
        )
        result = {
            "memory_id": memory.id,
            "domain_id": update.domain_id,
            "domain_name": assigned_domain.name if assigned_domain else (signal.domains[0] if signal.domains else "general"),
            "memory_type": signal.memory_type,
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

    def _preferred_domain(self, signal, nearest_domain):
        symbolic = signal.domains[0] if signal.domains else "general"
        if symbolic and symbolic != "general":
            existing = self.db.get_domain_by_name(symbolic)
            if existing is not None:
                return existing
            if nearest_domain is None or nearest_domain.name != symbolic:
                return None
        return nearest_domain

    def ingest_batch(self, texts: list[str], source: str | None = None, limit: int | None = None) -> dict[str, Any]:
        cleaned = [str(text or "").strip() for text in texts if str(text or "").strip()]
        if limit is not None:
            cleaned = cleaned[: max(0, int(limit))]
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for idx, text in enumerate(cleaned):
            try:
                if self.db.memory_exists_text(text):
                    skipped.append({"batch_index": idx, "reason": "duplicate_exact_text", "text_preview": text[:160]})
                    continue
                item = self.ingest(text, source=source)
                item["batch_index"] = idx
                item["source"] = source
                self.db.set_memory_source(item["memory_id"], source, idx)
                results.append(item)
            except Exception as exc:
                errors.append({"batch_index": idx, "error": str(exc), "text_preview": text[:160]})
        summary = {
            "source": source,
            "requested": len(texts),
            "accepted": len(cleaned),
            "stored": len(results),
            "skipped": len(skipped),
            "errors": len(errors),
            "results": results,
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

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        embedding = self.encoder.embed(query)
        self._ensure_embedding_signature(embedding)
        candidate_k = max(int(top_k), 50)
        items = self.recall_engine.index.search(embedding, top_k=candidate_k)
        query_l = str(query or "").lower()
        candidate_ids = [item.memory_id for item in items]
        feedback_by_memory = self.db.feedback_summary_for_memories(candidate_ids)
        reliability = self.db.feedback_reliability_for_candidates(candidate_ids)
        supersession_relations = self.db.supersession_summary_for_candidates(candidate_ids)
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
            feedback = feedback_by_memory.get(item.memory_id, {})
            feedback_score = self._feedback_score(feedback)
            domain_reliability = self._feedback_score(reliability["domains"].get(item.domain_id, {}))
            source_reliability = self._feedback_score(reliability["sources"].get(source, {}))
            heuristic_supersession_score = self._supersession_score(query_l, item.text, source, latest_versions)
            relation_supersession_score = self._relation_supersession_score(
                query_l,
                supersession_relations.get(item.memory_id, {}),
            )
            supersession_score = max(-1.0, min(1.0, heuristic_supersession_score + relation_supersession_score))
            score = (
                0.45 * item.score
                + 0.08 * item.importance
                + 0.08 * item.stability
                + 0.08 * domain_match
                + 0.10 * text_match
                + 0.12 * source_match
                + 0.08 * feedback_score
                + 0.03 * domain_reliability
                + 0.03 * source_reliability
                + 0.10 * supersession_score
            )
            out.append(
                {
                    "memory_id": item.memory_id,
                    "domain_id": item.domain_id,
                    "domain_name": domain_name,
                    "source": source,
                    "chunk_index": source_info["chunk_index"] if source_info else None,
                    "memory_type": item.memory_type,
                    "score": round(score, 6),
                    "cosine": round(item.score, 6),
                    "importance": round(item.importance, 6),
                    "stability": round(item.stability, 6),
                    "feedback_score": round(feedback_score, 6),
                    "feedback_count": int(feedback.get("count", 0)),
                    "text_match_score": round(text_match, 6),
                    "domain_reliability": round(domain_reliability, 6),
                    "source_reliability": round(source_reliability, 6),
                    "supersession_score": round(supersession_score, 6),
                    "relation_supersession_score": round(relation_supersession_score, 6),
                    "text": item.text,
                }
            )
        out.sort(key=lambda row: row["score"], reverse=True)
        return out[:top_k]

    def ask(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        agent_id: str = "default",
        store_session: bool = False,
        remember: bool = False,
        memory_text: str | None = None,
    ) -> dict[str, Any]:
        session_context = self._session_context(session_id, query=query)
        retrieval_query = self._session_retrieval_query(query, session_context)
        retrieval_top_k = max(int(top_k), 20) if session_context else int(top_k)
        results = self.retrieve(retrieval_query, top_k=retrieval_top_k)
        if session_context:
            results = self._apply_session_evidence_boost(results, session_context)[: max(1, int(top_k))]
        resolved = resolve_answer(query, results)
        session = None
        user_turn = None
        assistant_turn = None
        durable_memory = None
        evidence_memory_ids = [
            str(item.get("memory_id"))
            for item in resolved["evidence"]
            if item.get("memory_id")
        ]
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
                    "stale_count": len(resolved["stale"]),
                    "disputed_count": len(resolved["disputed"]),
                },
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
            durable_memory = self.ingest(durable_text, source=f"session:{session['id']}" if session else "session")
            self.db.set_memory_source(
                durable_memory["memory_id"],
                f"session:{session['id']}" if session else "session",
                0,
                metadata={"remembered_from_ask": True, "query": query},
            )
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "session_context_used": bool(session_context),
            "session_context": session_context,
            "session_id": session["id"] if session else None,
            "agent_id": session["agent_id"] if session else agent_id,
            "user_turn_id": user_turn["id"] if user_turn else None,
            "assistant_turn_id": assistant_turn["id"] if assistant_turn else None,
            "answer": resolved["answer"],
            "confidence": resolved["confidence"],
            "conflict": resolved["conflict"],
            "durable_memory": durable_memory,
            "evidence": resolved["evidence"],
            "current": resolved["current"],
            "historical": resolved["historical"],
            "stale": resolved["stale"],
            "disputed": resolved["disputed"],
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
    ) -> dict[str, Any]:
        cleaned = str(text or "").strip()
        if not cleaned:
            raise ValueError("teach text is required")
        session = None
        user_turn = None
        memory_source = source or f"teach:{agent_id}"
        memory = self.ingest(cleaned, source=memory_source)
        self.db.set_memory_source(
            memory["memory_id"],
            memory_source,
            0,
            metadata={"agent_id": agent_id, "session_id": session_id, **(metadata or {})},
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
    ) -> dict[str, Any]:
        cleaned = str(correction or "").strip()
        if not cleaned:
            raise ValueError("correction text is required")
        target_ids = self._correction_targets(target_memory_ids or [], target_query, top_k, session_id=session_id)
        correction_text = cleaned if cleaned.lower().startswith("correction:") else f"Correction: {cleaned}"
        memory_source = source or f"correction:{agent_id}"
        session = None
        turn = None
        correction_memory = self.ingest(correction_text, source=memory_source)
        self.db.set_memory_source(
            correction_memory["memory_id"],
            memory_source,
            0,
            metadata={
                "agent_id": agent_id,
                "session_id": session_id,
                "target_memory_ids": target_ids,
                "target_query": target_query,
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
        self.db.add_event(
            correction_memory["memory_id"],
            "correct",
            metadata={
                "agent_id": agent_id,
                "session_id": session["id"] if session else session_id,
                "target_memory_ids": target_ids,
                "relation_type": relation_type,
            },
        )
        return {
            "ok": True,
            "mode": "correct",
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
        top_k: int,
        session_id: str | None = None,
    ) -> list[str]:
        out: list[str] = []
        for memory_id in target_memory_ids:
            mid = str(memory_id or "").strip()
            if mid and mid not in out:
                out.append(mid)
        query = str(target_query or "").strip()
        if not out and not query and session_id:
            for mid in self.db.latest_assistant_evidence(session_id):
                if mid and mid not in out:
                    out.append(mid)
        if query:
            context = self._session_context(session_id, query=query)
            retrieval_query = self._session_retrieval_query(query, context)
            for item in self.retrieve(retrieval_query, top_k=max(1, int(top_k))):
                mid = str(item.get("memory_id") or "").strip()
                if mid and mid not in out:
                    out.append(mid)
        return out

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
        query_tokens = self._topic_tokens(query or "")
        vague_followup = self._is_vague_followup(query or "", query_tokens)
        prepared_turns: list[dict[str, Any]] = []
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
            score = overlap + role_bonus + evidence_bonus
            if vague_followup and (overlap > 0.0 or not has_topic_match):
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
        context_lines = [
            f"{item['role']}: {item['content']}"
            for item in session_context[-6:]
            if item.get("content")
        ]
        if not context_lines:
            return query
        return "Session context:\n" + "\n".join(context_lines) + f"\nCurrent question: {query}"

    @staticmethod
    def _apply_session_evidence_boost(
        results: list[dict[str, Any]],
        session_context: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        context_scores: dict[str, float] = {}
        for item in session_context:
            score = float(item.get("context_score") or 0.0)
            for memory_id in item.get("evidence_memory_ids") or []:
                mid = str(memory_id or "").strip()
                if mid:
                    context_scores[mid] = max(context_scores.get(mid, 0.0), score)
        if not context_scores:
            return results
        boosted: list[dict[str, Any]] = []
        for item in results:
            row = dict(item)
            context_score = context_scores.get(str(row.get("memory_id") or ""), 0.0)
            if context_score > 0.0:
                boost = min(0.35, 0.18 + 0.18 * context_score)
                row["base_score"] = row["score"]
                row["session_evidence_score"] = round(context_score, 6)
                row["session_evidence_boost"] = round(boost, 6)
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
            "are",
            "as",
            "at",
            "be",
            "by",
            "can",
            "could",
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
            "is",
            "it",
            "its",
            "me",
            "must",
            "of",
            "on",
            "or",
            "our",
            "should",
            "so",
            "that",
            "the",
            "their",
            "there",
            "this",
            "to",
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
    def _is_vague_followup(query: str, query_tokens: set[str]) -> bool:
        compact = f" {str(query or '').lower()} "
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
        return len(query_tokens) <= 3 or any(marker in compact for marker in vague_markers)

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
        query_tokens = MemoryPipeline._tokens(query)
        text_tokens = MemoryPipeline._tokens(text)
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
        }
        query_terms = {token for token in query_tokens if len(token) > 2 and token not in stopwords}
        if not query_terms:
            return 0.0
        hits = len(query_terms & set(text_tokens))
        return min(1.0, hits / max(1, len(query_terms)))

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
                "supersedes",
                "current",
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
    def _source_version(source: str | None) -> tuple[str | None, int]:
        if not source:
            return None, 0
        path = Path(str(source))
        candidates = [part.lower() for part in path.parts]
        candidates.append(path.stem.lower())
        for candidate in candidates:
            parts = candidate.split("_")
            if parts and parts[-1].startswith("v") and parts[-1][1:].isdigit():
                group = "_".join(parts[:-1]).strip("_") or path.stem.lower()
                return group, int(parts[-1][1:])
        return None, 0

    @staticmethod
    def _tokens(text: str) -> set[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
        return {token for token in cleaned.split() if len(token) > 1}

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
        fields = ("backend", "model_name", "embedding_dim", "model_path")
        if any(existing_c.get(field) != descriptor.get(field) for field in fields):
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
