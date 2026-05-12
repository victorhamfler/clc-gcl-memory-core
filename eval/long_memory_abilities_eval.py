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


def has_terms(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return all(term.lower() in lower for term in terms)


def main() -> None:
    namespace = "agent:long_memory_probe"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "long_memory_abilities.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            for idx in range(30):
                pipeline.teach(
                    f"Background turn {idx}: routine planning detail number {idx} has no private code or deployment policy.",
                    namespace=namespace,
                    agent_id="long_memory_agent",
                    source=f"long_memory/noise_{idx:02d}.md",
                    store_session=False,
                )

            pipeline.teach(
                "Information extraction fact: Mira's recovery code is Violet-73.",
                namespace=namespace,
                agent_id="long_memory_agent",
                source="long_memory/info.md",
                store_session=False,
            )
            first_session = pipeline.teach(
                "Multi-session fact: the launch codename is Blue Harbor.",
                namespace=namespace,
                agent_id="long_memory_agent",
                source="long_memory/session_a.md",
                store_session=True,
            )
            pipeline.ask(
                "What is the launch codename?",
                namespace=namespace,
                agent_id="long_memory_agent",
                session_id=first_session["session_id"],
                store_session=True,
            )
            pipeline.teach(
                "Session decomposition fact: the preferred editor is Helix. The meeting snacks are apples. The weather note is rainy.",
                namespace=namespace,
                agent_id="long_memory_agent",
                source="long_memory/mixed_turn.md",
                store_session=False,
            )
            old_policy = pipeline.teach(
                "Temporal policy v1: the deployment window is Tuesday.",
                namespace=namespace,
                agent_id="long_memory_agent",
                source="long_memory/deploy_v1.md",
                store_session=False,
            )
            correction = pipeline.correct(
                "Temporal policy v2: the current deployment window is Friday, not Tuesday.",
                target_memory_ids=[old_policy["memory"]["memory_id"]],
                namespace=namespace,
                agent_id="long_memory_agent",
                source="long_memory/deploy_v2.md",
                store_session=False,
            )

            extraction = pipeline.ask("What is Mira's recovery code?", namespace=namespace, store_session=False, top_k=4)
            multi_session = pipeline.ask("What is the launch codename?", namespace=namespace, store_session=False, top_k=4)
            temporal_current = pipeline.ask(
                "What is the current deployment window?",
                namespace=namespace,
                store_session=False,
                top_k=4,
            )
            decomposition = pipeline.ask("What is the preferred editor?", namespace=namespace, store_session=False, top_k=4)
            abstention = pipeline.ask("What is Mira's passport number?", namespace=namespace, store_session=False, top_k=4)
            authority = pipeline.authority(memory_ids=[old_policy["memory"]["memory_id"]], namespace=namespace)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    stale_blob = "\n".join(item.get("text") or "" for item in temporal_current.get("stale_context") or temporal_current.get("stale") or [])
    authority_blob = json.dumps(authority, sort_keys=True)
    checks = {
        "information_extraction": has_terms(extraction["answer"], ["Violet-73"]),
        "multi_session_recall": has_terms(multi_session["answer"], ["Blue Harbor"]),
        "temporal_current_prefers_latest": has_terms(temporal_current["answer"], ["Friday"]) and "Tuesday" in stale_blob,
        "authority_tracks_previous": old_policy["memory"]["memory_id"] in authority_blob
        and correction["correction_memory"]["memory_id"] in authority_blob,
        "session_decomposition": has_terms(decomposition["answer"], ["Helix"]),
        "abstention_when_unknown": "not have enough memory evidence" in abstention["answer"].lower(),
        "noise_scale_present": stats["memories"] >= 35,
    }
    assert all(checks.values()), checks
    print(
        json.dumps(
            {
                "ok": True,
                "checks": checks,
                "answers": {
                    "extraction": extraction["answer"],
                    "multi_session": multi_session["answer"],
                    "temporal_current": temporal_current["answer"],
                    "decomposition": decomposition["answer"],
                    "abstention": abstention["answer"],
                },
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
