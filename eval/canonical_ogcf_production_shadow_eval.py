from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicySelector  # noqa: E402
from core.config import load_config  # noqa: E402
from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer  # noqa: E402
from core.ogcf_selector import augment_selector_features  # noqa: E402
from core.pipeline import DEFAULT_CANONICAL_MEMORY_CONFIG, MemoryPipeline  # noqa: E402
from core.runtime import resolve_embedding_cache_path, runtime_embedding_config  # noqa: E402
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
DEFAULT_OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_production_shadow_eval_results.json"
DEFAULT_OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_production_shadow_eval_report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a read-only four-mode selector shadow eval over a real or copied memory DB. "
            "Modes: base, canonical, ogcf, combined."
        )
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config-path", type=Path, default=ROOT / "config.yaml")
    parser.add_argument(
        "--embedding-backend",
        choices=("auto", "config", "hash"),
        default="auto",
        help="Embedding runtime for query retrieval. Auto uses DB runtime_state when possible.",
    )
    parser.add_argument("--embedding-dim", type=int, default=None)
    parser.add_argument(
        "--embedding-normalize",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override embedding normalize flag for query retrieval; useful for raw-Gemma OGCF fixtures.",
    )
    parser.add_argument("--queries-json", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--query-limit", type=int, default=24)
    parser.add_argument("--ogcf-sample-limit", type=int, default=384)
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--include-global", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-ogcf", action="store_true")
    parser.add_argument(
        "--normalize-embeddings",
        action="store_true",
        help="Normalize embeddings before OGCF geometry. Default keeps stored unnormalized geometry.",
    )
    return parser.parse_args()


def canonical_config(enabled: bool) -> dict[str, Any]:
    cfg = dict(DEFAULT_CANONICAL_MEMORY_CONFIG)
    cfg["enabled"] = enabled
    return cfg


def db_embedding_signature(db_path: Path) -> dict[str, Any] | None:
    db = MemoryDB(db_path)
    try:
        signature = db.get_runtime_state("embedding_signature")
    finally:
        db.close()
    return signature if isinstance(signature, dict) else None


def apply_embedding_override(
    config: dict[str, Any],
    *,
    db_path: Path,
    backend: str,
    embedding_dim: int | None,
    embedding_normalize: bool | None,
) -> dict[str, Any]:
    out = copy.deepcopy(config)
    selected = str(backend or "auto").lower()
    signature = db_embedding_signature(db_path) if selected == "auto" else None
    if selected == "hash" or (selected == "auto" and signature and signature.get("backend") == "hash"):
        dim = int(embedding_dim or (signature or {}).get("embedding_dim") or out.get("embedding_dim") or 128)
        out["embedding_dim"] = dim
        out["embedding"] = {"backend": "hash", "dim": dim}
    elif embedding_dim is not None:
        out["embedding_dim"] = int(embedding_dim)
    if embedding_normalize is not None:
        embedding = dict(out.get("embedding") or {})
        embedding["normalize"] = bool(embedding_normalize)
        out["embedding"] = embedding
    return out


def strip_canonical(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if not key.startswith("canonical_")}
        for row in rows
    ]


def load_query_payload(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(item.get("query") if isinstance(item, dict) else item).strip() for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("queries"), list):
        return [
            str(item.get("query") if isinstance(item, dict) else item).strip()
            for item in payload["queries"]
        ]
    raise ValueError(f"Unsupported queries JSON shape: {path}")


def text_probe(text: str) -> str:
    words = [part.strip(" ,.;:!?()[]{}\"'") for part in str(text or "").split()]
    words = [word for word in words if word]
    if not words:
        return ""
    return " ".join(words[: min(14, len(words))])


