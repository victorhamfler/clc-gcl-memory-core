from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.chunking import chunk_text
from core.config import load_config, resolve_project_path
from core.consolidation import consolidation_plan, create_consolidation_summaries
from core.maintenance import improvement_plan, memory_review, record_memory_improvement, weak_memories
from core.runtime import create_pipeline, pipeline_stats


ROOT = Path(__file__).resolve().parent
FEEDBACK_RATINGS = {
    "excellent": 2.0,
    "useful": 1.0,
    "good": 1.0,
    "ok": 0.25,
    "neutral": 0.0,
    "missing_source": -0.5,
    "wrong_domain": -0.75,
    "stale": -0.75,
    "wrong": -1.0,
    "bad": -1.0,
}


class MemoryApi:
    def __init__(self, root: Path, db_path: Path | None = None):
        self.pipeline = create_pipeline(root, db_path=db_path)

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
        return {
            "ok": True,
            "session": session,
            "session_memory": self.pipeline.db.list_session_memory(session_id, limit=max(1, int(payload.get("limit") or 20))),
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("POST /ingest requires JSON field 'text'")
        memory = self.pipeline.ingest(
            text,
            source=str(payload.get("source") or "").strip() or None,
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "").strip() or None,
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
        )
        return {"ok": True, "mode": "ingest", "memory": memory, **memory}

    def teach(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("POST /teach requires JSON field 'text'")
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
        )

    def correct(self, payload: dict[str, Any]) -> dict[str, Any]:
        correction = str(payload.get("correction") or payload.get("text") or "").strip()
        if not correction:
            raise ValueError("POST /correct requires JSON field 'correction' or 'text'")
        target_memory_ids = payload.get("target_memory_ids")
        if target_memory_ids is None and payload.get("target_memory_id") is not None:
            target_memory_ids = [payload.get("target_memory_id")]
        if target_memory_ids is None:
            target_memory_ids = []
        if not isinstance(target_memory_ids, list):
            raise ValueError("'target_memory_ids' must be a JSON list when provided")
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        return self.pipeline.correct(
            correction,
            target_memory_ids=[str(item) for item in target_memory_ids],
            target_query=str(payload.get("target_query") or "").strip() or None,
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
        )

    def ingest_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_texts = payload.get("texts")
        source = str(payload.get("source") or "").strip() or None
        if raw_texts is None and payload.get("text") is not None:
            raw_texts = chunk_text(
                str(payload.get("text") or ""),
                max_words=int(payload.get("max_words") or 120),
                overlap_words=int(payload.get("overlap_words") or 20),
            )
        if not isinstance(raw_texts, list):
            raise ValueError("POST /ingest_batch requires JSON field 'texts' or chunkable 'text'")
        texts = [str(item or "") for item in raw_texts]
        return self.pipeline.ingest_batch(
            texts,
            source=source,
            limit=payload.get("limit"),
            namespace=str(payload.get("namespace") or "global").strip() or "global",
            priority=str(payload.get("priority") or "").strip() or None,
            force_clc_state=str(payload.get("force_clc_state") or payload.get("clc_state") or "").strip() or None,
        )

    def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("POST /retrieve requires JSON field 'query'")
        top_k = max(1, int(payload.get("top_k") or 5))
        return {
            "results": self.pipeline.retrieve(
                query,
                top_k=top_k,
                namespace=str(payload.get("namespace") or "global").strip() or "global",
                include_global=bool(payload.get("include_global", True)),
            )
        }

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("POST /ask requires JSON field 'query'")
        top_k = max(1, int(payload.get("top_k") or 5))
        return {
            "ok": True,
            **self.pipeline.ask(
                query,
                top_k=top_k,
                session_id=str(payload.get("session_id") or "").strip() or None,
                agent_id=str(payload.get("agent_id") or "default").strip() or "default",
                store_session=bool(payload.get("store_session", True)),
                remember=bool(payload.get("remember", False)),
                memory_text=str(payload.get("memory_text") or "").strip() or None,
                namespace=str(payload.get("namespace") or "global").strip() or "global",
                include_global=bool(payload.get("include_global", True)),
            ),
        }

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(payload.get("memory_id") or "").strip()
        label = str(payload.get("label") or "").strip().lower()
        if not memory_id:
            raise ValueError("POST /feedback requires JSON field 'memory_id'")
        if not label:
            raise ValueError("POST /feedback requires JSON field 'label'")
        rating = payload.get("rating")
        if rating is None:
            rating = FEEDBACK_RATINGS.get(label, 0.0)
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("'metadata' must be a JSON object when provided")
        return {
            "ok": True,
            "feedback": self.pipeline.db.add_retrieval_feedback(
                memory_id=memory_id,
                label=label,
                query=str(payload.get("query") or "").strip() or None,
                rating=float(rating),
                rank=payload.get("rank"),
                retrieval_score=payload.get("retrieval_score"),
                notes=str(payload.get("notes") or "").strip() or None,
                metadata=metadata,
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


def make_handler(api: MemoryApi):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CLCGCLMemory/0.1"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/health":
                    self._send_json(200, api.health())
                elif path == "/stats":
                    self._send_json(200, api.stats())
                else:
                    self._send_json(404, {"error": "unknown endpoint"})
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
                elif path == "/retrieve":
                    self._send_json(200, api.retrieve(payload))
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
                elif path == "/shutdown":
                    self._send_json(200, {"ok": True, "shutdown": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._send_json(404, {"error": "unknown endpoint"})
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

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
                    "/ingest",
                    "/ingest_batch",
                    "/teach",
                    "/correct",
                    "/retrieve",
                    "/ask",
                    "/session",
                    "/sessions",
                    "/session_history",
                    "/session_memory",
                    "/feedback",
                    "/consolidation_plan",
                    "/consolidate",
                    "/consolidation_sources",
                    "/memory_review",
                    "/memory_weak",
                    "/memory_improve",
                    "/memory_usage",
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
