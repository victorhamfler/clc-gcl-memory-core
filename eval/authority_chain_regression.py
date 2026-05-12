import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def main() -> None:
    query = "What is the current deployment rule for agents?"
    old_rule = "Old deployment rule: agents may deploy automatically after all smoke tests pass."
    first_correction = "Correction: agents must not deploy automatically; deployment requires explicit Victor approval."
    final_correction = "Correction: agents may prepare deployment notes, but only Victor can approve deployment."

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "authority_chain.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            taught = pipeline.teach(old_rule, source="deployment_policy_v1.md", agent_id="authority_agent")
            first = pipeline.correct(
                first_correction,
                target_memory_ids=[taught["memory"]["memory_id"]],
                target_query=query,
                source="deployment_policy_v2.md",
                agent_id="authority_agent",
            )
            final = pipeline.correct(
                final_correction,
                target_memory_ids=[first["correction_memory"]["memory_id"]],
                target_query=query,
                source="deployment_policy_v3.md",
                agent_id="authority_agent",
            )
            retrieved = pipeline.retrieve(query, top_k=5)
            asked = pipeline.ask(query, top_k=3)
        finally:
            pipeline.close()

    old_id = taught["memory"]["memory_id"]
    first_id = first["correction_memory"]["memory_id"]
    final_id = final["correction_memory"]["memory_id"]
    by_id = {item["memory_id"]: item for item in retrieved}
    asked_by_id = {item["memory_id"]: item for item in asked["evidence"]}

    assert retrieved[0]["memory_id"] == final_id
    assert by_id[final_id]["authority_state"] == "current"
    assert first_id in by_id[final_id]["supersedes_memory_ids"]
    assert by_id[first_id]["authority_state"] == "superseded"
    assert by_id[first_id]["authoritative_memory_ids"] == [final_id]
    assert by_id[old_id]["authority_state"] == "superseded"
    assert by_id[old_id]["authoritative_memory_ids"] == [final_id]
    assert by_id[old_id]["correction_chain_depth"] >= 2
    assert asked["evidence"][0]["memory_id"] == final_id
    assert asked_by_id[final_id]["authority_state"] == "current"
    assert "only victor can approve deployment" in asked["answer"].lower()

    print(
        json.dumps(
            {
                "ok": True,
                "ids": {
                    "old": old_id,
                    "first_correction": first_id,
                    "final_correction": final_id,
                },
                "retrieve": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "authority_state": item["authority_state"],
                        "authoritative_memory_ids": item["authoritative_memory_ids"],
                        "superseded_by_memory_ids": item["superseded_by_memory_ids"],
                        "supersedes_memory_ids": item["supersedes_memory_ids"],
                        "correction_chain_depth": item["correction_chain_depth"],
                    }
                    for item in retrieved
                ],
                "ask": {
                    "answer": asked["answer"],
                    "evidence": asked["evidence"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
