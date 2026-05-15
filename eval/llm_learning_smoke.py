from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.learning import learn_from_document, learn_from_text
from core.pipeline import MemoryPipeline
from core.runtime import init_db


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clc_gcl_llm_learning_") as tmp:
        db_path = Path(tmp) / "memory.db"
        init_db(ROOT, db_path)
        pipeline = MemoryPipeline(
            ROOT,
            db_path,
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
            llm_config={"enabled": False},
        )
        try:
            disabled = learn_from_text(
                pipeline,
                "Victor prefers concise status updates.",
                {"enabled": False},
                namespace="agent:learn",
                mode="dry_run",
            )
            assert disabled["ok"] is False
            assert disabled["error"] == "LLM backend disabled"

            cfg = {
                "enabled": True,
                "provider": "mock",
                "max_facts_per_call": 5,
                "min_fact_length": 10,
                "min_confidence": 0.70,
                "duplicate_threshold": 0.98,
                "correction_threshold": 0.0,
                "max_retries": 0,
                "chunk_delay": 0.0,
            }
            facts = [
                {
                    "fact": "Victor prefers concise status updates with clear test results.",
                    "type": "preference",
                    "confidence": 0.94,
                    "correction": False,
                    "entities": ["Victor"],
                }
            ]
            extract_only = learn_from_text(
                pipeline,
                "Victor prefers concise status updates with clear test results.",
                cfg,
                namespace="agent:learn",
                agent_id="learner",
                mode="extract_only",
                mock_facts=facts,
            )
            assert extract_only["facts_extracted"] == 1
            assert extract_only["facts_stored"] == 0
            assert extract_only["results"][0]["action"] == "teach"
            assert extract_only["warning"]

            stored = learn_from_text(
                pipeline,
                "Victor prefers concise status updates with clear test results.",
                cfg,
                namespace="agent:learn",
                agent_id="learner",
                mode="extract_and_store",
                mock_facts=facts,
            )
            assert stored["facts_stored"] == 1
            assert stored["results"][0]["action"] == "teach"
            assert stored["results"][0]["memory_id"]

            teach_alias = learn_from_text(
                pipeline,
                "The planner should tag API facts as design rules in the api_usability domain.",
                cfg,
                namespace="agent:learn",
                agent_id="learner",
                mode="teach",
                filters={"memory_type": "design_rule", "domain": "api_usability"},
                mock_facts=[
                    {
                        "fact": "The planner should tag API facts as design rules in the api_usability domain.",
                        "type": "semantic_note",
                        "confidence": 0.95,
                        "correction": False,
                    }
                ],
            )
            assert teach_alias["mode"] == "extract_and_store"
            assert teach_alias["facts_stored"] == 1
            assert teach_alias["results"][0]["memory_type"] == "design_rule"
            assert teach_alias["results"][0]["domain"] == "api_usability"

            duplicate = learn_from_text(
                pipeline,
                "Victor prefers concise status updates with clear test results.",
                cfg,
                namespace="agent:learn",
                agent_id="learner",
                mode="extract_and_store",
                mock_facts=facts,
            )
            assert duplicate["facts_stored"] == 0
            assert duplicate["facts_skipped"] == 1
            assert duplicate["results"][0]["action"] == "skip"

            pipeline.teach(
                "Victor likes espresso in the morning.",
                namespace="agent:learn",
                agent_id="learner",
                source="seed",
            )
            correction = learn_from_text(
                pipeline,
                "Actually, Victor now prefers matcha instead of espresso.",
                cfg,
                namespace="agent:learn",
                agent_id="learner",
                mode="extract_and_store",
                mock_facts=[
                    {
                        "fact": "Victor now prefers matcha instead of espresso.",
                        "type": "preference",
                        "confidence": 0.95,
                        "correction": True,
                        "entities": ["Victor"],
                    }
                ],
            )
            assert correction["facts_stored"] == 1
            assert correction["results"][0]["action"] == "correct"
            assert correction["results"][0]["linked_to"]

            document = learn_from_document(
                pipeline,
                title="Learning smoke document",
                content=(
                    "Victor prefers compact progress reports with exact command results. "
                    "The memory agent should dry-run LLM extraction before storing new facts.\n\n"
                    "The agent should use extract-only mode when it wants to inspect routing decisions. "
                    "The agent should use extract-and-store only after the dry run looks correct."
                ),
                llm_config={
                    **cfg,
                    "mock_facts": [
                        {
                            "fact": "The memory agent should dry-run LLM extraction before storing new facts.",
                            "type": "procedure",
                            "confidence": 0.96,
                            "correction": False,
                            "entities": ["memory agent"],
                        }
                    ],
                },
                namespace="agent:learn",
                agent_id="learner",
                mode="extract_only",
                max_words=12,
                overlap_words=0,
            )
            assert document["ok"] is True
            assert document["chunks_processed"] >= 2
            assert document["chunk_delay_sec"] == 0.0
            assert document["facts_extracted"] >= 1
        finally:
            pipeline.close()
    print("llm_learning_smoke: PASS")


if __name__ == "__main__":
    main()
