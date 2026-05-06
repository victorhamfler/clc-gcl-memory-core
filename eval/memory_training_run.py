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

from core.config import load_config
from core.pipeline import MemoryPipeline
from core.runtime import create_pipeline, init_db, pipeline_stats
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


def make_pipeline(db_path: Path, fast_hash: bool, embedding_dim: int) -> MemoryPipeline:
    if not fast_hash:
        return create_pipeline(ROOT, db_path=db_path)
    config = load_config(ROOT)
    init_db(ROOT, db_path)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": int(embedding_dim)},
        retrieval_weights=config.get("retrieval_weights"),
    )


def source_matches(source: str | None, expected_sources: list[str]) -> bool:
    normalized = normalize_source(source or "")
    return any(expected.lower() in normalized for expected in expected_sources)


def expected_terms_for(case: dict[str, Any], phase: str) -> list[str]:
    return case["v1_terms"] if phase == "after_v1" else case["v2_terms"]


def expected_sources_for(case: dict[str, Any], phase: str) -> list[str]:
    return case["expected_sources_v1"] if phase == "after_v1" else case["expected_sources_v2"]


def source_expectations_for(case: dict[str, Any], phase: str) -> dict[str, list[str]]:
    expected = expected_sources_for(case, phase)
    required = list(expected)
    acceptable = list(expected)
    if case["id"] == "user_preferences":
        if phase == "after_v1":
            required = ["user_profile"]
            acceptable = ["user_profile", "tool_rules"]
        else:
            required = ["user_preferences_v2"]
            acceptable = ["user_preferences_v2", "user_profile", "tool_rules"]
    return {"required": required, "acceptable": acceptable}


def evaluate_case(pipeline: MemoryPipeline, case: dict[str, Any], phase: str, top_k: int) -> dict[str, Any]:
    answer = pipeline.ask(case["query"], top_k=top_k, store_session=False)
    results = answer["raw_results"]
    source_results = results + list(answer.get("source_context", []))
    joined = "\n".join(str(item.get("text") or "") for item in results)
    expected_terms = expected_terms_for(case, phase)
    source_expectations = source_expectations_for(case, phase)
    required_sources = source_expectations["required"]
    acceptable_sources = source_expectations["acceptable"]
    top_source_is_expected = bool(results) and source_matches(results[0].get("source"), acceptable_sources)
    evidence_source_is_expected = bool(answer["evidence"]) and source_matches(answer["evidence"][0].get("source"), acceptable_sources)
    conflict_preferred = True
    if case["conflict"] and phase != "after_v1":
        conflict_preferred = score_terms(joined, case["v2_terms"]) >= score_terms(joined, case["v1_terms"])
    return {
        "id": case["id"],
        "query": case["query"],
        "phase": phase,
        "conflict_case": bool(case["conflict"]),
        "term_score": round(score_terms(joined, expected_terms), 4),
        "answer_term_score": round(score_terms(answer["answer"], expected_terms), 4),
        "source_score": round(score_sources(source_results, required_sources), 4),
        "required_sources": required_sources,
        "acceptable_sources": acceptable_sources,
        "v1_score": round(score_terms(joined, case["v1_terms"]), 4),
        "v2_score": round(score_terms(joined, case["v2_terms"]), 4),
        "stale_score": round(score_terms(joined, case["stale_terms"]), 4),
        "top_source_is_expected": top_source_is_expected,
        "evidence_source_is_expected": evidence_source_is_expected,
        "conflict_preferred": conflict_preferred,
        "answer_conflict": bool(answer["conflict"]),
        "answer_confidence": answer["confidence"],
        "answer": answer["answer"],
        "evidence": answer["evidence"],
        "stale": answer["stale"],
        "stale_context": answer.get("stale_context", []),
        "stale_context_count": len(answer.get("stale_context", [])),
        "source_context": answer.get("source_context", []),
        "source_context_count": len(answer.get("source_context", [])),
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
                "domain_name": item.get("domain_name"),
                "text_preview": str(item.get("text") or "")[:220],
            }
            for item in results
        ],
    }


