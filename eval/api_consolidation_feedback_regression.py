from __future__ import annotations

import json
import sys
import threading
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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    with TemporaryDirectory() as tmp:
        server, api = build_server(ROOT, "127.0.0.1", 0, db_path=Path(tmp) / "api.db")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        try:
            namespace = "agent:api-extra"
            ids = []
            for idx in range(5):
                taught = post_json(
                    f"{base}/teach",
                    {
                        "text": f"Consolidation dry run fact {idx}: agents should preview summaries before writing.",
                        "namespace": namespace,
                        "domain": "api_extra",
                        "memory_type": "design_rule",
                        "store_session": False,
                    },
                )
                ids.append(taught["memory"]["memory_id"])
            dry = post_json(f"{base}/consolidate", {"namespace": namespace, "min": 3, "dry_run": True})
            assert dry["mode"] == "dry_run", dry
            assert dry["created"] == 0, dry
            stats_after_dry = get_json(f"{base}/stats")
            assert stats_after_dry["memories"] == 5, stats_after_dry
            feedback = post_json(
                f"{base}/feedback",
                {"memory_id": ids[0], "label": "wrong", "rating": -1.0, "query": "preview summaries"},
            )
            assert feedback["ok"] is True
            listed = get_json(f"{base}/feedback?label=wrong&limit=5")
            assert listed["ok"] is True
            assert listed["feedback"][0]["memory_id"] == ids[0], listed
            post_json(f"{base}/shutdown", {})
            thread.join(timeout=5)
        finally:
            api.close()
            server.server_close()
    print("api_consolidation_feedback_regression: PASS")


if __name__ == "__main__":
    main()
