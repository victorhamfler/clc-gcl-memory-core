from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from core.resolver import resolve_answer
from eval.mechanism_ablation_eval import vector_only_retrieve
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


DOMAIN_DOCS = {
    "agent_memory": [
        "Agent memory retrieval should use topic filtered session context for vague follow up questions.",
        "Agent memory should preserve evidence ids, source paths, confidence, and conflict state.",
        "Agent memory should keep corrections linked to stale memories instead of deleting old knowledge.",
        "Agent memory should promote session turns into durable memory only when selected.",
    ],
    "CSD": [
        "CSD diagnostics should normalize raw semantic drift before calling novelty high.",
        "CSD contradiction diagnostics should protect anchors when direct negating corrections appear.",
        "CSD density diagnostics should report sparse local neighborhoods around new memories.",
        "CSD surprise combines novelty, density, contradiction, and domain shift.",
    ],
    "G-CL": [
        "G-CL anchor drift should update domain anchors only for compatible learning.",
        "G-CL geometry should track orthogonal drift, curvature, and effective dimension.",
        "G-CL should split domains when domain shift is high and recall is weak.",
        "G-CL should protect anchors during contradictions to reduce interference.",
    ],
    "OpenClaw": [
        "OpenClaw geometry controller should keep LCM as the source of truth.",
        "OpenClaw geometry controller should use a read heavy companion geometry database.",
        "OpenClaw branch states should include forming, active, stable, tensioned, and dormant.",
        "OpenClaw GGUF migration should rebuild vectors after embedding dimensions change.",
    ],
}


DISTRACTORS = [
    "General project note: retrieval, correction, and memory testing should be measured with repeatable evaluation scripts.",
    "General engineering note: confidence and source evidence should be visible in local experiments.",
    "General planning note: domain contamination tests should use similar words across unrelated topics.",
]


QUERIES = [
    {
        "id": "agent_memory_followups",
        "query": "How should agent memory retrieval handle vague follow up questions?",
        "domain": "agent_memory",
        "terms": ["topic filtered session context", "follow up"],
        "forbidden": ["orthogonal drift", "LCM", "raw semantic drift"],
    },
    {
        "id": "csd_novelty",
        "query": "How should CSD decide whether novelty is high?",
        "domain": "CSD",
        "terms": ["normalize raw semantic drift", "novelty high"],
        "forbidden": ["topic filtered session context", "anchor drift", "LCM"],
    },
    {
        "id": "gcl_geometry",
        "query": "What should G-CL geometry track for domain stability?",
        "domain": "G-CL",
        "terms": ["orthogonal drift", "curvature", "effective dimension"],
        "forbidden": ["raw semantic drift", "topic filtered session context", "LCM"],
    },
    {
        "id": "openclaw_source",
        "query": "What should the OpenClaw geometry controller use as the source of truth?",
        "domain": "OpenClaw",
        "terms": ["LCM", "source of truth"],
        "forbidden": ["topic filtered session context", "raw semantic drift", "anchor drift"],
    },
]


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def seed_corpus(pipeline: MemoryPipeline) -> dict[str, Any]:
    stored: list[dict[str, Any]] = []
    for domain, docs in DOMAIN_DOCS.items():
        for idx, text in enumerate(docs):
            result = pipeline.ingest(text, source=f"domain_contamination/{domain}/doc_{idx:02d}.md")
            pipeline.db.set_memory_source(result["memory_id"], f"domain_contamination/{domain}/doc_{idx:02d}.md", 0)
            stored.append({"domain": domain, "memory_id": result["memory_id"], "assigned_domain": result["domain_name"]})
    for idx, text in enumerate(DISTRACTORS):
        result = pipeline.ingest(text, source=f"domain_contamination/general/distractor_{idx:02d}.md")
        pipeline.db.set_memory_source(result["memory_id"], f"domain_contamination/general/distractor_{idx:02d}.md", 0)
        stored.append({"domain": "general", "memory_id": result["memory_id"], "assigned_domain": result["domain_name"]})
    return {"stored": len(stored), "items": stored}


def score_terms(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower) / len(terms)


def contamination_score(text: str, forbidden: list[str]) -> float:
    if not forbidden:
        return 0.0
    lower = text.lower()
    return sum(1 for term in forbidden if term.lower() in lower) / len(forbidden)


