from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


DOMAINS = {
    "agent_memory": [
        "Agent memory should preserve project decisions with evidence ids and session context.",
        "Agent memory should keep corrections linked to stale memories instead of deleting history.",
        "Agent memory should expose retrieval confidence, conflict state, and source files.",
        "Agent memory should use topic filtered session context for vague follow up questions.",
        "Agent memory should keep local experiments separate from uploaded GitHub state.",
        "Agent memory should evaluate answer quality after every retrieval change.",
    ],
    "CSD": [
        "CSD novelty diagnostics should normalize raw semantic drift against constraint geometry.",
        "CSD density diagnostics should detect sparse local neighborhoods around new memories.",
        "CSD contradiction diagnostics should mark direct corrections against close memories.",
        "CSD surprise should increase when novelty, density, contradiction, or domain shift rises.",
        "CSD recall should remain high when a new memory is close to the domain anchor.",
        "CSD curiosity should rise for novel non contradictory information with weak recall.",
    ],
    "G-CL": [
        "G-CL anchor drift should update domain anchors only when learning is compatible.",
        "G-CL geometry should track orthogonal drift, curvature, and effective dimension.",
        "G-CL should split domains when domain shift is high and recall is weak.",
        "G-CL should protect anchors when contradiction is high.",
        "G-CL stability should rise slowly for repeated recall and consolidation events.",
        "G-CL domain separation should reduce interference between unrelated knowledge streams.",
    ],
    "OpenClaw": [
        "OpenClaw geometry controller should keep the LCM database as the source of truth.",
        "OpenClaw geometry controller should use a read heavy companion geometry database.",
        "OpenClaw branch states should track forming, active, stable, tensioned, and dormant regimes.",
        "OpenClaw effective dimension should help detect branch complexity changes.",
        "OpenClaw GGUF migration should rebuild geometry vectors when embedding dimensions change.",
        "OpenClaw retrieval should prefer current branch context over unrelated branches.",
    ],
}


CORRECTIONS = [
    (
        "agent_memory",
        "Old agent memory policy: session turns should always become durable memories automatically.",
        "Correction: session turns should not always become durable memories automatically; durable promotion needs explicit selection.",
    ),
    (
        "G-CL",
        "Old G-CL policy: anchors should update on every high similarity memory.",
        "Correction: G-CL anchors should not update during protected contradictions even when similarity is high.",
    ),
    (
        "OpenClaw",
        "Old OpenClaw policy: geometry vectors may be reused after changing embedding dimensions.",
        "Correction: OpenClaw geometry vectors must be rebuilt after changing embedding dimensions.",
    ),
]


QUERIES = [
    {
        "id": "session_context",
        "query": "How should agent memory handle vague follow up questions?",
        "terms": ["topic filtered session context", "follow up"],
        "domain": "agent_memory",
    },
    {
        "id": "csd_contradiction",
        "query": "What should CSD do with direct corrections?",
        "terms": ["contradiction", "direct corrections"],
        "domain": "CSD",
    },
    {
        "id": "gcl_anchor_protect",
        "query": "When should G-CL protect anchors?",
        "terms": ["protect anchors", "contradiction"],
        "domain": "G-CL",
    },
    {
        "id": "openclaw_vectors",
        "query": "What should OpenClaw do after embedding dimensions change?",
        "terms": ["rebuilt", "embedding dimensions"],
        "domain": "OpenClaw",
    },
]


def source_for(domain: str, idx: int, correction: bool = False) -> str:
    suffix = "corrections" if correction else "stream"
    return f"long_run/{domain}/{suffix}_{idx:03d}.md"


