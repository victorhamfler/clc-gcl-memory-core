from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.maintenance import memory_review, record_memory_improvement, weak_memories
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def contains_all(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return all(term.lower() in lower for term in terms)


def contains_any(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return any(term.lower() in lower for term in terms)


def rank_of(memory_id: str, rows: list[dict[str, Any]]) -> int | None:
    for idx, row in enumerate(rows, start=1):
        if row.get("memory_id") == memory_id:
            return idx
    return None


def score_answer(answer: dict[str, Any], expected_terms: list[str], forbidden_terms: list[str]) -> float:
    text = str(answer.get("answer") or "")
    evidence = answer.get("evidence") or []
    term_score = sum(1 for term in expected_terms if term.lower() in text.lower()) / max(1, len(expected_terms))
    forbidden_score = 0.0 if contains_any(text, forbidden_terms) else 1.0
    evidence_score = 1.0 if evidence else 0.0
    current_score = 1.0 if evidence and evidence[0].get("memory_state") in {"current", "historical"} else 0.5
    return round(0.50 * term_score + 0.25 * forbidden_score + 0.15 * evidence_score + 0.10 * current_score, 4)


def main() -> None:
    query = "How should maintenance facts store provenance?"
    expected_terms = ["must include", "source labels", "evidence ids"]
    forbidden_terms = [
        "without evidence ids",
        "without source labels",
        "can be stored without",
        "Memory improvement for",
        "Original memory preview",
    ]

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "maintenance_impact.db")
        try:
            weak_seed = pipeline.ingest(
                "Maintenance facts are temporary notes and can be stored without evidence ids or source labels."
            )
            pipeline.db.add_retrieval_feedback(
                weak_seed["memory_id"],
                "missing_source",
                query=query,
                rating=-0.75,
                notes="seed stale maintenance behavior before improvement",
            )

            before_retrieval = pipeline.retrieve(query, top_k=5)
            before_answer = pipeline.ask(query, top_k=4)
            before_score = score_answer(before_answer, expected_terms, forbidden_terms)
            weak_before = weak_memories(pipeline.db, limit=5)

            improved = record_memory_improvement(
                pipeline,
                weak_seed["memory_id"],
                "Current maintenance rule: maintenance facts must include source labels, evidence ids, and provenance notes.",
                agent_id="maintenance_impact_agent",
            )
            improvement_id = improved["improvement_memory"]["memory_id"]

            after_retrieval = pipeline.retrieve(query, top_k=5)
            after_answer = pipeline.ask(query, top_k=4)
            after_score = score_answer(after_answer, expected_terms, forbidden_terms)
            review_after = memory_review(pipeline.db, weak_limit=5)
            weak_after = weak_memories(pipeline.db, limit=5)
            resolved_after = weak_memories(pipeline.db, limit=5, include_resolved=True)
            relations = pipeline.db.relation_counts()
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    before_rank = rank_of(weak_seed["memory_id"], before_retrieval)
    after_original_rank = rank_of(weak_seed["memory_id"], after_retrieval)
    after_improvement_rank = rank_of(improvement_id, after_retrieval)
    after_evidence_ids = [item.get("memory_id") for item in after_answer.get("evidence") or []]
    stale_ids = [item.get("memory_id") for item in after_answer.get("stale") or []]

    checks = {
        "weak_memory_found_before": any(item["memory_id"] == weak_seed["memory_id"] for item in weak_before),
        "before_answer_exposes_bad_rule": contains_any(before_answer["answer"], forbidden_terms),
        "improvement_created": improvement_id != weak_seed["memory_id"],
        "improvement_retrieves_top": after_improvement_rank == 1,
        "original_no_longer_top": after_original_rank is None or after_original_rank > 1,
        "after_answer_uses_improvement": improvement_id in after_evidence_ids,
        "after_answer_has_expected_terms": contains_all(after_answer["answer"], expected_terms),
        "after_answer_avoids_forbidden_terms": not contains_any(after_answer["answer"], forbidden_terms),
        "after_answer_hides_internal_wrapper": "mem_" not in after_answer["answer"],
        "answer_score_improved": after_score > before_score,
        "updates_relation_recorded": any(row["relation_type"] == "updates" for row in relations),
        "resolved_target_removed_from_active_weak_list": not any(
            item["memory_id"] == weak_seed["memory_id"] for item in weak_after
        ),
        "improvement_not_active_weak": not any(item["memory_id"] == improvement_id for item in weak_after),
        "resolved_target_marked_when_included": any(
            item["memory_id"] == weak_seed["memory_id"] and item["resolved"] for item in resolved_after
        ),
        "original_preserved_as_context": weak_seed["memory_id"] in stale_ids
        or weak_seed["memory_id"] in [item.get("memory_id") for item in after_answer.get("stale_context") or []]
        or after_original_rank is not None,
        "review_still_ok": review_after["ok"] is True,
    }

    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "query": query,
        "weak_memory_id": weak_seed["memory_id"],
        "improvement_memory_id": improvement_id,
        "before": {
            "score": before_score,
            "weak_rank": before_rank,
            "answer": before_answer["answer"],
            "evidence_ids": [item.get("memory_id") for item in before_answer.get("evidence") or []],
        },
        "after": {
            "score": after_score,
            "improvement_rank": after_improvement_rank,
            "original_rank": after_original_rank,
            "answer": after_answer["answer"],
            "evidence_ids": after_evidence_ids,
            "stale_ids": stale_ids,
        },
        "review_recommendations": review_after["recommendations"],
        "weak_after": weak_after,
        "resolved_after": resolved_after,
        "relations": relations,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
