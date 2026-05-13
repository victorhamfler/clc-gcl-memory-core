from __future__ import annotations

import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from core.runtime import init_db
from core.resolver import resolve_answer


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clc_gcl_agent_report_") as tmp:
        db_path = Path(tmp) / "memory.db"
        init_db(ROOT, db_path)
        pipeline = MemoryPipeline(
            ROOT,
            db_path,
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
            retrieval_weights={
                "vector": 0.38,
                "importance": 0.08,
                "stability": 0.08,
                "domain": 0.08,
                "text": 0.12,
                "intent": 0.14,
                "source": 0.18,
                "feedback": 0.10,
                "domain_reliability": 0.03,
                "source_reliability": 0.03,
                "supersession": 0.14,
                "relation_supersession": 0.16,
                "summary_relation": 0.08,
            },
        )
        try:
            ns = "agent:regression"
            pipeline.ingest(
                "The agent should save durable facts using the memory tool. User preferences and corrections are high priority memory.",
                namespace=ns,
                source="generic_agent_rule.md",
            )
            pipeline.ingest(
                "Victor is working on a new AI memory brain project for agents.",
                namespace=ns,
                source="victor_work.md",
            )
            pipeline.ingest(
                "Victor likes coffee in the morning and tea in the afternoon.",
                namespace=ns,
                source="victor_drink_v1.md",
            )
            pipeline.correct(
                "Victor likes espresso in the morning and green tea in the afternoon.",
                target_query="Victor likes coffee in the morning and tea in the afternoon.",
                namespace=ns,
                source="victor_drink_v2.md",
                agent_id="regression",
            )
            pipeline.ingest(
                "Victor prefers transparency over vague authority. He values source clarity and honest explanation of what was analyzed.",
                namespace=ns,
                source="victor_presentation.md",
            )

            work_answer = _answer_text(pipeline, "What is Victor working on?", ns)
            _assert_contains(work_answer, ("memory brain", "project"), "work answer should use Victor's project memory")
            _assert_not_contains(work_answer, ("espresso", "green tea", "coffee"), "work answer should not drift into drink preferences")

            presentation_answer = _answer_text(pipeline, "How does Victor like his information presented?", ns)
            _assert_contains(
                presentation_answer,
                ("transparency", "source clarity", "honest"),
                "presentation answer should use information-presentation preferences",
            )
            _assert_not_contains(
                presentation_answer,
                ("espresso", "green tea", "coffee"),
                "presentation answer should not be dominated by drink corrections",
            )

            broad_preferences = _answer_text(pipeline, "Tell me about Victor's preferences", ns)
            _assert_contains(broad_preferences, ("victor",), "broad preference answer should stay on Victor-specific memories")
            _assert_not_contains(
                broad_preferences,
                ("user preferences and corrections are high priority memory",),
                "broad preference answer should not return generic agent policy as the main answer",
            )

            pizza_old = pipeline.ingest("Victor likes pizza.", namespace=ns, source="pizza_v1.md")
            pizza_new = pipeline.ingest("Victor hates pizza and never eats it.", namespace=ns, source="pizza_v2.md")
            if float(pizza_new["contradiction"]) < 0.75:
                raise AssertionError(f"pizza preference conflict was not detected: {pizza_new}")
            if pizza_old["memory_id"] == pizza_new["memory_id"]:
                raise AssertionError("pizza conflict did not store a distinct correction candidate")
        finally:
            pipeline.close()


def _answer_text(pipeline: MemoryPipeline, query: str, namespace: str) -> str:
    results = pipeline.retrieve(query, top_k=5, namespace=namespace, include_global=False)
    return str(resolve_answer(query, results)["answer"]).lower()


def _assert_contains(text: str, needles: tuple[str, ...], message: str) -> None:
    if not any(needle in text for needle in needles):
        raise AssertionError(f"{message}. Answer: {text}")


def _assert_not_contains(text: str, needles: tuple[str, ...], message: str) -> None:
    if any(needle in text for needle in needles):
        raise AssertionError(f"{message}. Answer: {text}")


if __name__ == "__main__":
    main()
    print("agent_report_regression_20260513: PASS")