def stream_items(cycles: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    index = 0
    for cycle in range(cycles):
        for domain, seeds in DOMAINS.items():
            seed = seeds[cycle % len(seeds)]
            variant = (
                f"{seed} Run cycle {cycle + 1}: this memory records ordered long-run drift behavior "
                f"for the {domain} domain while preserving stable retrieval."
            )
            items.append({"index": index, "domain": domain, "text": variant, "source": source_for(domain, index)})
            index += 1
        if cycle in {2, 5, 8}:
            correction_domain, old_text, correction_text = CORRECTIONS[(cycle // 3) % len(CORRECTIONS)]
            items.append({"index": index, "domain": correction_domain, "text": old_text, "source": source_for(correction_domain, index)})
            index += 1
            items.append(
                {
                    "index": index,
                    "domain": correction_domain,
                    "text": correction_text,
                    "source": source_for(correction_domain, index, correction=True),
                    "correction": True,
                }
            )
            index += 1
    return items


def init_pipeline(root: Path, db_path: Path, use_config_embedding: bool) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    if use_config_embedding:
        from core.runtime import create_pipeline

        return create_pipeline(ROOT, db_path=db_path)
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def compact_ingest(item: dict[str, Any], result: dict[str, Any], domains: list[dict[str, Any]]) -> dict[str, Any]:
    domain = next((row for row in domains if row["name"] == result["domain_name"]), None)
    return {
        "index": item["index"],
        "source_domain": item["domain"],
        "assigned_domain": result["domain_name"],
        "clc_state": result["clc_state"],
        "decision_reason": result["decision_reason"],
        "gcl_action": result["gcl_action"],
        "csd_score": result["csd_score"],
        "csd_density": result["csd_density"],
        "contradiction": result["contradiction"],
        "surprise": result["surprise"],
        "recall": result["recall"],
        "curiosity": result["curiosity"],
        "focus": result["focus"],
        "combined_drift": result["combined_drift"],
        "orthogonal_drift": result["orthogonal_drift"],
        "curvature": result["curvature"],
        "anchor_update_strength": result["anchor_update_strength"],
        "domain_effective_dimension": domain["effective_dimension"] if domain else None,
        "domain_drift_ema": domain["drift_ema"] if domain else None,
        "domain_curvature_ema": domain["curvature_ema"] if domain else None,
        "domain_stability": domain["stability"] if domain else None,
        "memory_id": result["memory_id"],
    }


def domain_snapshot(pipeline) -> list[dict[str, Any]]:
    return [
        {
            "id": domain.id,
            "name": domain.name,
            "memory_count": domain.memory_count,
            "effective_dimension": round(domain.effective_dimension, 4),
            "drift_ema": round(domain.drift_ema, 6),
            "curvature_ema": round(domain.curvature_ema, 6),
            "stability": round(domain.stability, 6),
        }
        for domain in pipeline.db.list_domains()
    ]


def score_terms(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower) / len(terms)


def evaluate_queries(pipeline, top_k: int) -> list[dict[str, Any]]:
    rows = []
    for case in QUERIES:
        results = pipeline.retrieve(case["query"], top_k=top_k)
        joined = "\n".join(item["text"] for item in results)
        domain_hits = sum(1 for item in results if item.get("domain_name") == case["domain"])
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                "domain": case["domain"],
                "term_score": round(score_terms(joined, case["terms"]), 4),
                "domain_precision": round(domain_hits / max(1, len(results)), 4),
                "top_domain": results[0].get("domain_name") if results else None,
                "top_score": results[0].get("score") if results else None,
                "top_preview": results[0].get("text", "")[:220] if results else "",
            }
        )
    return rows


def mean(rows: list[float]) -> float:
    return round(sum(rows) / len(rows), 6) if rows else 0.0


def summarize_trace(trace: list[dict[str, Any]], query_checks: list[dict[str, Any]]) -> dict[str, Any]:
    states: dict[str, int] = {}
    actions: dict[str, int] = {}
    for row in trace:
        states[row["clc_state"]] = states.get(row["clc_state"], 0) + 1
        actions[row["gcl_action"]] = actions.get(row["gcl_action"], 0) + 1
    contradictions = [row for row in trace if row["contradiction"] > 0.75]
    anchor_updates = [row for row in trace if row["gcl_action"] == "anchor_update"]
    return {
        "items": len(trace),
        "state_counts": states,
        "action_counts": actions,
        "mean_csd_score": mean([row["csd_score"] for row in trace]),
        "mean_csd_density": mean([row["csd_density"] for row in trace]),
        "mean_recall": mean([row["recall"] for row in trace]),
        "mean_surprise": mean([row["surprise"] for row in trace]),
        "mean_combined_drift": mean([row["combined_drift"] for row in trace]),
        "mean_orthogonal_drift": mean([row["orthogonal_drift"] for row in trace]),
        "max_curvature": max((row["curvature"] for row in trace), default=0.0),
        "contradiction_count": len(contradictions),
        "protected_contradictions": sum(1 for row in contradictions if row["clc_state"] == "PROTECT" and row["gcl_action"] == "no_anchor_update"),
        "anchor_update_count": len(anchor_updates),
        "mean_query_term_score": mean([row["term_score"] for row in query_checks]),
        "mean_query_domain_precision": mean([row["domain_precision"] for row in query_checks]),
    }


def run(db_path: Path, cycles: int, checkpoint_every: int, top_k: int, use_config_embedding: bool) -> dict[str, Any]:
    root = db_path.parent
    pipeline = init_pipeline(root, db_path, use_config_embedding=use_config_embedding)
    trace: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    try:
        items = stream_items(cycles)
        for idx, item in enumerate(items, start=1):
            result = pipeline.ingest(item["text"], source=item["source"])
            pipeline.db.set_memory_source(result["memory_id"], item["source"], 0, metadata={"long_run_domain": item["domain"]})
            domains = domain_snapshot(pipeline)
            trace.append(compact_ingest(item, result, domains))
            if idx % checkpoint_every == 0 or idx == len(items):
                query_checks = evaluate_queries(pipeline, top_k=top_k)
                checkpoints.append(
                    {
                        "after_items": idx,
                        "summary": summarize_trace(trace, query_checks),
                        "domains": domains,
                        "query_checks": query_checks,
                    }
                )
        final_queries = evaluate_queries(pipeline, top_k=top_k)
        final_domains = domain_snapshot(pipeline)
        stats = pipeline.db.stats()
    finally:
        pipeline.close()
    summary = summarize_trace(trace, final_queries)
    checks = {
        "domains_created": len({row["assigned_domain"] for row in trace}) >= 4,
        "anchor_updates_happen": summary["anchor_update_count"] >= max(4, cycles // 2),
        "contradictions_protected": summary["contradiction_count"] == summary["protected_contradictions"],
        "retrieval_terms_retained": summary["mean_query_term_score"] >= 0.75,
        "domain_precision_reasonable": summary["mean_query_domain_precision"] >= 0.60,
        "effective_dimension_grows": max((domain["effective_dimension"] for domain in final_domains), default=1.0) > 1.0,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": summary,
        "checkpoints": checkpoints,
        "final_domains": final_domains,
        "final_query_checks": final_queries,
        "trace_tail": trace[-10:],
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-run CSD/G-CL drift and retrieval diagnostic")
    parser.add_argument("--db-path", default=None, help="Optional DB path. Defaults to a temporary DB.")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--use-config-embedding", action="store_true", help="Use config.yaml embedding backend instead of fast hash embeddings.")
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(db_path, args.cycles, args.checkpoint_every, args.top_k, args.use_config_embedding)
    else:
        with TemporaryDirectory() as tmp:
            payload = run(Path(tmp) / "long_run_drift.db", args.cycles, args.checkpoint_every, args.top_k, args.use_config_embedding)
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
