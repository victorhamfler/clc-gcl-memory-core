from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline  # noqa: E402
from core.runtime import init_db  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "correction_chain_retrieval_regression_results.json"


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": row.get("memory_id"),
        "authority_state": row.get("authority_state"),
        "correction_chain_depth": row.get("correction_chain_depth"),
        "score": row.get("score"),
        "correction_chain_score": row.get("correction_chain_score"),
        "intent_match_score": row.get("intent_match_score"),
        "supersession_score": row.get("supersession_score"),
        "relation_supersession_score": row.get("relation_supersession_score"),
        "source": row.get("source"),
        "text": row.get("text"),
    }


def run() -> dict[str, Any]:
    namespace = "agent:correction-chain-retrieval-regression"
    agent_id = "correction-chain-regression"
    query = "What is the current Hermes project codename?"

    with tempfile.TemporaryDirectory(prefix="correction_chain_retrieval_") as tmp:
        db_path = Path(tmp) / "memory.db"
        init_db(ROOT, db_path)
        pipeline = MemoryPipeline(
            ROOT,
            db_path,
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
        )
        try:
            v1 = pipeline.teach(
                "Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project.md",
                namespace=namespace,
                agent_id=agent_id,
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )
            v1_id = v1["memory"]["memory_id"]
            v2 = pipeline.correct(
                "Hermes project codename is Cedar Map, not Alpha Loom.",
                target_memory_ids=[v1_id],
                target_query=query,
                source="agent_memory_v2/project.md",
                namespace=namespace,
                agent_id=agent_id,
                store_session=False,
                relation_type="corrects",
                domain="agent_memory",
                memory_type="semantic_note",
            )
            v2_id = v2["correction_memory"]["memory_id"]
            v3 = pipeline.correct(
                "Hermes project codename is Cedar Map with CLC selector guardrails enabled.",
                target_memory_ids=[v2_id],
                target_query=query,
                source="agent_memory_v3/project.md",
                namespace=namespace,
                agent_id=agent_id,
                store_session=False,
                relation_type="corrects",
                domain="agent_memory",
                memory_type="semantic_note",
            )
            v3_id = v3["correction_memory"]["memory_id"]
            pipeline.teach(
                "Victor currently prefers dark mode in dashboards.",
                source="agent_memory_v1/preferences.md",
                namespace=namespace,
                agent_id=agent_id,
                store_session=False,
                domain="preference",
                memory_type="preference",
            )

            rows = pipeline.retrieve(query, top_k=8, namespace=namespace, include_global=False)
            answer = pipeline.ask(query, top_k=8, namespace=namespace, include_global=False)
        finally:
            pipeline.close()

    by_id = {row["memory_id"]: row for row in rows}
    ranks = {row["memory_id"]: idx + 1 for idx, row in enumerate(rows)}
    current_row = by_id[v3_id]
    superseded_rows = [by_id[mid] for mid in (v1_id, v2_id)]
    result = {
        "pass": True,
        "query": query,
        "answer": answer.get("answer"),
        "answer_mentions_cedar": "cedar map" in str(answer.get("answer", "")).lower(),
        "ids": {"v1": v1_id, "v2": v2_id, "v3": v3_id},
        "ranks": {"v1": ranks.get(v1_id), "v2": ranks.get(v2_id), "v3": ranks.get(v3_id)},
        "scores": {
            "v1": by_id[v1_id].get("score"),
            "v2": by_id[v2_id].get("score"),
            "v3": current_row.get("score"),
        },
        "correction_chain_scores": {
            "v1": by_id[v1_id].get("correction_chain_score"),
            "v2": by_id[v2_id].get("correction_chain_score"),
            "v3": current_row.get("correction_chain_score"),
        },
        "rows": [_brief(row) for row in rows],
    }
    checks = {
        "answer_mentions_cedar": result["answer_mentions_cedar"],
        "v3_retrieved": v3_id in by_id,
        "v1_retrieved": v1_id in by_id,
        "v2_retrieved": v2_id in by_id,
        "v3_ranks_before_v1": ranks[v3_id] < ranks[v1_id],
        "v3_ranks_before_v2": ranks[v3_id] < ranks[v2_id],
        "v3_score_exceeds_superseded": all(float(current_row["score"]) > float(row["score"]) for row in superseded_rows),
        "v3_chain_score_positive": float(current_row.get("correction_chain_score") or 0.0) > 0.0,
        "superseded_chain_scores_negative": all(
            float(row.get("correction_chain_score") or 0.0) < 0.0 for row in superseded_rows
        ),
    }
    result["checks"] = checks
    result["pass"] = all(checks.values())
    return result


def main() -> int:
    result = run()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result["pass"]:
        print(f"correction_chain_retrieval_regression: PASS ({OUT_JSON})")
        return 0
    print(json.dumps(result, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
