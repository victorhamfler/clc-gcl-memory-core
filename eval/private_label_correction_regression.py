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
            Path(tmp) / "private_label_correction_regression.db",
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
        )
        pipeline.db.init_schema(ROOT / "storage" / "schema.sql")
        try:
            original = pipeline.teach(
                "Cerulean Keystone is the private label for Victor's deployment checklist.",
                source="private_label_v1.md",
                namespace="agent:private-label",
                agent_id="private_label_agent",
                store_session=False,
            )["memory"]
            correction = pipeline.correct(
                "Cerulean Keystone was renamed Amber Compass for Victor's deployment checklist.",
                target_memory_ids=[original["memory_id"]],
                source="private_label_v2.md",
                namespace="agent:private-label",
                agent_id="private_label_agent",
                store_session=False,
            )["correction_memory"]
            answer = pipeline.ask(
                "What is the private label?",
                namespace="agent:private-label",
                include_global=False,
                top_k=5,
            )
            assert answer["evidence"], answer
            assert correction["memory_id"] in [item.get("memory_id") for item in answer["evidence"]], answer
            assert "Amber Compass" in answer["answer"], answer
        finally:
            pipeline.close()
    print("private_label_correction_regression: PASS")


if __name__ == "__main__":
    main()