def evaluate_case(case: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    answer = resolve_answer(case["query"], results)
    joined = "\n".join(item["text"] for item in results)
    expected_domain = case["domain"]
    top_domain = results[0].get("domain_name") if results else None
    domain_hits = sum(1 for item in results if item.get("domain_name") == expected_domain)
    evidence_hits = sum(1 for item in answer["evidence"] if item.get("domain_name") == expected_domain)
    wrong = [
        {
            "memory_id": item["memory_id"],
            "domain_name": item.get("domain_name"),
            "score": item.get("score"),
            "source": item.get("source"),
            "text_preview": item["text"][:180],
        }
        for item in results
        if item.get("domain_name") != expected_domain
    ]
    return {
        "id": case["id"],
        "query": case["query"],
        "expected_domain": expected_domain,
        "top_domain": top_domain,
        "top_domain_correct": top_domain == expected_domain,
        "domain_precision": round(domain_hits / max(1, len(results)), 4),
        "evidence_domain_precision": round(evidence_hits / max(1, len(answer["evidence"])), 4),
        "term_score": round(score_terms(joined, case["terms"]), 4),
        "answer_term_score": round(score_terms(answer["answer"], case["terms"]), 4),
        "contamination_score": round(contamination_score(joined, case["forbidden"]), 4),
        "answer_contamination_score": round(contamination_score(answer["answer"], case["forbidden"]), 4),
        "answer": answer["answer"],
        "evidence": answer["evidence"],
        "wrong_domain_results": wrong,
        "top": [
            {
                "memory_id": item["memory_id"],
                "domain_name": item.get("domain_name"),
                "score": item.get("score"),
                "cosine": item.get("cosine"),
                "source": item.get("source"),
                "text_preview": item["text"][:180],
            }
            for item in results
        ],
    }


def evaluate_mode(pipeline: MemoryPipeline, mode: str, top_k: int) -> list[dict[str, Any]]:
    rows = []
    for case in QUERIES:
        if mode == "vector_only":
            results = vector_only_retrieve(pipeline, case["query"], top_k=top_k)
        else:
            results = pipeline.retrieve(case["query"], top_k=top_k)
        rows.append(evaluate_case(case, results))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "top_domain_accuracy": round(sum(1 for row in rows if row["top_domain_correct"]) / len(rows), 4),
        "mean_domain_precision": round(sum(row["domain_precision"] for row in rows) / len(rows), 4),
        "mean_evidence_domain_precision": round(sum(row["evidence_domain_precision"] for row in rows) / len(rows), 4),
        "mean_term_score": round(sum(row["term_score"] for row in rows) / len(rows), 4),
        "mean_answer_term_score": round(sum(row["answer_term_score"] for row in rows) / len(rows), 4),
        "mean_contamination_score": round(sum(row["contamination_score"] for row in rows) / len(rows), 4),
        "mean_answer_contamination_score": round(sum(row["answer_contamination_score"] for row in rows) / len(rows), 4),
    }


def run(top_k: int) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "domain_contamination.db")
        try:
            seed = seed_corpus(pipeline)
            vector_rows = evaluate_mode(pipeline, "vector_only", top_k=top_k)
            enhanced_rows = evaluate_mode(pipeline, "enhanced", top_k=top_k)
            stats = pipeline.db.stats()
            domains = [
                {
                    "name": domain.name,
                    "memory_count": domain.memory_count,
                    "effective_dimension": round(domain.effective_dimension, 4),
                    "drift_ema": round(domain.drift_ema, 6),
                    "curvature_ema": round(domain.curvature_ema, 6),
                }
                for domain in pipeline.db.list_domains()
            ]
        finally:
            pipeline.close()
    vector_summary = summarize(vector_rows)
    enhanced_summary = summarize(enhanced_rows)
    checks = {
        "enhanced_top_domain_perfect": enhanced_summary["top_domain_accuracy"] == 1.0,
        "enhanced_domain_precision_reasonable": enhanced_summary["mean_domain_precision"] >= 0.75,
        "enhanced_answer_contamination_low": enhanced_summary["mean_answer_contamination_score"] <= 0.05,
        "enhanced_not_worse_than_vector": enhanced_summary["mean_domain_precision"] >= vector_summary["mean_domain_precision"],
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "summaries": {
            "vector_only": vector_summary,
            "enhanced": enhanced_summary,
        },
        "deltas": {
            "domain_precision": round(enhanced_summary["mean_domain_precision"] - vector_summary["mean_domain_precision"], 4),
            "top_domain_accuracy": round(enhanced_summary["top_domain_accuracy"] - vector_summary["top_domain_accuracy"], 4),
            "answer_contamination": round(enhanced_summary["mean_answer_contamination_score"] - vector_summary["mean_answer_contamination_score"], 4),
        },
        "cases": {
            "vector_only": vector_rows,
            "enhanced": enhanced_rows,
        },
        "seed": seed,
        "domains": domains,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure wrong-domain retrieval and answer contamination")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    payload = run(top_k=args.top_k)
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
