from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from core.runtime import init_db


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="correction_evidence_") as tmp:
        db_path = Path(tmp) / "memory.db"
        init_db(ROOT, db_path)
        pipeline = MemoryPipeline(ROOT, db_path, embedding_dim=128, embedding_config={"backend": "hash", "dim": 128})
        try:
            namespace = "agent:correction-regression"
            original = pipeline.teach(
                "Cerulean Keystone is the private label for Victor's deployment checklist.",
                namespace=namespace,
                agent_id="regression",
                store_session=False,
            )
            before = pipeline.ask("What should I remember about that label?", namespace=namespace, top_k=5)
            assert "Cerulean Keystone" in before["answer"], before["answer"]
            corrected = pipeline.correct(
                "Cerulean Keystone was renamed Amber Compass for Victor's deployment checklist.",
                target_memory_ids=[original["memory"]["memory_id"]],
                target_query="Cerulean Keystone label",
                namespace=namespace,
                agent_id="regression",
                store_session=False,
            )
            correction_id = corrected["correction_memory"]["memory_id"]
            after = pipeline.ask("What should I remember about that label?", namespace=namespace, top_k=5)
            assert "Amber Compass" in after["answer"], after
            assert after["evidence"][0]["memory_id"] == correction_id, after["evidence"]
            assert all(item["memory_id"] != original["memory"]["memory_id"] for item in after["evidence"][:1]), after["evidence"]
        finally:
            pipeline.close()
    print("correction_evidence_ranking_regression: PASS")


if __name__ == "__main__":
    main()