def generated_queries(db_path: Path, limit: int) -> list[str]:
    db = MemoryDB(db_path)
    try:
        rows = db.list_memory_vectors(include_deprecated=False)
    finally:
        db.close()
    queries: list[str] = []
    seen: set[str] = set()
    stride = max(1, len(rows) // max(1, limit * 3))
    for row in rows[::stride]:
        probe = text_probe(str(row.get("text") or ""))
        if len(probe) < 16:
            continue
        query = f"What should the agent remember about {probe}?"
        key = " ".join(query.lower().split())
        if key not in seen:
            seen.add(key)
            queries.append(query)
        if len(queries) >= limit:
            break
    return queries


def sampled_vector_rows(db_path: Path, limit: int) -> list[dict[str, Any]]:
    db = MemoryDB(db_path)
    try:
        rows = db.list_memory_vectors(include_deprecated=False)
    finally:
        db.close()
    if limit <= 0 or len(rows) <= limit:
        return rows
    stride = max(1, len(rows) // limit)
    sampled = rows[::stride][:limit]
    if len(sampled) < min(limit, len(rows)):
        sampled = rows[:limit]
    return sampled


def build_ogcf_meta(
    db_path: Path,
    *,
    sample_limit: int,
    normalize_embeddings: bool,
) -> dict[str, Any]:
    rows = sampled_vector_rows(db_path, sample_limit)
    vectors = [row.get("embedding") for row in rows if row.get("embedding")]
    memory_ids = [str(row.get("id")) for row in rows if row.get("embedding")]
    if len(vectors) < 12:
        return {
            "ok": False,
            "reason": "not_enough_vectors",
            "vector_count": len(vectors),
            "memory_cluster_map": {},
        }

    embeddings = np.asarray(vectors, dtype=float)
    if normalize_embeddings:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-12)

    n = embeddings.shape[0]
    dim = embeddings.shape[1]
    n_clusters = max(3, min(60, int(math.sqrt(n) * 2), n - 1))
    rank_k = max(2, min(8, dim, n_clusters - 1))
    neighbors = max(2, min(5, n - 1))
    engine = OGCFGeometryEngine(
        n_clusters=n_clusters,
        rank_k=rank_k,
        neighbors=neighbors,
        random_baselines=8,
        seed=42,
    )
    reviewer = OGCFMemoryReviewer(engine)
    geo = engine.analyze(embeddings, memory_ids, db_path)

    risk_regions: list[dict[str, Any]] = []
    for loop in geo.loops:
        risk_regions.append(
            {
                "clusters": f"{loop.cluster_a}-{loop.cluster_b}-{loop.cluster_c}",
                "interaction_z": round(loop.interaction_z, 4),
                "interaction_excess": round(loop.interaction_excess, 6),
                "local_defect_z_mean": round(loop.local_defect_z_mean, 4),
                "failure_mode": reviewer._failure_mode(loop),
                "recommended_action": reviewer._loop_action(loop),
                "cluster_sizes": f"{loop.cluster_size_a}-{loop.cluster_size_b}-{loop.cluster_size_c}",
            }
        )
    max_interaction_z = max((loop.interaction_z for loop in geo.loops), default=0.0)
    report = {
        "config": {
            "n_clusters": geo.n_clusters,
            "rank_k": geo.rank_k,
            "neighbors": geo.neighbors,
        },
        "embedding_norm_stats": geo.embedding_norm_stats,
        "loop_count": len(geo.loops),
        "max_interaction_z": round(max_interaction_z, 4),
        "bridge_overload_score": round(max(0.0, min(1.0, max_interaction_z / 3.0)), 4),
        "risk_regions": sorted(risk_regions, key=lambda x: x["interaction_z"], reverse=True),
        "bridge_clusters": reviewer._detect_bridge_clusters(geo, memory_ids, db_path),
        "cluster_summary": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "local_defect": round(c.local_defect, 4),
                "top_domain": c.top_domain,
            }
            for c in geo.clusters
        ],
    }
    report["ok"] = True
    report["vector_count"] = len(memory_ids)
    report["normalized_embeddings"] = bool(normalize_embeddings)
    report["memory_cluster_map"] = {
        memory_id: int(label)
        for memory_id, label in zip(memory_ids, geo.labels)
    }
    return report


