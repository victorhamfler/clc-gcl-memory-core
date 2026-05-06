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


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def evidence_text(answer: dict) -> str:
    chunks = [answer.get("answer") or ""]
    chunks.extend(item.get("text_preview") or "" for item in answer.get("evidence") or [])
    return "\n".join(chunks).lower()


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "namespace_isolation.db")
        try:
            global_memory = pipeline.teach(
                "Global agent rule: all agents should preserve source labels in evidence.",
                source="namespace/global.md",
                namespace="global",
                store_session=False,
            )
            alpha_memory = pipeline.teach(
                "Alpha private codename: Redwood Lantern is only for agent alpha.",
                source="namespace/alpha.md",
                agent_id="alpha",
                namespace="agent:alpha",
                store_session=False,
            )
            beta_memory = pipeline.teach(
                "Beta private codename: Blue Quartz is only for agent beta.",
                source="namespace/beta.md",
                agent_id="beta",
                namespace="agent:beta",
                store_session=False,
            )
            session = pipeline.db.create_session(agent_id="alpha", title="namespace eval")
            session_answer = pipeline.ask(
                "Remember the session-only label?",
                memory_text="Session private label: Silver Loom belongs only to this session.",
                remember=True,
                session_id=session["id"],
                agent_id="alpha",
                namespace="agent:alpha",
                store_session=True,
            )

            alpha_ask = pipeline.ask("What is alpha private codename?", namespace="agent:alpha", store_session=False)
            beta_ask_alpha = pipeline.ask("What is alpha private codename?", namespace="agent:beta", store_session=False)
            beta_ask_beta = pipeline.ask("What is beta private codename?", namespace="agent:beta", store_session=False)
            alpha_global = pipeline.ask("What should all agents preserve in evidence?", namespace="agent:alpha", store_session=False)
            beta_global = pipeline.ask("What should all agents preserve in evidence?", namespace="agent:beta", store_session=False)
            session_private = pipeline.ask(
                "What is the session private label?",
                namespace=f"session:{session['id']}",
                store_session=False,
            )
            alpha_no_session = pipeline.ask(
                "What is the session private label?",
                namespace="agent:alpha",
                include_global=False,
                store_session=False,
            )
            stats = pipeline.db.stats()
            namespace_counts = pipeline.db.namespace_counts()
        finally:
            pipeline.close()

    alpha_text = evidence_text(alpha_ask)
    beta_alpha_text = evidence_text(beta_ask_alpha)
    beta_text = evidence_text(beta_ask_beta)
    alpha_global_text = evidence_text(alpha_global)
    beta_global_text = evidence_text(beta_global)
    session_text = evidence_text(session_private)
    alpha_no_session_text = evidence_text(alpha_no_session)
    checks = {
        "global_memory_stored_global": global_memory["namespace"] == "global",
        "alpha_memory_stored_private": alpha_memory["namespace"] == "agent:alpha",
        "beta_memory_stored_private": beta_memory["namespace"] == "agent:beta",
        "session_memory_stored_session_namespace": session_answer["durable_memory"]["namespace"] == f"session:{session['id']}",
        "alpha_sees_alpha_private": "redwood lantern" in alpha_text,
        "beta_does_not_see_alpha_private": "redwood lantern" not in beta_alpha_text,
        "beta_does_not_substitute_beta_for_alpha": "blue quartz" not in beta_alpha_text,
        "beta_sees_beta_private": "blue quartz" in beta_text,
        "alpha_sees_global": "source labels" in alpha_global_text,
        "beta_sees_global": "source labels" in beta_global_text,
        "session_namespace_sees_session_memory": "silver loom" in session_text,
        "agent_namespace_does_not_see_session_memory": "silver loom" not in alpha_no_session_text,
        "namespace_counts_present": {"global", "agent:alpha", "agent:beta", f"session:{session['id']}"} <= {
            item["namespace"] for item in namespace_counts
        },
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "answers": {
            "alpha_private": alpha_ask["answer"],
            "beta_asks_alpha": beta_ask_alpha["answer"],
            "beta_private": beta_ask_beta["answer"],
            "session_private": session_private["answer"],
            "alpha_no_session": alpha_no_session["answer"],
        },
        "namespace_counts": namespace_counts,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
