from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.runtime import create_pipeline, pipeline_stats


DEFAULT_CASES = [
    {
        "query": "CLC controller novelty surprise recall focus",
        "expected": ["CLC", "surprise", "recall", "focus", "controller"],
        "expected_concepts": [["CLC"], ["surprise"], ["recall"], ["focus"], ["controller", "regulator"]],
        "expected_domains": ["CLC"],
        "expected_sources": ["combined_mechanism"],
    },
    {
        "query": "G-CL anchor drift memory geometry domain update",
        "expected": ["G-CL", "anchor", "drift", "geometry", "domain"],
        "expected_concepts": [["G-CL"], ["anchor", "reference state"], ["drift"], ["geometry"], ["domain", "adapter"]],
        "expected_domains": ["G-CL"],
        "expected_sources": ["G-CL_SKILL"],
    },
    {
        "query": "CSD contradiction novelty density diagnostics",
        "expected": ["CSD", "contradiction", "novelty", "density", "diagnostic"],
        "expected_concepts": [["CSD", "constraint sensitivity"], ["contradiction", "residual", "anomaly"], ["novelty", "new structure"], ["density", "constraint geometry", "geometry scale"], ["diagnostic", "diagnoses", "diagnose"]],
        "expected_domains": ["CSD"],
        "expected_sources": ["CSD_SKILL"],
    },
    {
        "query": "EmbeddingGemma GGUF llama cpp 768 semantic vectors",
        "expected": ["EmbeddingGemma", "GGUF", "llama", "768", "vector"],
        "expected_concepts": [["EmbeddingGemma", "embedding-gemma"], ["GGUF"], ["llama", "llama_cpp"], ["768"], ["vector", "embedding"]],
        "expected_domains": ["OpenClaw", "CLC"],
        "expected_sources": ["GEOMETRY_GGUF_MIGRATION_RUNBOOK", "combined_mechanism"],
    },
    {
        "query": "geometry controller effective dimension curvature regime",
        "expected": ["geometry", "effective", "dimension", "curvature", "regime"],
        "expected_concepts": [["geometry controller", "LCM Geometry"], ["effective rank", "effective dimension", "eff_rank"], ["curvature", "drift"], ["regime", "PRODUCTIVE", "RIGID", "UNSTABLE"], ["branch", "controller"]],
        "expected_domains": ["OpenClaw"],
        "expected_sources": ["GEOMETRY_CONTROLLER_MANUAL"],
    },
]


def hit_score(text: str, expected: list[str]) -> float:
    haystack = text.lower()
    if not expected:
        return 0.0
    hits = sum(1 for term in expected if term.lower() in haystack)
    return hits / len(expected)


def field_score(values: list[str | None], expected: list[str] | None) -> float:
    if not expected:
        return 0.0
    normalized = [str(value or "").lower() for value in values]
    hits = 0
    for target in expected:
        target_l = target.lower()
        if any(target_l in value for value in normalized):
            hits += 1
    return hits / len(expected)


def concept_score(text: str, expected_concepts: list[list[str]] | None) -> float:
    if not expected_concepts:
        return 0.0
    haystack = text.lower()
    hits = 0
    for alternatives in expected_concepts:
        if any(term.lower() in haystack for term in alternatives):
            hits += 1
    return hits / len(expected_concepts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed retrieval probes against the configured memory DB")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    pipeline = create_pipeline(ROOT, db_path=Path(args.db_path) if args.db_path else None)
    start = time.perf_counter()
    try:
        cases = []
        for case in DEFAULT_CASES:
            results = pipeline.retrieve(case["query"], top_k=args.top_k)
            top_text = "\n".join(item["text"] for item in results[: args.top_k])
            score = hit_score(top_text, case["expected"])
            semantic_score = concept_score(top_text, case.get("expected_concepts"))
            domain_score = field_score([item.get("domain_name") for item in results], case.get("expected_domains"))
            source_score = field_score([item.get("source") for item in results], case.get("expected_sources"))
            cases.append(
                {
                    "query": case["query"],
                    "expected": case["expected"],
                    "expected_concepts": case.get("expected_concepts", []),
                    "expected_domains": case.get("expected_domains", []),
                    "expected_sources": case.get("expected_sources", []),
                    "hit_score": round(score, 4),
                    "concept_score": round(semantic_score, 4),
                    "domain_score": round(domain_score, 4),
                    "source_score": round(source_score, 4),
                    "top": [
                        {
                            "score": item["score"],
                            "cosine": item["cosine"],
                            "domain_name": item.get("domain_name"),
                            "source": item.get("source"),
                            "chunk_index": item.get("chunk_index"),
                            "memory_type": item["memory_type"],
                            "text_preview": item["text"][:220],
                        }
                        for item in results
                    ],
                }
            )
        payload = {
            "ok": True,
            "elapsed_sec": round(time.perf_counter() - start, 6),
            "mean_hit_score": round(sum(c["hit_score"] for c in cases) / len(cases), 4),
            "mean_concept_score": round(sum(c["concept_score"] for c in cases) / len(cases), 4),
            "mean_domain_score": round(sum(c["domain_score"] for c in cases) / len(cases), 4),
            "mean_source_score": round(sum(c["source_score"] for c in cases) / len(cases), 4),
            "stats": pipeline_stats(pipeline),
            "cases": cases,
        }
    finally:
        pipeline.close()

    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print(
        f"mean_hit_score={payload['mean_hit_score']} "
        f"mean_concept_score={payload['mean_concept_score']} "
        f"mean_domain_score={payload['mean_domain_score']} "
        f"mean_source_score={payload['mean_source_score']} elapsed_sec={payload['elapsed_sec']}"
    )
    for case in payload["cases"]:
        print(f"\nQUERY: {case['query']}")
        print(
            f"hit_score={case['hit_score']} domain_score={case['domain_score']} "
            f"source_score={case['source_score']} concept_score={case['concept_score']}"
        )
        for idx, item in enumerate(case["top"], start=1):
            print(
                f"{idx}. score={item['score']} cosine={item['cosine']} "
                f"domain={item.get('domain_name')} source={item.get('source')} "
                f"type={item['memory_type']} :: {item['text_preview']}"
            )


if __name__ == "__main__":
    main()
