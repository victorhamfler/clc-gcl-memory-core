from __future__ import annotations

import json
import sys
import threading
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from serve import build_server
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def make_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def pipeline_regression() -> dict:
    namespace = "agent:hermes"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = make_pipeline(root, root / "agent_bug_report_regression.db")
        try:
            pipeline.teach(
                "Victor is working on a new AI memory project.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
            pipeline.teach(
                "Victor prefers transparency over vague authority when discussing system behavior.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
            pipeline.teach(
                "Weather radar method for Victor: use AccuWeather URL. This works better than trying to visually analyze radar canvas images from meteoblue.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
            work_answer = pipeline.ask(
                "What is he working on?",
                namespace=namespace,
                include_global=False,
                top_k=5,
                store_session=False,
            )
            old = pipeline.teach(
                "Victor likes coffee in the morning and tea in the afternoon.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
            opposite = pipeline.teach(
                "Victor hates all forms of tea and never drinks it.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
            correction = pipeline.correct(
                "Victor likes espresso in the morning and green tea in the afternoon.",
                namespace=namespace,
                agent_id="hermes",
                store_session=False,
            )
        finally:
            pipeline.close()

    answer = work_answer["answer"]
    checks = {
        "answer_uses_project_fact": "new AI memory project" in answer,
        "answer_omits_weather_fragment": "meteoblue" not in answer and "Weather radar" not in answer,
        "preference_contradiction_detected": float(opposite["memory"]["contradiction"]) >= 0.75,
        "correction_auto_links": correction["linked"] is True and old["memory"]["memory_id"] in correction["target_memory_ids"],
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "answer": answer,
        "opposite": opposite["memory"],
        "correction": {
            "linked": correction["linked"],
            "target_memory_ids": correction["target_memory_ids"],
            "relations": correction["relations"],
        },
    }


def server_get_regression() -> dict:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "server_get_regression.db"
        server, api = build_server(ROOT, "127.0.0.1", 0, db_path=db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        try:
            taught = post_json(
                f"{base}/teach",
                {
                    "text": "GET endpoint regression memory: session and usage endpoints should be readable.",
                    "agent_id": "hermes",
                    "namespace": "agent:hermes",
                    "store_session": True,
                },
            )
            sessions = get_json(f"{base}/sessions?agent_id=hermes&namespace=agent:hermes")
            usage = get_json(f"{base}/memory_usage?namespace=agent:hermes&limit=5")
            post_json(f"{base}/shutdown", {})
            thread.join(timeout=5)
        finally:
            api.close()
            server.server_close()
    checks = {
        "teach_ok": taught["ok"] is True,
        "get_sessions_ok": sessions["ok"] is True and bool(sessions["sessions"]),
        "get_memory_usage_ok": usage["ok"] is True and "memory_usage" in usage,
    }
    return {"ok": all(checks.values()), "checks": checks, "sessions": sessions, "usage": usage}


def main() -> None:
    pipeline = pipeline_regression()
    server = server_get_regression()
    payload = {"ok": pipeline["ok"] and server["ok"], "pipeline": pipeline, "server": server}
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
