from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from core.runtime import init_db


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="session_context_boundary_") as tmp:
        db_path = Path(tmp) / "memory.db"
        init_db(ROOT, db_path)
        pipeline = MemoryPipeline(ROOT, db_path, embedding_dim=128, embedding_config={"backend": "hash", "dim": 128})
        try:
            namespace = "agent:session-boundary"
            session_id = "sess_boundary"
            weather = pipeline.teach(
                "Victor checks local weather with Meteoblue radar before planning a walk.",
                namespace=namespace,
                session_id=session_id,
                agent_id="regression",
            )
            work = pipeline.teach(
                "Victor is building an AI memory brain assistant with CLC, CSD, and G-CL mechanisms.",
                namespace=namespace,
                session_id=session_id,
                agent_id="regression",
            )
            weather_answer = pipeline.ask(
                "How does Victor check the weather?",
                namespace=namespace,
                session_id=session_id,
                agent_id="regression",
                top_k=5,
            )
            assert weather_answer["evidence"][0]["memory_id"] == weather["memory"]["memory_id"], weather_answer["evidence"]
            assert weather_answer["retrieval_query"] == "How does Victor check the weather?", weather_answer["retrieval_query"]
            work_answer = pipeline.ask(
                "What AI project is Victor building?",
                namespace=namespace,
                session_id=session_id,
                agent_id="regression",
                top_k=5,
            )
            assert work_answer["evidence"][0]["memory_id"] == work["memory"]["memory_id"], work_answer["evidence"]
            assert work_answer["retrieval_query"] == "What AI project is Victor building?", work_answer["retrieval_query"]
        finally:
            pipeline.close()
    print("session_context_boundary_regression: PASS")


if __name__ == "__main__":
    main()
