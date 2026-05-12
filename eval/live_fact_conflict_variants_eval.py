from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.pipeline import MemoryPipeline
from core.runtime import init_db


def make_pipeline(db_path: Path) -> MemoryPipeline:
    config = load_config(ROOT)
    init_db(ROOT, db_path)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=config.get("retrieval_weights"),
    )


def main() -> None:
    with TemporaryDirectory() as tmp:
        pipeline = make_pipeline(Path(tmp) / "live_fact_conflict_variants.db")
        namespace = "agent:fact_conflict"
        first = pipeline.teach(
            "Spain capital is Barcelona.",
            namespace=namespace,
            store_session=False,
            source="fact_variant_a",
        )["memory"]
        second = pipeline.teach(
            "Spain capital is Madrid.",
            namespace=namespace,
            store_session=False,
            source="fact_variant_b",
        )["memory"]
        answer = pipeline.ask(
            "What is the capital of Spain?",
            namespace=namespace,
            include_global=False,
            top_k=5,
            store_session=False,
        )
        pipeline.db.close()

    conflict_ids = {
        str(memory_id)
        for conflict in answer.get("live_conflicts") or []
        for memory_id in conflict.get("memory_ids") or []
    }
    evidence_conflict_ids = {
        str(item.get("memory_id"))
        for item in answer.get("evidence") or []
        if item.get("conflict")
    }
    checks = {
        "top_level_conflict": answer.get("conflict") is True,
        "live_conflict_details": bool(answer.get("live_conflicts")),
        "both_memories_in_conflict": {first["memory_id"], second["memory_id"]} <= conflict_ids,
        "evidence_annotated": bool(evidence_conflict_ids & {first["memory_id"], second["memory_id"]}),
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "answer": answer["answer"],
        "conflict": answer.get("conflict"),
        "live_conflicts": answer.get("live_conflicts"),
        "evidence": answer.get("evidence"),
    }
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
