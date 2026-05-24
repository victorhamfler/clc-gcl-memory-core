from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OGCF_CACHE = REPO_ROOT / "experiments" / "ogcf_next_cache"
DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
DEFAULT_IDS = OGCF_CACHE / "sampled_2000_ids.json"
DEFAULT_RAW = OGCF_CACHE / "gemma_raw_embeddings_2000.npy"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_unnormalized_bridge_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_unnormalized_bridge_eval_report.md"
sys.path.insert(0, str(ROOT))

from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer  # noqa: E402


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def parse_embedding(value: Any) -> list[float]:
    raw = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value or "")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [float(x) for x in loaded] if isinstance(loaded, list) else []


def norm_stats(embeddings: np.ndarray) -> dict[str, float]:
    norms = np.linalg.norm(embeddings, axis=1)
    return {
        "min": float(norms.min()),
        "mean": float(norms.mean()),
        "max": float(norms.max()),
        "std": float(norms.std()),
    }


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def quality(row: dict[str, Any]) -> tuple[float, str, str]:
    return (
        float(row.get("confidence") or 0.0) * float(row.get("importance") or 0.0),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def load_db_rows(db_path: Path, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows: dict[str, dict[str, Any]] = {}
    for memory_id in memory_ids:
        row = conn.execute(
            """
            SELECT m.id, m.text, m.domain_id, m.namespace, m.importance, m.confidence,
                   m.created_at, m.deprecated, v.embedding
            FROM memories m
            JOIN vectors v ON v.memory_id = m.id
            WHERE m.id = ?
            """,
            (memory_id,),
        ).fetchone()
        if not row:
            continue
        item = dict(row)
        item["normalized_text"] = normalize_text(item.get("text"))
        item["db_embedding"] = parse_embedding(item.get("embedding"))
        rows[memory_id] = item
    conn.close()
    return rows


def exact_dedup_indices(rows: list[dict[str, Any]]) -> list[int]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["normalized_text"]].append(index)
    keep = []
    for indices in groups.values():
        keeper = max(indices, key=lambda idx: quality(rows[idx]))
        keep.append(keeper)
    return sorted(keep)


def duplicate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["normalized_text"] for row in rows)
    duplicate_groups = [(text, count) for text, count in counts.items() if count > 1]
    duplicate_groups.sort(key=lambda item: (-item[1], item[0]))
    return {
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_memory_count": sum(count - 1 for _, count in duplicate_groups),
        "top_duplicate_texts": [
            {"text": text[:240], "count": count}
            for text, count in duplicate_groups[:10]
        ],
    }


def cluster_text_summary(
    labels: np.ndarray,
    rows: list[dict[str, Any]],
    cluster_id: int,
    limit: int = 5,
) -> dict[str, Any]:
    cluster_rows = [row for index, row in enumerate(rows) if int(labels[index]) == int(cluster_id)]
    text_counts = Counter(row["normalized_text"] for row in cluster_rows)
    domain_counts = Counter(str(row.get("domain_id") or "") for row in cluster_rows)
    return {
        "cluster_id": int(cluster_id),
        "size": len(cluster_rows),
        "unique_texts": len(text_counts),
        "unique_domains": len(domain_counts),
        "top_texts": [
            {"text": text[:240], "count": count}
            for text, count in text_counts.most_common(limit)
        ],
        "top_domains": [
            {"domain_id": domain, "count": count}
            for domain, count in domain_counts.most_common(limit)
        ],
    }


