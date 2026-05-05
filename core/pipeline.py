from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.clc_controller import CLCController
from core.contradiction import store_contradiction_if_needed
from core.csd import CSDLayer
from core.encoder import build_encoder
from core.gcl_memory import GCLMemoryUpdater
from core.models import MemoryNode
from core.recall import RecallEngine
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
        out: list[dict[str, Any]] = []
        for item in items:
            domain = self.db.get_domain(item.domain_id) if item.domain_id else None
            domain_name = domain.name if domain else None
            source_info = self.db.get_memory_source(item.memory_id)
            domain_match = 1.0 if domain_name and domain_name.lower() in query_l else 0.0
            source_match = self._source_affinity(query_l, source_info["source"] if source_info else None)
            score = (
                0.56 * item.score
                + 0.08 * item.importance
                + 0.08 * item.stability
                + 0.08 * domain_match
                + 0.12 * source_match
            )
            out.append(
                {
                    "memory_id": item.memory_id,
                    "domain_id": item.domain_id,
                    "domain_name": domain_name,
                    "source": source_info["source"] if source_info else None,
                    "chunk_index": source_info["chunk_index"] if source_info else None,
                    "memory_type": item.memory_type,
                    "score": round(score, 6),
                    "cosine": round(item.score, 6),
                    "importance": round(item.importance, 6),
                    "stability": round(item.stability, 6),
                    "text": item.text,
                }
            )
        out.sort(key=lambda row: row["score"], reverse=True)
        return out[:top_k]

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
