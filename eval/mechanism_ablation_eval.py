from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.resolver import resolve_answer
from core.runtime import create_pipeline, pipeline_stats
from eval.agent_corpus_experiment import (
    QUERY_CASES,
    V1_DIR,
    V2_DIR,
    apply_adaptation_feedback,
    apply_manifest_relations,
    corpus_files,
    import_corpus,
    load_manifest,
    normalize_source,
    score_sources,
    score_terms,
)


def vector_only_retrieve(pipeline, query: str, top_k: int) -> list[dict[str, Any]]:
    embedding = pipeline.encoder.embed(query)
    pipeline._ensure_embedding_signature(embedding)
    items = pipeline.recall_engine.index.search(embedding, top_k=top_k)
    rows: list[dict[str, Any]] = []
    for item in items:
        domain = pipeline.db.get_domain(item.domain_id) if item.domain_id else None
        source_info = pipeline.db.get_memory_source(item.memory_id)
        rows.append(
            {
                "memory_id": item.memory_id,
                "domain_id": item.domain_id,
                "domain_name": domain.name if domain else None,
                "source": source_info["source"] if source_info else None,
                "chunk_index": source_info["chunk_index"] if source_info else None,
                "memory_type": item.memory_type,
                "score": round(item.score, 6),
                "cosine": round(item.score, 6),
                "importance": round(item.importance, 6),
                "stability": round(item.stability, 6),
                "feedback_score": 0.0,
                "feedback_count": 0,
                "domain_reliability": 0.0,
                "source_reliability": 0.0,
                "supersession_score": 0.0,
                "relation_supersession_score": 0.0,
                "text": item.text,
            }
        )
    return rows


def source_matches(source: str | None, expected_sources: list[str]) -> bool:
    normalized = normalize_source(source or "")
    return any(expected.lower() in normalized for expected in expected_sources)


