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
        db_path = Path(tmp) / "api_hardening_regression.db"
        server, api = build_server(ROOT, "127.0.0.1", 0, db_path=db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        start = time.perf_counter()
        try:
            health = get_json(f"{base}/health")
            session = post_json(
                f"{base}/session",
                {
                    "agent_id": "api_hardening_agent",
                    "title": "API hardening regression",
                },
            )
            session_id = session["session"]["id"]
            session_write = post_json(
                f"{base}/session_memory",
                {
                    "session_id": session_id,
                    "key": "working_goal",
                    "value": "Verify writable session memory and agent-friendly API aliases.",
                    "metadata": {"source": "api_hardening_regression"},
                },
            )
            session_read = post_json(f"{base}/session_memory", {"session_id": session_id})
            batch = post_json(
                f"{base}/ingest_batch",
                {
                    "source": "api_hardening_regression",
                    "texts": [
                        "API hardening fact: agents need full evidence text for reliable inspection.",
                        "API hardening fact: batch ingestion responses should include an ok flag.",
                    ],
                },
            )
            asked = post_json(
                f"{base}/ask",
                {
                    "query": "What do agents need for reliable API evidence inspection?",
                    "top_k": 2,
                    "agent_id": "api_hardening_agent",
                    "session_id": session_id,
                },
            )
            evidence_id = asked["evidence"][0]["memory_id"]
            feedback = post_json(
                f"{base}/feedback",
                {
                    "memory_id": evidence_id,
                    "query": "API evidence inspection",
                    "rating": 1.0,
                    "notes": "rating-only feedback should be accepted",
                },
            )
            taught = post_json(
                f"{base}/teach",
                {
                    "text": "Old hardening rule: agents can rely only on evidence previews.",
                    "agent_id": "api_hardening_agent",
                    "session_id": session_id,
                },
            )
            corrected = post_json(
                f"{base}/correct",
                {
                    "corrected_text": "Corrected hardening rule: agents should use full evidence text when verifying retrieved memories.",
                    "memory_id": taught["memory"]["memory_id"],
                    "query": "evidence previews full evidence text",
                    "agent_id": "api_hardening_agent",
                    "session_id": session_id,
                },
            )
            orphan = post_json(
                f"{base}/correct",
                {
                    "correction": "Orphan hardening correction with no target should be explicit.",
                    "agent_id": "api_hardening_agent",
                    "store_session": False,
                },
            )
            after = post_json(
                f"{base}/ask",
                {
                    "query": "Should agents rely only on evidence previews?",
                    "top_k": 3,
                    "agent_id": "api_hardening_agent",
                    "session_id": session_id,
                },
            )
            stats = get_json(f"{base}/stats")
            post_json(f"{base}/shutdown", {})
            thread.join(timeout=5)
        finally:
            api.close()
            server.server_close()

    assert health["ok"] is True
    assert session_write["ok"] is True
    assert session_write["mode"] == "session_memory_write"
    assert session_write["memory"]["key"] == "working_goal"
    assert session_read["mode"] == "session_memory_read"
    assert any(item["key"] == "working_goal" for item in session_read["session_memory"])
    assert batch["ok"] is True
    assert batch["mode"] == "ingest_batch"
    assert batch["stored"] == 2
    assert batch["partial_errors"] is False
    assert asked["evidence"]
    assert asked["evidence"][0]["text"]
    assert asked["evidence"][0]["text_preview"]
    assert "full evidence text" in asked["evidence"][0]["text"].lower()
    assert feedback["ok"] is True
    assert feedback["feedback"]["label"] == "useful"
    assert corrected["ok"] is True
    assert corrected["target_memory_ids"] == [taught["memory"]["memory_id"]]
    assert corrected["linked"] is True
    assert corrected["warning"] is None
    assert corrected["relations"]
    assert corrected["feedback"]
    assert orphan["ok"] is True
    assert orphan["linked"] is False
    assert orphan["target_memory_ids"] == []
    assert "not linked" in orphan["warning"]
    assert any(item.get("conflict") for item in after["evidence"]) or after["conflict"] is True
    assert stats["session_memory"] >= 1

    print(
        json.dumps(
            {
                "ok": True,
                "elapsed_sec": round(time.perf_counter() - start, 6),
                "session_memory": session_read["session_memory"],
                "batch": {
                    "ok": batch["ok"],
                    "mode": batch["mode"],
                    "stored": batch["stored"],
                    "partial_errors": batch["partial_errors"],
                },
                "feedback_label": feedback["feedback"]["label"],
                "correction_memory_id": corrected["correction_memory"]["memory_id"],
                "after_conflict": after["conflict"],
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
