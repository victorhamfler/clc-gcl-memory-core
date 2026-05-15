from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline


def main() -> None:
    with TemporaryDirectory() as tmp:
        pipeline = MemoryPipeline(
            ROOT,
            Path(tmp) / "session_cross_topic_leak_regression.db",
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
        )
        pipeline.db.init_schema(ROOT / "storage" / "schema.sql")
        try:
            namespace = "agent:session-leak"
            session = pipeline.db.ensure_session(agent_id="session_leak_agent", title="Cross topic leak")["id"]
            weather = pipeline.teach(
                "Victor checks the weather with the North Window weather dashboard.",
                namespace=namespace,
                session_id=session,
                agent_id="session_leak_agent",
            )["memory"]
            work = pipeline.teach(
                "Victor is building the CLC GCL agent memory brain project.",
                namespace=namespace,
                session_id=session,
                agent_id="session_leak_agent",
            )["memory"]

            weather_answer = pipeline.ask(
                "How does Victor check the weather?",
                namespace=namespace,
                include_global=False,
                session_id=session,
                agent_id="session_leak_agent",
                top_k=5,
            )
            weather_ids = [item.get("memory_id") for item in weather_answer["evidence"]]
            assert weather_answer["retrieval_query"] == "How does Victor check the weather?", weather_answer
            assert weather["memory_id"] == weather_ids[0], weather_answer
            assert work["memory_id"] not in weather_ids, weather_answer

            followup = pipeline.ask(
                "Tell me more about that project",
                namespace=namespace,
                include_global=False,
                session_id=session,
                agent_id="session_leak_agent",
                top_k=5,
            )
            followup_ids = [item.get("memory_id") for item in followup["evidence"]]
            assert work["memory_id"] in followup_ids, followup
            assert "Session context:" in followup["retrieval_query"], followup
        finally:
            pipeline.close()
    print("session_cross_topic_leak_regression: PASS")


if __name__ == "__main__":
    main()