def run_pipeline(
    db_path: Path,
    *,
    canonical_enabled: bool,
    config: dict[str, Any],
) -> MemoryPipeline:
    embedding_config = resolve_embedding_cache_path(ROOT, runtime_embedding_config(config))
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_dim=int(config.get("embedding_dim") or 128),
        top_k=int(config.get("top_k") or 8),
        embedding_config=embedding_config,
        retrieval_weights=config.get("retrieval_weights"),
        symbolic_config=config.get("symbolic"),
        claim_scope_config=config.get("claim_scope"),
        answer_type_config=config.get("answer_type"),
        retrieval_signal_config=config.get("retrieval_signals"),
        evidence_state_config=config.get("evidence_states"),
        canonical_memory_config=canonical_config(canonical_enabled),
        llm_config=config.get("llm"),
        clc_thresholds=config.get("thresholds"),
    )


def run_mode(
    pipeline: MemoryPipeline,
    query: str,
    *,
    top_k: int,
    namespace: str | None,
    include_global: bool,
    canonical: bool,
    ogcf: bool,
    ogcf_meta: dict[str, Any] | None,
    ogcf_intent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retrieved_rows = pipeline.retrieve(
        query,
        top_k=top_k,
        namespace=namespace,
        include_global=include_global,
    )
    rows = copy.deepcopy(retrieved_rows if canonical else strip_canonical(retrieved_rows))
    features, diagnostics = selector_features_from_retrieval_context(
        rows,
        condition_name="standard_budget144",
    )
    if ogcf:
        features, diagnostics = augment_selector_features(
            features,
            rows,
            ogcf_meta,
            diagnostics,
            query=query,
            ogcf_intent_config=ogcf_intent_config,
        )
    decision = CLCPolicySelector().select(features)
    return {
        "decision": asdict(decision),
        "features": asdict(features),
        "diagnostics": diagnostics,
        "top_memory_ids": [str(row.get("memory_id") or row.get("id")) for row in rows[:top_k]],
        "top_scores": [row.get("score") for row in rows[: min(3, len(rows))]],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    modes = ("base", "canonical", "ogcf", "combined")
    summary: dict[str, Any] = {}
    for mode in modes:
        actions = Counter(item["modes"][mode]["decision"]["action"] for item in results)
        avg_mbr = sum(float(item["modes"][mode]["features"]["memory_bad_rate"]) for item in results) / max(1, len(results))
        avg_probe = sum(float(item["modes"][mode]["features"]["probe_drop"]) for item in results) / max(1, len(results))
        avg_csd = sum(float(item["modes"][mode]["features"]["csd_ratio"]) for item in results) / max(1, len(results))
        summary[mode] = {
            "action_counts": dict(sorted(actions.items())),
            "avg_memory_bad_rate": round(avg_mbr, 6),
            "avg_probe_drop": round(avg_probe, 6),
            "avg_csd_ratio": round(avg_csd, 6),
        }
    canonical_changed = sum(
        1 for item in results
        if item["modes"]["base"]["decision"]["action"] != item["modes"]["canonical"]["decision"]["action"]
    )
    ogcf_changed = sum(
        1 for item in results
        if item["modes"]["base"]["decision"]["action"] != item["modes"]["ogcf"]["decision"]["action"]
    )
    combined_changed = sum(
        1 for item in results
        if item["modes"]["canonical"]["decision"]["action"] != item["modes"]["combined"]["decision"]["action"]
    )
    return {
        "query_count": len(results),
        "modes": summary,
        "policy_deltas": {
            "canonical_vs_base": canonical_changed,
            "ogcf_vs_base": ogcf_changed,
            "combined_vs_canonical": combined_changed,
        },
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Canonical + OGCF Production Shadow Eval",
        "",
        f"DB: `{payload['db_path']}`",
        f"Queries: {payload['summary']['query_count']}",
        f"OGCF enabled: {payload['ogcf_meta'].get('ok', False)}",
        f"OGCF vector count: {payload['ogcf_meta'].get('vector_count', 0)}",
        f"OGCF bridge overload score: {payload['ogcf_meta'].get('bridge_overload_score', 0.0)}",
        f"OGCF max interaction z: {payload['ogcf_meta'].get('max_interaction_z', 0.0)}",
        "",
        "## Policy Distribution",
        "",
        "| Mode | Action counts | Avg MBR | Avg probe | Avg CSD |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for mode, row in payload["summary"]["modes"].items():
        lines.append(
            f"| {mode} | `{json.dumps(row['action_counts'], sort_keys=True)}` | "
            f"{row['avg_memory_bad_rate']} | {row['avg_probe_drop']} | {row['avg_csd_ratio']} |"
        )
    lines.extend(
        [
            "",
            "## Policy Deltas",
            "",
            "```json",
            json.dumps(payload["summary"]["policy_deltas"], indent=2),
            "```",
            "",
            "## Query Details",
            "",
            "| # | Query | Base | Canonical | OGCF | Combined | OGCF affected |",
            "| ---: | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for idx, item in enumerate(payload["results"], start=1):
        query = str(item["query"]).replace("|", "\\|")[:110]
        row = item["modes"]
        affected = row["combined"]["diagnostics"].get("ogcf_affected_memory_ratio", 0.0)
        lines.append(
            f"| {idx} | {query} | {row['base']['decision']['action']} | "
            f"{row['canonical']['decision']['action']} | {row['ogcf']['decision']['action']} | "
            f"{row['combined']['decision']['action']} | {affected} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    db_path = args.db_path.resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    config = load_config(args.config_path.parent) if args.config_path.exists() else load_config(ROOT)
    config = apply_embedding_override(
        config,
        db_path=db_path,
        backend=args.embedding_backend,
        embedding_dim=args.embedding_dim,
        embedding_normalize=args.embedding_normalize,
    )

    queries = [q for q in load_query_payload(args.queries_json) if q]
    if not queries:
        queries = generated_queries(db_path, args.query_limit)
    queries = queries[: max(1, int(args.query_limit))]
    if not queries:
        raise RuntimeError("No queries available for shadow eval")

    ogcf_meta: dict[str, Any] | None = None
    if not args.skip_ogcf:
        ogcf_meta = build_ogcf_meta(
            db_path,
            sample_limit=max(12, int(args.ogcf_sample_limit)),
            normalize_embeddings=bool(args.normalize_embeddings),
        )
    else:
        ogcf_meta = {"ok": False, "reason": "skip_ogcf", "memory_cluster_map": {}}

    base_pipeline = run_pipeline(db_path, canonical_enabled=False, config=config)
    canonical_pipeline = run_pipeline(db_path, canonical_enabled=True, config=config)
    ogcf_intent_config = config.get("ogcf_intent")
    try:
        results = []
        for query in queries:
            modes = {
                "base": run_mode(
                    base_pipeline,
                    query,
                    top_k=args.top_k,
                    namespace=args.namespace,
                    include_global=args.include_global,
                    canonical=False,
                    ogcf=False,
                    ogcf_meta=None,
                    ogcf_intent_config=ogcf_intent_config,
                ),
                "canonical": run_mode(
                    canonical_pipeline,
                    query,
                    top_k=args.top_k,
                    namespace=args.namespace,
                    include_global=args.include_global,
                    canonical=True,
                    ogcf=False,
                    ogcf_meta=None,
                    ogcf_intent_config=ogcf_intent_config,
                ),
                "ogcf": run_mode(
                    base_pipeline,
                    query,
                    top_k=args.top_k,
                    namespace=args.namespace,
                    include_global=args.include_global,
                    canonical=False,
                    ogcf=True,
                    ogcf_meta=ogcf_meta,
                    ogcf_intent_config=ogcf_intent_config,
                ),
                "combined": run_mode(
                    canonical_pipeline,
                    query,
                    top_k=args.top_k,
                    namespace=args.namespace,
                    include_global=args.include_global,
                    canonical=True,
                    ogcf=True,
                    ogcf_meta=ogcf_meta,
                    ogcf_intent_config=ogcf_intent_config,
                ),
            }
            results.append({"query": query, "modes": modes})
    finally:
        base_pipeline.close()
        canonical_pipeline.close()

    payload = {
        "ok": True,
        "db_path": str(db_path),
        "top_k": int(args.top_k),
        "config_path": str(args.config_path.resolve()) if args.config_path else None,
        "embedding_backend": args.embedding_backend,
        "embedding_normalize": args.embedding_normalize,
        "namespace": args.namespace,
        "include_global": bool(args.include_global),
        "ogcf_meta": ogcf_meta or {},
        "summary": summarize(results),
        "results": results,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.out_md.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(args.out_json), "markdown": str(args.out_md), "summary": payload["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
