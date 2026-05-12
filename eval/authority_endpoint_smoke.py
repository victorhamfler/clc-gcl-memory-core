import json
import sys
import threading
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve import build_server


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
    query = "What is the current release approval rule?"
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "authority_endpoint.db"
        server, api = build_server(ROOT, "127.0.0.1", 0, db_path=db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        try:
            old = post_json(
                f"{base}/teach",
                {
                    "text": "Old release rule: agents may approve releases automatically after tests pass.",
                    "source": "release_policy_v1.md",
                    "agent_id": "authority_endpoint_agent",
                },
            )
            first = post_json(
                f"{base}/correct",
                {
                    "correction": "Correction: agents must not approve releases automatically; Victor approval is required.",
                    "memory_id": old["memory"]["memory_id"],
                    "query": query,
                    "source": "release_policy_v2.md",
                    "agent_id": "authority_endpoint_agent",
                },
            )
            final = post_json(
                f"{base}/correct",
                {
                    "correction": "Correction: agents can prepare release notes, but only Victor can approve a release.",
                    "memory_id": first["correction_memory"]["memory_id"],
                    "query": query,
                    "source": "release_policy_v3.md",
                    "agent_id": "authority_endpoint_agent",
                },
            )
            by_id = post_json(f"{base}/authority", {"memory_id": old["memory"]["memory_id"]})
            by_query = post_json(f"{base}/authority", {"query": query, "top_k": 3})
            post_json(f"{base}/shutdown", {})
            thread.join(timeout=5)
        finally:
            api.close()
            server.server_close()

    old_id = old["memory"]["memory_id"]
    first_id = first["correction_memory"]["memory_id"]
    final_id = final["correction_memory"]["memory_id"]
    by_id_nodes = {item["memory_id"]: item for item in by_id["nodes"]}
    by_query_nodes = {item["memory_id"]: item for item in by_query["nodes"]}

    assert by_id["ok"] is True
    assert by_id["mode"] == "authority"
    assert by_id["authoritative_memory_ids"] == [final_id]
    assert by_id_nodes[old_id]["authority_state"] == "superseded"
    assert by_id_nodes[old_id]["authoritative_memory_ids"] == [final_id]
    assert by_id_nodes[old_id]["correction_chain_depth"] >= 2
    assert by_id_nodes[first_id]["authority_state"] == "superseded"
    assert by_id_nodes[final_id]["authority_state"] == "current"
    assert len(by_id["relations"]) == 2
    assert by_query["ok"] is True
    assert by_query["query"] == query
    assert by_query["query_results"][0]["memory_id"] == final_id
    assert by_query_nodes[final_id]["query_rank"] == 1
    assert "only Victor can approve" in by_query_nodes[final_id]["text"]

    print(
        json.dumps(
            {
                "ok": True,
                "old_id": old_id,
                "first_id": first_id,
                "final_id": final_id,
                "by_id_authoritative": by_id["authoritative_memory_ids"],
                "by_query_top": by_query["query_results"][0]["memory_id"],
                "relations": by_id["relations"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
