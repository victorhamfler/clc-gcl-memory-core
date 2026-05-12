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


def context_text(answer: dict) -> str:
    return "\n".join(str(item.get("content") or "") for item in answer.get("session_context") or [])


def evidence_ids(answer: dict) -> list[str]:
    return [str(item.get("memory_id") or "") for item in answer.get("evidence") or [] if item.get("memory_id")]


def main() -> None:
    label_memory = "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment."
    policy_memory = "GitHub policy memory: the assistant must not push to GitHub automatically unless Mira explicitly asks."
    label_followup = "What should I remember about that label?"
    rule_followup = "What should I remember about that rule?"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_topic_switch_regression.db"
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
            pipeline.ask(
                "What is Cerulean Keystone?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            policy_answer = pipeline.ask(
                "Can the assistant push to GitHub automatically?",
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            rule_answer = pipeline.ask(
                rule_followup,
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
            label_answer = pipeline.ask(
                label_followup,
                top_k=2,
                session_id=session_id,
                agent_id="agent_context",
                store_session=True,
            )
        finally:
            pipeline.close()

    label_id = taught_label["memory"]["memory_id"]
    policy_id = taught_policy["memory"]["memory_id"]
    rule_context = context_text(rule_answer)
    label_context = context_text(label_answer)

    assert policy_answer["evidence"][0]["memory_id"] == policy_id
    assert policy_id in evidence_ids(rule_answer)
    assert label_id not in evidence_ids(rule_answer)
    assert "push to GitHub automatically" in rule_answer["retrieval_query"]
    assert "Cerulean Keystone" not in rule_context
    assert label_id in evidence_ids(label_answer)
    assert policy_id not in evidence_ids(label_answer)
    assert "Cerulean Keystone" in label_answer["retrieval_query"]
    assert "push to GitHub automatically" not in label_context

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": session_id,
                "rule_answer": rule_answer["answer"],
                "rule_context": rule_answer["session_context"],
                "label_answer": label_answer["answer"],
                "label_context": label_answer["session_context"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
