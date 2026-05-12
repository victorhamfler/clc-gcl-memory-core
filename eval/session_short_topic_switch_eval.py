from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.pipeline import MemoryPipeline
from core.runtime import create_pipeline, init_db


def make_pipeline(root: Path, db_path: Path, use_config_embedding: bool) -> MemoryPipeline:
    if use_config_embedding:
        return create_pipeline(ROOT, db_path=db_path)
    init_db(ROOT, db_path)
    config = load_config(ROOT)
    return MemoryPipeline(
        root=root,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=config.get("retrieval_weights"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify short topic-switching questions do not inherit stale session context.")
    parser.add_argument("--use-config-embedding", action="store_true")
    args = parser.parse_args()

    namespace = "agent:short_topic_switch"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "session_short_topic_switch.db"
        pipeline = make_pipeline(root, db_path, args.use_config_embedding)
        try:
            pipeline.teach(
                "CLC kernel memory: CLC chooses learning states such as RECALL, FOCUS, PROTECT, and SPLIT_DOMAIN.",
                namespace=namespace,
                agent_id="topic_agent",
                source="short_topic_switch/clc.md",
                store_session=False,
            )
            pipeline.teach(
                "CSD memory: CSD detects contradiction pressure, novelty, density, and semantic surprise.",
                namespace=namespace,
                agent_id="topic_agent",
                source="short_topic_switch/csd.md",
                store_session=False,
            )
            pipeline.teach(
                "G-CL memory: G-CL maintains domain anchors, drift, curvature, and effective dimension.",
                namespace=namespace,
                agent_id="topic_agent",
                source="short_topic_switch/gcl.md",
                store_session=False,
            )
            first = pipeline.ask(
                "what is the CLC kernel",
                namespace=namespace,
                agent_id="topic_agent",
                store_session=True,
                top_k=3,
            )
            second = pipeline.ask(
                "what is CSD",
                namespace=namespace,
                agent_id="topic_agent",
                session_id=first["session_id"],
                store_session=True,
                top_k=3,
            )
            third = pipeline.ask(
                "how does G-CL work",
                namespace=namespace,
                agent_id="topic_agent",
                session_id=first["session_id"],
                store_session=True,
                top_k=3,
            )
        finally:
            pipeline.close()

    second_context = "\n".join(item.get("content") or "" for item in second.get("session_context") or [])
    third_context = "\n".join(item.get("content") or "" for item in third.get("session_context") or [])
    second_answer = second["answer"].lower()
    third_answer = third["answer"].lower()

    checks = {
        "second_does_not_prepend_clc_context": "clc kernel" not in second_context.lower(),
        "third_does_not_prepend_csd_context": "csd detects" not in third_context.lower(),
        "second_answers_csd": "csd" in second_answer and "contradiction" in second_answer,
        "third_answers_gcl": "g-cl" in third_answer and ("drift" in third_answer or "anchor" in third_answer),
    }
    assert all(checks.values()), checks
    print(
        json.dumps(
            {
                "ok": True,
                "embedding": "configured" if args.use_config_embedding else "hash",
                "checks": checks,
                "answers": {
                    "first": first["answer"],
                    "second": second["answer"],
                    "third": third["answer"],
                },
                "session_context_used": {
                    "first": first["session_context_used"],
                    "second": second["session_context_used"],
                    "third": third["session_context_used"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