def run_geometry_variant(
    name: str,
    rows: list[dict[str, Any]],
    embeddings: np.ndarray,
    db_path: Path,
    *,
    n_clusters: int,
    rank_k: int,
    neighbors: int,
    random_baselines: int,
) -> dict[str, Any]:
    n_clusters = max(2, min(int(n_clusters), len(rows) - 1))
    engine = OGCFGeometryEngine(
        n_clusters=n_clusters,
        rank_k=rank_k,
        neighbors=neighbors,
        random_baselines=random_baselines,
        seed=42,
    )
    memory_ids = [str(row["id"]) for row in rows]
    geo = engine.analyze(embeddings.astype(np.float32), memory_ids, db_path)
    reviewer = OGCFMemoryReviewer(engine)
    bridge_clusters = reviewer._detect_bridge_clusters(geo, memory_ids, db_path)
    loops = sorted(
        [
            {
                "clusters": f"{loop.cluster_a}-{loop.cluster_b}-{loop.cluster_c}",
                "interaction_z": round(float(loop.interaction_z), 6),
                "interaction_excess": round(float(loop.interaction_excess), 6),
                "holonomy_rank_norm": round(float(loop.holonomy_rank_norm), 6),
                "cluster_sizes": f"{loop.cluster_size_a}-{loop.cluster_size_b}-{loop.cluster_size_c}",
            }
            for loop in geo.loops
        ],
        key=lambda item: item["interaction_z"],
        reverse=True,
    )
    top_bridge_clusters = []
    for bridge in bridge_clusters[:8]:
        summary = cluster_text_summary(geo.labels, rows, int(bridge["cluster_id"]))
        summary.update(
            {
                "local_defect": bridge.get("local_defect"),
                "domain_count_ratio": round(float(bridge.get("unique_domains") or 0) / max(1, int(bridge.get("size") or 1)), 6),
            }
        )
        top_bridge_clusters.append(summary)
    return {
        "name": name,
        "row_count": len(rows),
        "n_clusters": n_clusters,
        "rank_k": rank_k,
        "neighbors": neighbors,
        "random_baselines": random_baselines,
        "embedding_norm_stats": norm_stats(embeddings),
        "loop_count": len(geo.loops),
        "max_interaction_z": round(max((float(loop.interaction_z) for loop in geo.loops), default=0.0), 6),
        "max_interaction_excess": round(max((float(loop.interaction_excess) for loop in geo.loops), default=0.0), 6),
        "bridge_cluster_count": len(bridge_clusters),
        "top_loops": loops[:10],
        "top_bridge_clusters": top_bridge_clusters,
    }


