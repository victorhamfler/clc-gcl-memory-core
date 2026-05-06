from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.models import DomainState, MemoryNode
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB, utc_now


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def make_memory(memory_id: str, text: str, embedding: list[float], domain_id: str) -> MemoryNode:
    now = utc_now()
    return MemoryNode(
        id=memory_id,
        text=text,
        embedding=embedding,
        domain_id=domain_id,
        memory_type="design_rule",
        importance=0.5,
        stability=0.0,
        confidence=0.8,
        csd_score=0.0,
        surprise=0.0,
        recall_score=1.0,
        curiosity=0.0,
        focus=0.5,
        clc_state="RECALL",
        created_at=now,
        updated_at=now,
    )


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def compact(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "memory_id": item["memory_id"],
            "score": item["score"],
            "feedback_score": item["feedback_score"],
            "feedback_count": item["feedback_count"],
            "source": item.get("source"),
            "text_preview": item["text"][:180],
        }
        for item in results
    ]


def run(rounds: int = 5) -> dict[str, Any]:
    query = "What is the preferred planning cadence for the agent?"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "feedback_impact.db")
        try:
            embedding = pipeline.encoder.embed(query)
            domain = DomainState(id="dom_feedback_impact", name="agent_memory", anchor_vector=embedding, memory_count=2)
            pipeline.db.upsert_domain(domain)

            stale = make_memory(
                "mem_feedback_daily",
                "Planning cadence memory: the agent should create a daily automatic planning summary.",
                embedding,
                domain.id,
            )
            useful = make_memory(
                "mem_feedback_on_demand",
                "Planning cadence memory: the agent should create planning summaries only when the user asks.",
                embedding,
                domain.id,
            )
            pipeline.db.insert_memory(stale)
            pipeline.db.set_memory_source(stale.id, "feedback_impact/daily_policy.md", 0)
            pipeline.db.insert_memory(useful)
            pipeline.db.set_memory_source(useful.id, "feedback_impact/on_demand_policy.md", 0)

            timeline = [{"round": 0, "results": compact(pipeline.retrieve(query, top_k=2))}]
            for round_index in range(1, rounds + 1):
                current = pipeline.retrieve(query, top_k=2)
                stale_rank = next((idx + 1 for idx, item in enumerate(current) if item["memory_id"] == stale.id), None)
                useful_rank = next((idx + 1 for idx, item in enumerate(current) if item["memory_id"] == useful.id), None)
                stale_score = next((item["score"] for item in current if item["memory_id"] == stale.id), None)
                useful_score = next((item["score"] for item in current if item["memory_id"] == useful.id), None)
                pipeline.db.add_retrieval_feedback(
                    stale.id,
                    "wrong",
                    query=query,
                    rating=-1.0,
                    rank=stale_rank,
                    retrieval_score=stale_score,
                    metadata={"experiment": "feedback_impact", "round": round_index},
                )
                pipeline.db.add_retrieval_feedback(
                    useful.id,
                    "useful",
                    query=query,
                    rating=1.0,
                    rank=useful_rank,
                    retrieval_score=useful_score,
                    metadata={"experiment": "feedback_impact", "round": round_index},
                )
                timeline.append({"round": round_index, "results": compact(pipeline.retrieve(query, top_k=2))})

            ask = pipeline.ask(query, top_k=2, store_session=False)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    initial_top = timeline[0]["results"][0]["memory_id"]
    final_top = timeline[-1]["results"][0]["memory_id"]
    ok = (
        initial_top == "mem_feedback_daily"
        and final_top == "mem_feedback_on_demand"
        and "only when the user asks" in ask["answer"]
        and "daily automatic" not in ask["answer"].lower()
        and stats["retrieval_feedback"] == rounds * 2
    )
    return {
        "ok": ok,
        "query": query,
        "rounds": rounds,
        "initial_top": initial_top,
        "final_top": final_top,
        "answer": ask["answer"],
        "timeline": timeline,
        "stats": stats,
    }


def main() -> None:
    payload = run()
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
