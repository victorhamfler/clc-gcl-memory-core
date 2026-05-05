from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chunking import load_texts_from_file
from core.runtime import create_pipeline, pipeline_stats
from eval.query_eval import DEFAULT_CASES, concept_score, field_score, hit_score


SEED_FILES = [
    (Path(r"C:\Users\victo\Downloads\2026-05-03_15-50-47_ChatGPT_1._The_combined_mechanism_in_one_sentence.md"), 20),
    (Path(r"C:\Users\victo\Downloads\G-CL_SKILL.md"), 16),
    (Path(r"C:\Users\victo\Downloads\CSD_SKILL.md"), 16),
    (Path(r"C:\Users\victo\Desktop\projcod2\.tmp\geometry_controller_repo\CSD_GCL_Next_Implementation_Spec_2026-04-08.md"), 5),
    (Path(r"C:\Users\victo\Desktop\projcod2\.tmp\geometry_controller_repo\GEOMETRY_GGUF_MIGRATION_RUNBOOK.md"), 3),
    (Path(r"C:\Users\victo\Desktop\projcod2\.tmp\geometry_controller_repo\GEOMETRY_CONTROLLER_MANUAL.md"), 5),
]


def run_eval(pipeline, top_k: int) -> dict:
    cases = []
    for case in DEFAULT_CASES:
        results = pipeline.retrieve(case["query"], top_k=top_k)
        top_text = "\n".join(item["text"] for item in results)
        cases.append(
            {
                "query": case["query"],
                "hit_score": round(hit_score(top_text, case["expected"]), 4),
                "concept_score": round(concept_score(top_text, case.get("expected_concepts")), 4),
                "domain_score": round(field_score([item.get("domain_name") for item in results], case.get("expected_domains")), 4),
                "source_score": round(field_score([item.get("source") for item in results], case.get("expected_sources")), 4),
                "top": [
                    {
                        "score": item["score"],
                        "cosine": item["cosine"],
                        "domain_name": item.get("domain_name"),
                        "source": item.get("source"),
                        "chunk_index": item.get("chunk_index"),
                        "text_preview": item["text"][:180],
                    }
                    for item in results
                ],
            }
        )
    return {
        "mean_hit_score": round(sum(c["hit_score"] for c in cases) / len(cases), 4),
        "mean_concept_score": round(sum(c["concept_score"] for c in cases) / len(cases), 4),
        "mean_domain_score": round(sum(c["domain_score"] for c in cases) / len(cases), 4),
        "mean_source_score": round(sum(c["source_score"] for c in cases) / len(cases), 4),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a temporary corpus DB and evaluate retrieval quality")
    parser.add_argument("--max-words", type=int, default=120)
    parser.add_argument("--overlap-words", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    start = time.perf_counter()
    temp_dir = TemporaryDirectory() if not args.db_path else None
    try:
        db_path = Path(args.db_path) if args.db_path else Path(temp_dir.name) / f"corpus_{args.max_words}.db"
        if args.reset and db_path.exists():
            db_path.unlink()
        pipeline = create_pipeline(ROOT, db_path=db_path)
        imports = []
        try:
            for source_path, limit in SEED_FILES:
                texts = load_texts_from_file(source_path, max_words=args.max_words, overlap_words=args.overlap_words)
                texts = texts[:limit]
                result = pipeline.ingest_batch(texts, source=str(source_path))
                imports.append(
                    {
                        "source": str(source_path),
                        "requested": result["requested"],
                        "stored": result["stored"],
                        "skipped": result["skipped"],
                        "errors": result["errors"],
                    }
                )
            eval_payload = run_eval(pipeline, args.top_k)
            stats = pipeline_stats(pipeline)
        finally:
            pipeline.close()
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    payload = {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "max_words": args.max_words,
        "overlap_words": args.overlap_words,
        "imports": imports,
        "stats": stats,
        **eval_payload,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print(
        f"max_words={args.max_words} hit={payload['mean_hit_score']} "
        f"concept={payload['mean_concept_score']} "
        f"domain={payload['mean_domain_score']} source={payload['mean_source_score']} "
        f"memories={payload['stats']['memories']} elapsed={payload['elapsed_sec']}"
    )


if __name__ == "__main__":
    main()
