from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve import build_server


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "server_smoke.db"
        server, api = build_server(ROOT, "127.0.0.1", 0, db_path=db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        start = time.perf_counter()
        try:
            health = get_json(f"{base}/health")
            first = post_json(
                f"{base}/ingest",
                {"text": "The long-running memory API keeps EmbeddingGemma loaded for repeated requests."},
            )
            batch = post_json(
                f"{base}/ingest_batch",
                {
                    "source": "server_smoke",
                    "texts": [
                        "Retrieval should reuse the persistent sidecar instead of reloading the model.",
                        "Batch ingestion should store several memory candidates in one server process.",
                    ],
                },
            )
            retrieved = post_json(f"{base}/retrieve", {"query": "persistent semantic memory retrieval", "top_k": 2})
            asked = post_json(
                f"{base}/ask",
                {
                    "query": "How should persistent memory retrieval work?",
                    "top_k": 2,
                    "agent_id": "server_smoke_agent",
                },
            )
            asked_again = post_json(
                f"{base}/ask",
                {
                    "query": "What should batch ingestion store?",
                    "top_k": 2,
                    "agent_id": "server_smoke_agent",
                    "session_id": asked["session_id"],
                },
            )
            history = post_json(f"{base}/session_history", {"session_id": asked["session_id"]})
            sessions = post_json(f"{base}/sessions", {"agent_id": "server_smoke_agent"})
            taught = post_json(
                f"{base}/teach",
                {
                    "text": "Server smoke teaching memory: the agent should preserve API evidence ids.",
                    "agent_id": "server_smoke_agent",
                    "session_id": asked["session_id"],
                },
            )
            corrected = post_json(
                f"{base}/correct",
                {
                    "correction": "server smoke correction: API evidence ids must remain visible in assistant turns.",
                    "target_memory_id": taught["memory"]["memory_id"],
                    "target_query": "API evidence ids",
                    "agent_id": "server_smoke_agent",
                    "session_id": asked["session_id"],
                    "top_k": 2,
                },
            )
            plan = post_json(f"{base}/consolidation_plan", {"min": 2, "max": 8})
            consolidated = post_json(f"{base}/consolidate", {"min": 2, "max": 8, "groups": 1})
            summary_sources = {"sources": []}
            if consolidated.get("created_summaries"):
                summary_sources = post_json(
                    f"{base}/consolidation_sources",
                    {"summary_memory_id": consolidated["created_summaries"][0]["summary_memory_id"]},
                )
            top = retrieved["results"][0]
            feedback = post_json(
                f"{base}/feedback",
                {
                    "query": "persistent semantic memory retrieval",
                    "memory_id": top["memory_id"],
                    "label": "useful",
                    "rank": 1,
                    "retrieval_score": top["score"],
                    "notes": "server smoke feedback check",
                },
            )
            maintenance_review = post_json(f"{base}/memory_review", {"limit": 3})
            maintenance_weak = post_json(f"{base}/memory_weak", {"limit": 3})
            maintenance_plan = post_json(f"{base}/memory_improve", {"limit": 2})
            weak_target = maintenance_weak["weak_memories"][0]["memory_id"] if maintenance_weak["weak_memories"] else top["memory_id"]
            maintenance_improve = post_json(
                f"{base}/memory_improve",
                {
                    "memory_id": weak_target,
                    "note": "Server smoke maintenance update: preserve source labels and evidence ids.",
                    "agent_id": "server_smoke_agent",
                },
            )
            maintenance_resolved = post_json(f"{base}/memory_weak", {"limit": 5, "resolved_only": True})
            stats = get_json(f"{base}/stats")
            post_json(f"{base}/shutdown", {})
            thread.join(timeout=5)
        finally:
            api.close()
            server.server_close()

        assert health["ok"] is True
        assert first["embedding_dim"] == 768
        assert batch["stored"] == 2
        assert batch["results"][0]["embedding_backend"] == "wsl_llama_cpp"
        assert retrieved["results"]
        assert asked["ok"] is True
        assert asked["evidence"]
        assert asked["answer"]
        assert asked_again["session_id"] == asked["session_id"]
        assert len(history["turns"]) == 4
        assert sessions["sessions"][0]["turn_count"] == 4
        assert taught["ok"] is True
        assert corrected["ok"] is True
        assert corrected["relations"]
        assert corrected["feedback"]
        assert plan["ok"] is True
        assert consolidated["ok"] is True
        assert summary_sources["sources"]
        assert feedback["ok"] is True
        assert feedback["feedback"]["label"] == "useful"
        assert maintenance_review["ok"] is True
        assert maintenance_weak["ok"] is True
        assert maintenance_plan["ok"] is True
        assert maintenance_improve["ok"] is True
        assert maintenance_improve["relation"]["relation_type"] == "updates"
        assert maintenance_resolved["ok"] is True
        assert maintenance_resolved["resolved_only"] is True
        assert any(item["memory_id"] == weak_target and item["resolved"] for item in maintenance_resolved["weak_memories"])
        assert stats["memories"] >= 6
        assert stats["retrieval_feedback"] >= 2
        assert stats["relations"] >= 1
        assert stats["sessions"] == 1
        assert stats["session_turns"] >= 6
        assert stats["vector_dimensions"] == [768]
        print(
            json.dumps(
                {
                    "ok": True,
                    "elapsed_sec": round(time.perf_counter() - start, 6),
                    "stats": stats,
                    "top_result": retrieved["results"][0]["memory_type"],
                    "ask": {
                        "answer": asked["answer"],
                        "confidence": asked["confidence"],
                        "session_id": asked["session_id"],
                        "evidence_count": len(asked["evidence"]),
                        "turn_count": len(history["turns"]),
                    },
                    "teach_memory_id": taught["memory"]["memory_id"],
                    "correct_memory_id": corrected["correction_memory"]["memory_id"],
                    "consolidated": consolidated,
                    "summary_sources": summary_sources["sources"][:2],
                    "maintenance": {
                        "review_recommendations": maintenance_review["recommendations"],
                        "weak_count": len(maintenance_weak["weak_memories"]),
                        "resolved_count": len(maintenance_resolved["weak_memories"]),
                        "improvement_memory_id": maintenance_improve["improvement_memory"]["memory_id"],
                    },
                    "feedback": feedback["feedback"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
