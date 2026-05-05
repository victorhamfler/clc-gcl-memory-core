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

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("POST /ingest requires JSON field 'text'")
        return self.pipeline.ingest(text)

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
        return self.pipeline.ingest_batch(texts, source=source, limit=payload.get("limit"))

    def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("POST /retrieve requires JSON field 'query'")
        top_k = max(1, int(payload.get("top_k") or 5))
        return {"results": self.pipeline.retrieve(query, top_k=top_k)}

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
                elif path == "/retrieve":
                    self._send_json(200, api.retrieve(payload))
                elif path == "/feedback":
                    self._send_json(200, api.feedback(payload))
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
                "endpoints": ["/health", "/stats", "/ingest", "/ingest_batch", "/retrieve", "/feedback"],
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