def evaluate_phase(pipeline: MemoryPipeline, phase: str, top_k: int) -> list[dict[str, Any]]:
    return [evaluate_case(pipeline, case, phase, top_k) for case in QUERY_CASES]


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize_phase(rows: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [row for row in rows if row["conflict_case"]]
    return {
        "mean_term_score": mean([row["term_score"] for row in rows]),
        "mean_answer_term_score": mean([row["answer_term_score"] for row in rows]),
        "mean_source_score": mean([row["source_score"] for row in rows]),
        "top_source_accuracy": mean([1.0 if row["top_source_is_expected"] else 0.0 for row in rows]),
        "evidence_source_accuracy": mean([1.0 if row["evidence_source_is_expected"] else 0.0 for row in rows]),
        "conflict_preference": mean([1.0 if row["conflict_preferred"] else 0.0 for row in conflicts]),
        "answer_conflict_accuracy": mean(
            [1.0 if bool(row["answer_conflict"]) == bool(row["conflict_case"]) else 0.0 for row in rows]
        ),
        "mean_confidence": mean([float(row["answer_confidence"] or 0.0) for row in rows]),
        "mean_stale_score": mean([row["stale_score"] for row in rows]),
    }


def training_score(summary: dict[str, Any]) -> float:
    return round(
        0.22 * summary["mean_term_score"]
        + 0.22 * summary["mean_answer_term_score"]
        + 0.18 * summary["mean_source_score"]
        + 0.14 * summary["top_source_accuracy"]
        + 0.10 * summary["evidence_source_accuracy"]
        + 0.10 * summary["conflict_preference"]
        + 0.04 * summary["answer_conflict_accuracy"],
        4,
    )


def compact_top(row: dict[str, Any]) -> dict[str, Any]:
    top = row["top"][0] if row["top"] else {}
    return {
        "id": row["id"],
        "term_score": row["term_score"],
        "answer_term_score": row["answer_term_score"],
        "source_score": row["source_score"],
        "top_source_expected": row["top_source_is_expected"],
        "evidence_source_expected": row["evidence_source_is_expected"],
        "answer_conflict": row["answer_conflict"],
        "stale_context_count": row.get("stale_context_count", 0),
        "source_context_count": row.get("source_context_count", 0),
        "confidence": row["answer_confidence"],
        "top_source": top.get("source"),
        "top_preview": top.get("text_preview"),
        "answer": row["answer"],
    }


def regression_cases(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    before_by_id = {row["id"]: row for row in before}
    out = []
    for row in after:
        old = before_by_id.get(row["id"])
        if not old:
            continue
        if row["answer_term_score"] < old["answer_term_score"] or row["source_score"] < old["source_score"]:
            out.append(
                {
                    "id": row["id"],
                    "source_delta": round(row["source_score"] - old["source_score"], 4),
                    "answer_delta": round(row["answer_term_score"] - old["answer_term_score"], 4),
                    "before": compact_top(old),
                    "after": compact_top(row),
                }
            )
    return out


def weak_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weak = []
    for row in rows:
        if row["answer_term_score"] < 0.6 or row["source_score"] < 0.5 or not row["evidence_source_is_expected"]:
            weak.append(compact_top(row))
    return weak


def recommendations(summaries: dict[str, dict[str, Any]], final_rows: list[dict[str, Any]]) -> list[str]:
    final = summaries["after_feedback"]
    notes = []
    if final["mean_answer_term_score"] < 0.75:
        notes.append("Improve answer synthesis: retrieved evidence is usable, but extractive snippets miss expected answer terms.")
    if final["mean_source_score"] < 0.85:
        notes.append("Tune retrieval source weighting and relation weighting so v2/current sources dominate adaptation queries.")
    if final["answer_conflict_accuracy"] < 0.8:
        notes.append("Refine resolver conflict classification so stable preference queries do not look conflicted and corrected facts do.")
    conflict_rows = [row for row in final_rows if row["conflict_case"]]
    if any(row.get("stale_context_count", 0) == 0 for row in conflict_rows):
        notes.append("Improve stale companion lookup so every corrected conflict answer can expose its superseded context.")
    elif conflict_rows:
        notes.append("Corrected conflict answers expose superseded context; next useful work is feedback impact and consolidation safety testing.")
    if not notes:
        notes.append("Training run is healthy; next useful work is weight optimization and consolidation safety tests.")
    return notes


def build_report(
    summaries: dict[str, dict[str, Any]],
    cases: dict[str, list[dict[str, Any]]],
    manifest_relations: dict[str, Any],
    feedback_applied: list[dict[str, Any]],
) -> dict[str, Any]:
    scores = {phase: training_score(summary) for phase, summary in summaries.items()}
    return {
        "training_scores": scores,
        "deltas": {
            "v2_vs_v1": round(scores["after_v2"] - scores["after_v1"], 4),
            "relations_vs_v2": round(scores["after_relations"] - scores["after_v2"], 4),
            "feedback_vs_relations": round(scores["after_feedback"] - scores["after_relations"], 4),
            "feedback_vs_v1": round(scores["after_feedback"] - scores["after_v1"], 4),
        },
        "relation_count": manifest_relations["relations_added"],
        "feedback_count": len(feedback_applied),
        "weak_final_cases": weak_cases(cases["after_feedback"]),
        "regressions": regression_cases(cases["after_v2"], cases["after_feedback"]),
        "recommendations": recommendations(summaries, cases["after_feedback"]),
    }


def run(
    db_path: Path,
    max_words: int = 90,
    overlap_words: int = 12,
    top_k: int = 4,
    feedback_repeats: int = 3,
    fast_hash: bool = False,
    embedding_dim: int = 128,
) -> dict[str, Any]:
    start = time.perf_counter()
    pipeline = make_pipeline(db_path, fast_hash=fast_hash, embedding_dim=embedding_dim)
    try:
        v1_import = import_corpus(pipeline, corpus_files(V1_DIR), max_words, overlap_words)
        after_v1 = evaluate_phase(pipeline, "after_v1", top_k)

        v2_import = import_corpus(pipeline, corpus_files(V2_DIR), max_words, overlap_words)
        after_v2 = evaluate_phase(pipeline, "after_v2", top_k)

        manifest_relations = apply_manifest_relations(pipeline, load_manifest())
        after_relations = evaluate_phase(pipeline, "after_relations", top_k)

        feedback_applied = apply_adaptation_feedback(pipeline, after_relations, repeats=feedback_repeats)
        after_feedback = evaluate_phase(pipeline, "after_feedback", top_k)
        stats = pipeline_stats(pipeline)
    finally:
        pipeline.close()

    cases = {
        "after_v1": after_v1,
        "after_v2": after_v2,
        "after_relations": after_relations,
        "after_feedback": after_feedback,
    }
    summaries = {phase: summarize_phase(rows) for phase, rows in cases.items()}
    report = build_report(summaries, cases, manifest_relations, feedback_applied)
    return {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "database": str(db_path),
        "embedding_mode": "hash" if fast_hash else "configured",
        "imports": {"v1": v1_import, "v2": v2_import},
        "manifest_relations": manifest_relations,
        "feedback_applied_count": len(feedback_applied),
        "summaries": summaries,
        "report": report,
        "cases": cases,
        "stats": stats,
    }


def print_text_report(payload: dict[str, Any]) -> None:
    report = payload["report"]
    summaries = payload["summaries"]
    print("Memory Training Run")
    print(f"database: {payload['database']}")
    print(f"embedding: {payload['embedding_mode']}")
    print(f"elapsed_sec: {payload['elapsed_sec']}")
    print("")
    print("Scores")
    for phase, score in report["training_scores"].items():
        summary = summaries[phase]
        print(
            f"- {phase}: score={score:.4f}, terms={summary['mean_term_score']:.4f}, "
            f"answer={summary['mean_answer_term_score']:.4f}, source={summary['mean_source_score']:.4f}, "
            f"conflict={summary['answer_conflict_accuracy']:.4f}"
        )
    print("")
    print("Deltas")
    for name, value in report["deltas"].items():
        print(f"- {name}: {value:+.4f}")
    print("")
    print(f"relations_added: {report['relation_count']}")
    print(f"feedback_applied: {report['feedback_count']}")
    print("")
    print("Weak Final Cases")
    if not report["weak_final_cases"]:
        print("- none")
    for row in report["weak_final_cases"]:
        print(f"- {row['id']}: answer={row['answer_term_score']}, source={row['source_score']}, evidence_ok={row['evidence_source_expected']}")
    print("")
    print("Recommendations")
    for note in report["recommendations"]:
        print(f"- {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a teach/update/feedback training cycle for the agent memory corpus.")
    parser.add_argument("--db-path", default=None, help="Optional DB path. Defaults to a temporary DB.")
    parser.add_argument("--max-words", type=int, default=90)
    parser.add_argument("--overlap-words", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--feedback-repeats", type=int, default=3)
    parser.add_argument("--fast-hash", action="store_true", help="Use deterministic hash embeddings for quick tests.")
    parser.add_argument("--embedding-dim", type=int, default=128, help="Hash embedding dimension with --fast-hash.")
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
            max_words=args.max_words,
            overlap_words=args.overlap_words,
            top_k=args.top_k,
            feedback_repeats=args.feedback_repeats,
            fast_hash=args.fast_hash,
            embedding_dim=args.embedding_dim,
        )
    else:
        with TemporaryDirectory() as tmp:
            payload = run(
                Path(tmp) / "memory_training_run.db",
                max_words=args.max_words,
                overlap_words=args.overlap_words,
                top_k=args.top_k,
                feedback_repeats=args.feedback_repeats,
                fast_hash=args.fast_hash,
                embedding_dim=args.embedding_dim,
            )

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print_text_report(payload)


if __name__ == "__main__":
    main()
