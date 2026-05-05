from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.runtime import configured_db_path, create_pipeline, pipeline_stats
from eval.query_eval import DEFAULT_CASES, concept_score, field_score, hit_score


def evaluate_cases(pipeline, top_k: int) -> dict[str, Any]:
    cases = []
    for case in DEFAULT_CASES:
        results = pipeline.retrieve(case["query"], top_k=top_k)
        top_text = "\n".join(item["text"] for item in results[:top_k])
        cases.append(
            {
                "query": case["query"],
                "expected": case["expected"],
                "expected_concepts": case.get("expected_concepts", []),
                "expected_domains": case.get("expected_domains", []),
                "expected_sources": case.get("expected_sources", []),
                "hit_score": round(hit_score(top_text, case["expected"]), 4),
                "concept_score": round(concept_score(top_text, case.get("expected_concepts")), 4),
                "domain_score": round(field_score([item.get("domain_name") for item in results], case.get("expected_domains")), 4),
                "source_score": round(field_score([item.get("source") for item in results], case.get("expected_sources")), 4),
                "top": results,
            }
        )
    return summarize_cases(cases)


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mean_hit_score": round(sum(c["hit_score"] for c in cases) / len(cases), 4),
        "mean_concept_score": round(sum(c["concept_score"] for c in cases) / len(cases), 4),
        "mean_domain_score": round(sum(c["domain_score"] for c in cases) / len(cases), 4),
        "mean_source_score": round(sum(c["source_score"] for c in cases) / len(cases), 4),
        "cases": cases,
    }


def result_matches(item: dict[str, Any], expected_domains: list[str], expected_sources: list[str]) -> bool:
    domain = str(item.get("domain_name") or "").lower()
    source = str(item.get("source") or "").lower()
    domain_ok = not expected_domains or any(expected.lower() in domain for expected in expected_domains)
    source_ok = not expected_sources or any(expected.lower() in source for expected in expected_sources)
    return domain_ok and source_ok


def choose_feedback_targets(case: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    expected_domains = case.get("expected_domains", [])
    expected_sources = case.get("expected_sources", [])
    top = list(case.get("top") or [])
    if not top:
        return None, None
    good = next((item for item in top if result_matches(item, expected_domains, expected_sources)), None)
    bad = next((item for item in reversed(top) if not result_matches(item, expected_domains, expected_sources)), None)
    if bad is None and len(top) > 1:
        bad = top[-1]
    if good and bad and good["memory_id"] == bad["memory_id"]:
        bad = None
    return good, bad


def rank_of(results: list[dict[str, Any]], memory_id: str | None) -> int | None:
    if not memory_id:
        return None
    for idx, item in enumerate(results, start=1):
        if item["memory_id"] == memory_id:
            return idx
    return None


def run_experiment(db_path: Path, top_k: int, positive_repeats: int, negative_repeats: int) -> dict[str, Any]:
    start = time.perf_counter()
    pipeline = create_pipeline(ROOT, db_path=db_path)
    try:
        before = evaluate_cases(pipeline, top_k=top_k)
        applied = []
        for case in before["cases"]:
            good, bad = choose_feedback_targets(case)
            if good:
                for _ in range(positive_repeats):
                    pipeline.db.add_retrieval_feedback(
                        memory_id=good["memory_id"],
                        label="useful",
                        query=case["query"],
                        rating=1.0,
                        rank=rank_of(case["top"], good["memory_id"]),
                        retrieval_score=good["score"],
                        metadata={"experiment": "feedback_experiment", "target": "good"},
                    )
            if bad:
                for _ in range(negative_repeats):
                    pipeline.db.add_retrieval_feedback(
                        memory_id=bad["memory_id"],
                        label="wrong",
                        query=case["query"],
                        rating=-1.0,
                        rank=rank_of(case["top"], bad["memory_id"]),
                        retrieval_score=bad["score"],
                        metadata={"experiment": "feedback_experiment", "target": "bad"},
                    )
            applied.append(
                {
                    "query": case["query"],
                    "good_memory_id": good["memory_id"] if good else None,
                    "bad_memory_id": bad["memory_id"] if bad else None,
                }
            )
        after = evaluate_cases(pipeline, top_k=top_k)
        movements = []
        for before_case, after_case, targets in zip(before["cases"], after["cases"], applied, strict=True):
            good_id = targets["good_memory_id"]
            bad_id = targets["bad_memory_id"]
            movements.append(
                {
                    "query": before_case["query"],
                    "good_memory_id": good_id,
                    "good_rank_before": rank_of(before_case["top"], good_id),
                    "good_rank_after": rank_of(after_case["top"], good_id),
                    "bad_memory_id": bad_id,
                    "bad_rank_before": rank_of(before_case["top"], bad_id),
                    "bad_rank_after": rank_of(after_case["top"], bad_id),
                    "scores_before": {
                        "hit": before_case["hit_score"],
                        "concept": before_case["concept_score"],
                        "domain": before_case["domain_score"],
                        "source": before_case["source_score"],
                    },
                    "scores_after": {
                        "hit": after_case["hit_score"],
                        "concept": after_case["concept_score"],
                        "domain": after_case["domain_score"],
                        "source": after_case["source_score"],
                    },
                    "top_after": [
                        {
                            "memory_id": item["memory_id"],
                            "score": item["score"],
                            "feedback_score": item.get("feedback_score"),
                            "feedback_count": item.get("feedback_count"),
                            "domain_reliability": item.get("domain_reliability"),
                            "source_reliability": item.get("source_reliability"),
                            "domain_name": item.get("domain_name"),
                            "source": item.get("source"),
                        }
                        for item in after_case["top"]
                    ],
                }
            )
        stats = pipeline_stats(pipeline)
    finally:
        pipeline.close()
    return {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "database": str(db_path),
        "positive_repeats": positive_repeats,
        "negative_repeats": negative_repeats,
        "before": {k: before[k] for k in ("mean_hit_score", "mean_concept_score", "mean_domain_score", "mean_source_score")},
        "after": {k: after[k] for k in ("mean_hit_score", "mean_concept_score", "mean_domain_score", "mean_source_score")},
        "movements": movements,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the active DB, apply scripted feedback, and measure ranking movement")
    parser.add_argument("--source-db", default=None, help="Database to copy; defaults to configured active DB")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--positive-repeats", type=int, default=3)
    parser.add_argument("--negative-repeats", type=int, default=3)
    parser.add_argument("--keep-db", default=None, help="Optional path to keep the experiment DB copy")
    args = parser.parse_args()

    source_db = Path(args.source_db) if args.source_db else configured_db_path(ROOT)
    if not source_db.is_absolute():
        source_db = ROOT / source_db
    if args.keep_db:
        experiment_db = Path(args.keep_db)
        if not experiment_db.is_absolute():
            experiment_db = ROOT / experiment_db
        experiment_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_db, experiment_db)
        payload = run_experiment(experiment_db, args.top_k, args.positive_repeats, args.negative_repeats)
    else:
        with TemporaryDirectory() as tmp:
            experiment_db = Path(tmp) / "feedback_experiment.db"
            shutil.copy2(source_db, experiment_db)
            payload = run_experiment(experiment_db, args.top_k, args.positive_repeats, args.negative_repeats)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
