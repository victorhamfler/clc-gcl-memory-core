from __future__ import annotations

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
    label_memory = "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment."
    policy_memory = "GitHub policy memory: the assistant must not push to GitHub automatically unless Mira explicitly asks."
    label_query = "What is Cerulean Keystone?"
    policy_query = "Can the assistant push to GitHub automatically?"
    label_followup = "What should I remember about that label?"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_topic_filter_smoke.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            taught_label = pipeline.teach(
                label_memory,
                source="agent_training_v1/project_label.md",
                agent_id="agent_context",
                store_session=True,
            )
            session_id = taught_label["session_id"]
            taught_policy = pipeline.teach(
                policy_memory,
                source="agent_training_v1/github_policy.md",
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            pipeline.ask(label_query, top_k=2, session_id=session_id, agent_id="agent_context", store_session=True)
            policy = pipeline.ask(policy_query, top_k=2, session_id=session_id, agent_id="agent_context", store_session=True)
            followup = pipeline.ask(label_followup, top_k=2, session_id=session_id, agent_id="agent_context", store_session=True)
        finally:
            pipeline.close()

    retrieval_query = followup["retrieval_query"]
    context_blob = "\n".join(item["content"] for item in followup["session_context"])
    evidence_ids = [item["memory_id"] for item in followup["evidence"]]

    assert policy["evidence"][0]["memory_id"] == taught_policy["memory"]["memory_id"]
    assert taught_label["memory"]["memory_id"] in evidence_ids
    assert "Cerulean Keystone" in retrieval_query
    assert "GitHub policy memory" not in context_blob
    assert "push to GitHub automatically" not in context_blob

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": session_id,
                "followup_answer": followup["answer"],
                "followup_context": followup["session_context"],
                "followup_evidence": followup["evidence"],
                "retrieval_query": retrieval_query,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
