from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from serve import MemoryApi
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def write_hash_config(root: Path, db_path: Path) -> None:
    storage_dir = root / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.joinpath("schema.sql").write_text(SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    root.joinpath("config.yaml").write_text(
        "\n".join(
            [
                f"database_path: {db_path.name}",
                "embedding_dim: 128",
                "top_k: 8",
                "embedding:",
                "  backend: hash",
                "  dim: 128",
            ]
        ),
        encoding="utf-8",
    )


def run() -> dict:
    query = "What is Victor's planning preference?"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "usage_confidence.db"
        pipeline = init_pipeline(root, db_path)
        try:
            memory = pipeline.teach(
                "Victor's planning preference: give concise structure, evidence, and next actions.",
                source="usage_confidence/profile.md",
                namespace="agent:hermes",
                store_session=False,
            )["memory"]
            first = pipeline.ask(query, namespace="agent:hermes", include_global=False, top_k=1, store_session=False)
            second = pipeline.ask(query, namespace="agent:hermes", include_global=False, top_k=1, store_session=False)
            usage = pipeline.db.memory_usage(namespace="agent:hermes", include_global=False, limit=5)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

        write_hash_config(root, db_path)
        api = MemoryApi(root, db_path=db_path)
        try:
            endpoint_usage = api.memory_usage({"namespace": "agent:hermes", "include_global": False, "limit": 5})
        finally:
            api.close()

    checks = {
        "first_answer_uses_memory": first["evidence"] and first["evidence"][0]["memory_id"] == memory["memory_id"],
        "first_logs_usage": len(first["usage_events"]) == 1,
        "second_sees_prior_usage": second["evidence"] and int(second["evidence"][0].get("usage_count") or 0) >= 1,
        "confidence_increases_with_usage": float(second["confidence"]) > float(first["confidence"]),
        "usage_stats_increment": int(stats.get("retrieval_uses") or 0) >= 2,
        "usage_endpoint_returns_memory": bool(endpoint_usage["memory_usage"])
        and endpoint_usage["memory_usage"][0]["memory_id"] == memory["memory_id"],
    }
    ok = all(checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "memory_id": memory["memory_id"],
        "first": {
            "confidence": first["confidence"],
            "usage_events": first["usage_events"],
            "evidence": first["evidence"],
        },
        "second": {
            "confidence": second["confidence"],
            "evidence": second["evidence"],
        },
        "usage": usage,
        "endpoint_usage": endpoint_usage["memory_usage"],
        "stats": stats,
    }


def main() -> None:
    payload = run()
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
