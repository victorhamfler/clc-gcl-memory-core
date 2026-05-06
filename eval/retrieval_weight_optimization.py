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

from core.pipeline import DEFAULT_RETRIEVAL_WEIGHTS
from eval.agent_corpus_experiment import (
    V1_DIR,
    V2_DIR,
    apply_adaptation_feedback,
    apply_manifest_relations,
    corpus_files,
    import_corpus,
    load_manifest,
)
from eval.memory_training_run import (
    evaluate_phase,
    make_pipeline,
    summarize_phase,
    training_score,
    weak_cases,
)


WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "baseline": {},
    "source_current": {
        "vector": 0.38,
        "text": 0.12,
        "source": 0.18,
        "feedback": 0.10,
        "supersession": 0.14,
        "relation_supersession": 0.16,
    },
    "source_heavy": {
        "vector": 0.34,
        "text": 0.12,
        "source": 0.24,
        "feedback": 0.08,
        "source_reliability": 0.06,
        "supersession": 0.12,
        "relation_supersession": 0.18,
    },
    "relation_heavy": {
        "vector": 0.38,
        "source": 0.14,
        "feedback": 0.10,
        "supersession": 0.16,
        "relation_supersession": 0.26,
    },
    "answer_text": {
        "vector": 0.36,
        "text": 0.20,
        "source": 0.16,
        "feedback": 0.08,
        "supersession": 0.12,
        "relation_supersession": 0.14,
    },
    "feedback_reliability": {
        "vector": 0.36,
        "source": 0.14,
        "feedback": 0.18,
        "domain_reliability": 0.07,
        "source_reliability": 0.07,
        "supersession": 0.12,
        "relation_supersession": 0.16,
    },
    "low_vector_current": {
        "vector": 0.30,
        "text": 0.16,
        "source": 0.22,
        "feedback": 0.12,
        "supersession": 0.16,
        "relation_supersession": 0.22,
    },
}


def merged_weights(profile: dict[str, float]) -> dict[str, float]:
    weights = dict(DEFAULT_RETRIEVAL_WEIGHTS)
    weights.update(profile)
    return weights


def evaluate_profile(pipeline, name: str, profile: dict[str, float], top_k: int) -> dict[str, Any]:
    pipeline.retrieval_weights = merged_weights(profile)
    rows = evaluate_phase(pipeline, "after_feedback", top_k=top_k)
    summary = summarize_phase(rows)
    score = training_score(summary)
    return {
        "profile": name,
        "score": score,
        "summary": summary,
        "weights": pipeline.retrieval_weights,
        "weak_cases": weak_cases(rows),
        "case_scores": [
            {
                "id": row["id"],
                "answer_term_score": row["answer_term_score"],
                "source_score": row["source_score"],
                "top_source_expected": row["top_source_is_expected"],
                "evidence_source_expected": row["evidence_source_is_expected"],
                "answer_conflict": row["answer_conflict"],
                "confidence": row["answer_confidence"],
            }
            for row in rows
        ],
    }


def config_block(weights: dict[str, float]) -> str:
    lines = ["retrieval_weights:"]
    for key in DEFAULT_RETRIEVAL_WEIGHTS:
        lines.append(f"  {key}: {weights[key]:.4f}")
    return "\n".join(lines)


def run(
    db_path: Path,
    fast_hash: bool = True,
    embedding_dim: int = 128,
    max_words: int = 90,
    overlap_words: int = 12,
    top_k: int = 4,
    feedback_repeats: int = 3,
) -> dict[str, Any]:
    start = time.perf_counter()
    pipeline = make_pipeline(db_path, fast_hash=fast_hash, embedding_dim=embedding_dim)
    try:
        v1_import = import_corpus(pipeline, corpus_files(V1_DIR), max_words, overlap_words)
        v2_import = import_corpus(pipeline, corpus_files(V2_DIR), max_words, overlap_words)
        manifest_relations = apply_manifest_relations(pipeline, load_manifest())
        baseline_rows = evaluate_phase(pipeline, "after_relations", top_k=top_k)
        feedback_applied = apply_adaptation_feedback(pipeline, baseline_rows, repeats=feedback_repeats)

        results = [
            evaluate_profile(pipeline, name, profile, top_k=top_k)
            for name, profile in WEIGHT_PROFILES.items()
        ]
    finally:
        pipeline.close()

    results.sort(
        key=lambda row: (
            row["score"],
            row["summary"]["mean_answer_term_score"],
            row["summary"]["mean_source_score"],
            row["summary"]["answer_conflict_accuracy"],
        ),
        reverse=True,
    )
    best = results[0]
    baseline = next(row for row in results if row["profile"] == "baseline")
    return {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "database": str(db_path),
        "embedding_mode": "hash" if fast_hash else "configured",
        "imports": {"v1": v1_import, "v2": v2_import},
        "manifest_relations": manifest_relations,
        "feedback_applied_count": len(feedback_applied),
        "best_profile": best["profile"],
        "best_score": best["score"],
        "baseline_score": baseline["score"],
        "score_delta": round(best["score"] - baseline["score"], 4),
        "best_config": config_block(best["weights"]),
        "results": results,
    }


def print_text_report(payload: dict[str, Any]) -> None:
    print("Retrieval Weight Optimization")
    print(f"database: {payload['database']}")
    print(f"embedding: {payload['embedding_mode']}")
    print(f"elapsed_sec: {payload['elapsed_sec']}")
    print("")
    print(f"best_profile: {payload['best_profile']}")
    print(f"best_score: {payload['best_score']:.4f}")
    print(f"baseline_score: {payload['baseline_score']:.4f}")
    print(f"score_delta: {payload['score_delta']:+.4f}")
    print("")
    print("Profiles")
    for row in payload["results"]:
        summary = row["summary"]
        print(
            f"- {row['profile']}: score={row['score']:.4f}, answer={summary['mean_answer_term_score']:.4f}, "
            f"source={summary['mean_source_score']:.4f}, top_source={summary['top_source_accuracy']:.4f}, "
            f"conflict={summary['answer_conflict_accuracy']:.4f}, weak={len(row['weak_cases'])}"
        )
    print("")
    print("Best Config")
    print(payload["best_config"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Search retrieval weight profiles against the agent-memory training corpus.")
    parser.add_argument("--db-path", default=None, help="Optional DB path. Defaults to a temporary DB.")
    parser.add_argument("--configured-embedding", action="store_true", help="Use config.yaml embedding instead of fast hash embeddings.")
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--max-words", type=int, default=90)
    parser.add_argument("--overlap-words", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--feedback-repeats", type=int, default=3)
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(
            db_path,
            fast_hash=not args.configured_embedding,
            embedding_dim=args.embedding_dim,
            max_words=args.max_words,
            overlap_words=args.overlap_words,
            top_k=args.top_k,
            feedback_repeats=args.feedback_repeats,
        )
    else:
        with TemporaryDirectory() as tmp:
            payload = run(
                Path(tmp) / "retrieval_weight_optimization.db",
                fast_hash=not args.configured_embedding,
                embedding_dim=args.embedding_dim,
                max_words=args.max_words,
                overlap_words=args.overlap_words,
                top_k=args.top_k,
                feedback_repeats=args.feedback_repeats,
            )

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print_text_report(payload)


if __name__ == "__main__":
    main()