def build_report(
    db_path: Path,
    ids_path: Path,
    raw_embeddings_path: Path,
    *,
    n_clusters: int = 60,
    rank_k: int = 8,
    neighbors: int = 5,
    random_baselines: int = 20,
) -> dict[str, Any]:
    memory_ids = json.loads(ids_path.read_text(encoding="utf-8"))
    if not isinstance(memory_ids, list):
        raise ValueError(f"Expected sampled ids list in {ids_path}")
    raw_embeddings = np.load(raw_embeddings_path)
    if raw_embeddings.shape[0] != len(memory_ids):
        raise ValueError(f"Raw embedding count {raw_embeddings.shape[0]} does not match id count {len(memory_ids)}")
    row_by_id = load_db_rows(db_path, [str(mid) for mid in memory_ids])
    rows: list[dict[str, Any]] = []
    raw_kept = []
    db_kept = []
    for index, memory_id in enumerate(memory_ids):
        row = row_by_id.get(str(memory_id))
        if not row or not row.get("db_embedding"):
            continue
        rows.append(row)
        raw_kept.append(raw_embeddings[index])
        db_kept.append(row["db_embedding"])
    raw = np.array(raw_kept, dtype=np.float32)
    normalized = np.array(db_kept, dtype=np.float32)
    keep_indices = exact_dedup_indices(rows)
    dedup_rows = [rows[index] for index in keep_indices]
    raw_dedup = raw[keep_indices]

    variants = [
        run_geometry_variant(
            "normalized_db_vectors",
            rows,
            normalized,
            db_path,
            n_clusters=n_clusters,
            rank_k=rank_k,
            neighbors=neighbors,
            random_baselines=random_baselines,
        ),
        run_geometry_variant(
            "unnormalized_raw_gemma",
            rows,
            raw,
            db_path,
            n_clusters=n_clusters,
            rank_k=rank_k,
            neighbors=neighbors,
            random_baselines=random_baselines,
        ),
        run_geometry_variant(
            "unnormalized_raw_gemma_exact_dedup",
            dedup_rows,
            raw_dedup,
            db_path,
            n_clusters=min(n_clusters, max(2, len(dedup_rows) // 30)),
            rank_k=rank_k,
            neighbors=neighbors,
            random_baselines=random_baselines,
        ),
    ]
    by_name = {variant["name"]: variant for variant in variants}
    duplicate_stats = duplicate_summary(rows)
    return {
        "schema": "ogcf_unnormalized_bridge_eval/v1",
        "description": "Compares normalized DB vectors, raw unnormalized Gemma vectors, and exact-deduped raw vectors for OGCF bridge detection.",
        "db_path": str(db_path),
        "ids_path": str(ids_path),
        "raw_embeddings_path": str(raw_embeddings_path),
        "sampled_id_count": len(memory_ids),
        "usable_row_count": len(rows),
        "exact_dedup_row_count": len(dedup_rows),
        "exact_dedup_removed_count": len(rows) - len(dedup_rows),
        "duplicate_summary": duplicate_stats,
        "config": {
            "n_clusters": n_clusters,
            "rank_k": rank_k,
            "neighbors": neighbors,
            "random_baselines": random_baselines,
        },
        "variants": variants,
        "interpretation": {
            "raw_has_norm_variance": by_name["unnormalized_raw_gemma"]["embedding_norm_stats"]["std"] > 1e-3,
            "db_vectors_are_normalized": by_name["normalized_db_vectors"]["embedding_norm_stats"]["std"] <= 1e-3,
            "raw_max_z": by_name["unnormalized_raw_gemma"]["max_interaction_z"],
            "normalized_max_z": by_name["normalized_db_vectors"]["max_interaction_z"],
            "dedup_removed_duplicate_memories": len(rows) - len(dedup_rows),
            "raw_bridge_cluster_count": by_name["unnormalized_raw_gemma"]["bridge_cluster_count"],
            "dedup_bridge_cluster_count": by_name["unnormalized_raw_gemma_exact_dedup"]["bridge_cluster_count"],
        },
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Unnormalized Bridge Evaluation",
        "",
        f"DB: `{report['db_path']}`",
        f"Usable rows: `{report['usable_row_count']}`",
        f"Exact-dedup rows: `{report['exact_dedup_row_count']}`",
        f"Exact duplicates removed: `{report['exact_dedup_removed_count']}`",
        "",
        "## Interpretation",
        "",
        "```json",
        json.dumps(report["interpretation"], indent=2),
        "```",
        "",
        "## Variant Summary",
        "",
        "| variant | rows | norm std | loops | max z | max IE | bridge clusters |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in report["variants"]:
        lines.append(
            "| `{name}` | {rows} | {norm_std:.4f} | {loops} | {max_z:.4f} | {max_ie:.4f} | {bridges} |".format(
                name=variant["name"],
                rows=variant["row_count"],
                norm_std=variant["embedding_norm_stats"]["std"],
                loops=variant["loop_count"],
                max_z=variant["max_interaction_z"],
                max_ie=variant["max_interaction_excess"],
                bridges=variant["bridge_cluster_count"],
            )
        )
    lines.extend(["", "## Duplicate Pressure", "", "```json", json.dumps(report["duplicate_summary"], indent=2), "```"])
    lines.extend(["", "## Top Bridge Clusters", ""])
    for variant in report["variants"]:
        lines.extend([f"### {variant['name']}", ""])
        if not variant["top_bridge_clusters"]:
            lines.append("No bridge clusters detected.")
            lines.append("")
            continue
        lines.extend(["| cluster | size | unique texts | unique domains | top text |", "| ---: | ---: | ---: | ---: | --- |"])
        for cluster in variant["top_bridge_clusters"][:5]:
            top_text = cluster["top_texts"][0]["text"] if cluster.get("top_texts") else ""
            lines.append(
                f"| {cluster['cluster_id']} | {cluster['size']} | {cluster['unique_texts']} | {cluster['unique_domains']} | {clean_cell(top_text)} |"
            )
        lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare normalized and unnormalized OGCF bridge detection.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ids", default=str(DEFAULT_IDS))
    parser.add_argument("--raw-embeddings", default=str(DEFAULT_RAW))
    parser.add_argument("--n-clusters", type=int, default=60)
    parser.add_argument("--rank-k", type=int, default=8)
    parser.add_argument("--neighbors", type=int, default=5)
    parser.add_argument("--random-baselines", type=int, default=20)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(
        Path(args.db),
        Path(args.ids),
        Path(args.raw_embeddings),
        n_clusters=max(2, int(args.n_clusters)),
        rank_k=max(1, int(args.rank_k)),
        neighbors=max(1, int(args.neighbors)),
        random_baselines=max(1, int(args.random_baselines)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "usable_row_count": report["usable_row_count"],
                "exact_dedup_removed_count": report["exact_dedup_removed_count"],
                "interpretation": report["interpretation"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