def evaluate_results(case: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    joined = "\n".join(item["text"] for item in results)
    answer = resolve_answer(case["query"], results)
    answer_text = answer["answer"]
    expected_sources = case["expected_sources_v2"]
    expected_terms = case["v2_terms"]
    top_source_is_expected = bool(results) and source_matches(results[0].get("source"), expected_sources)
    evidence_source_is_expected = bool(answer["evidence"]) and source_matches(answer["evidence"][0].get("source"), expected_sources)
    conflict_preferred = True
    if case["conflict"]:
        conflict_preferred = score_terms(joined, case["v2_terms"]) >= score_terms(joined, case["v1_terms"])
    return {
        "id": case["id"],
        "query": case["query"],
        "conflict": case["conflict"],
        "term_score": round(score_terms(joined, expected_terms), 4),
        "source_score": round(score_sources(results, expected_sources), 4),
        "v1_score": round(score_terms(joined, case["v1_terms"]), 4),
        "v2_score": round(score_terms(joined, case["v2_terms"]), 4),
        "stale_score": round(score_terms(joined, case["stale_terms"]), 4),
        "top_source_is_expected": top_source_is_expected,
        "evidence_source_is_expected": evidence_source_is_expected,
        "conflict_preferred": conflict_preferred,
        "answer_term_score": round(score_terms(answer_text, expected_terms), 4),
        "answer_conflict": answer["conflict"],
        "answer_confidence": answer["confidence"],
        "answer": answer_text,
        "top": [
            {
                "memory_id": item["memory_id"],
                "score": item["score"],
                "cosine": item.get("cosine"),
                "feedback_score": item.get("feedback_score"),
                "feedback_count": item.get("feedback_count"),
                "supersession_score": item.get("supersession_score"),
                "relation_supersession_score": item.get("relation_supersession_score"),
                "source": item.get("source"),
                "text_preview": item["text"][:220],
            }
            for item in results
        ],
        "evidence": answer["evidence"],
        "stale": answer["stale"],
    }


def evaluate_mode(pipeline, mode: str, top_k: int) -> list[dict[str, Any]]:
    rows = []
    for case in QUERY_CASES:
        if mode == "vector_only":
            results = vector_only_retrieve(pipeline, case["query"], top_k=top_k)
        else:
            results = pipeline.retrieve(case["query"], top_k=top_k)
        rows.append(evaluate_results(case, results))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [row for row in rows if row["conflict"]]
    return {
        "mean_term_score": round(sum(row["term_score"] for row in rows) / len(rows), 4),
        "mean_source_score": round(sum(row["source_score"] for row in rows) / len(rows), 4),
        "mean_answer_term_score": round(sum(row["answer_term_score"] for row in rows) / len(rows), 4),
        "top_source_accuracy": round(sum(1 for row in rows if row["top_source_is_expected"]) / len(rows), 4),
        "evidence_source_accuracy": round(sum(1 for row in rows if row["evidence_source_is_expected"]) / len(rows), 4),
        "conflict_preference": round(sum(1 for row in conflicts if row["conflict_preferred"]) / len(conflicts), 4),
        "answer_conflict_accuracy": round(sum(1 for row in rows if bool(row["answer_conflict"]) == bool(row["conflict"])) / len(rows), 4),
        "mean_confidence": round(sum(float(row["answer_confidence"] or 0.0) for row in rows) / len(rows), 4),
    }


def run(db_path: Path, max_words: int, overlap_words: int, top_k: int, feedback_repeats: int) -> dict[str, Any]:
    start = time.perf_counter()
    pipeline = create_pipeline(ROOT, db_path=db_path)
    try:
        v1_import = import_corpus(pipeline, corpus_files(V1_DIR), max_words, overlap_words)
        v2_import = import_corpus(pipeline, corpus_files(V2_DIR), max_words, overlap_words)

        vector_only = evaluate_mode(pipeline, "vector_only", top_k=top_k)
        enhanced_no_relations = evaluate_mode(pipeline, "enhanced_no_relations", top_k=top_k)

        manifest_relations = apply_manifest_relations(pipeline, load_manifest())
        enhanced_relations = evaluate_mode(pipeline, "enhanced_relations", top_k=top_k)

        feedback = apply_adaptation_feedback(pipeline, enhanced_relations, repeats=feedback_repeats)
        enhanced_feedback = evaluate_mode(pipeline, "enhanced_feedback", top_k=top_k)

        stats = pipeline_stats(pipeline)
    finally:
        pipeline.close()

    cases = {
        "vector_only": vector_only,
        "enhanced_no_relations": enhanced_no_relations,
        "enhanced_relations": enhanced_relations,
        "enhanced_feedback": enhanced_feedback,
    }
    summaries = {name: summarize(rows) for name, rows in cases.items()}
    return {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "database": str(db_path),
        "imports": {"v1": v1_import, "v2": v2_import},
        "manifest_relations": manifest_relations,
        "feedback_applied_count": len(feedback),
        "summaries": summaries,
        "deltas": {
            "enhanced_vs_vector_term": round(summaries["enhanced_no_relations"]["mean_term_score"] - summaries["vector_only"]["mean_term_score"], 4),
            "relations_vs_no_relations_conflict": round(summaries["enhanced_relations"]["conflict_preference"] - summaries["enhanced_no_relations"]["conflict_preference"], 4),
            "feedback_vs_relations_source": round(summaries["enhanced_feedback"]["mean_source_score"] - summaries["enhanced_relations"]["mean_source_score"], 4),
            "feedback_vs_vector_answer": round(summaries["enhanced_feedback"]["mean_answer_term_score"] - summaries["vector_only"]["mean_answer_term_score"], 4),
        },
        "cases": cases,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare raw vector retrieval against CSD/G-CL ranking, relations, and feedback")
    parser.add_argument("--db-path", default=None, help="Optional DB path. Defaults to a temporary DB.")
    parser.add_argument("--max-words", type=int, default=90)
    parser.add_argument("--overlap-words", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--feedback-repeats", type=int, default=3)
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(db_path, args.max_words, args.overlap_words, args.top_k, args.feedback_repeats)
    else:
        with TemporaryDirectory() as tmp:
            payload = run(Path(tmp) / "mechanism_ablation.db", args.max_words, args.overlap_words, args.top_k, args.feedback_repeats)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
