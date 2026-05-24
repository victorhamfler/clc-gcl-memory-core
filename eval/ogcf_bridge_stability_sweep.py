from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OGCF_CACHE = REPO_ROOT / "experiments" / "ogcf_next_cache"
DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
DEFAULT_IDS = OGCF_CACHE / "sampled_2000_ids.json"
DEFAULT_RAW = OGCF_CACHE / "gemma_raw_embeddings_2000.npy"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_bridge_stability_sweep_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_bridge_stability_sweep_report.md"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ogcf_unnormalized_bridge_eval import (  # noqa: E402
    clean_cell,
    duplicate_summary,
    exact_dedup_indices,
    load_db_rows,
    run_geometry_variant,
)


def bridge_cluster_metrics(variant: dict[str, Any]) -> dict[str, Any]:
    bridges = variant.get("top_bridge_clusters") or []
    duplicate_dominated = 0
    diverse = 0
    signatures = []
    for bridge in bridges:
        size = int(bridge.get("size") or 0)
        unique_texts = int(bridge.get("unique_texts") or 0)
        unique_domains = int(bridge.get("unique_domains") or 0)
        if size >= 10 and unique_texts <= 2:
            duplicate_dominated += 1
        if unique_texts >= 5 and unique_domains >= 5:
            diverse += 1
        top_texts = bridge.get("top_texts") or []
        if top_texts:
            signatures.append(str(top_texts[0].get("text") or "")[:120])
    return {
        "duplicate_dominated_top_bridge_count": duplicate_dominated,
        "diverse_top_bridge_count": diverse,
        "top_bridge_signatures": signatures[:5],
    }


def summarize_group(name: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "name": name,
            "run_count": 0,
            "interaction_trigger_rate": 0.0,
            "median_max_z": 0.0,
            "max_z_range": [0.0, 0.0],
            "median_bridge_clusters": 0.0,
            "median_diverse_top_bridges": 0.0,
            "median_duplicate_dominated_top_bridges": 0.0,
        }
    max_z = np.array([float(item["max_interaction_z"]) for item in results], dtype=float)
    bridge_counts = np.array([int(item["bridge_cluster_count"]) for item in results], dtype=float)
    diverse = np.array([int(item["bridge_metrics"]["diverse_top_bridge_count"]) for item in results], dtype=float)
    dup_dom = np.array(
        [int(item["bridge_metrics"]["duplicate_dominated_top_bridge_count"]) for item in results],
        dtype=float,
    )
    return {
        "name": name,
        "run_count": len(results),
        "interaction_trigger_rate": round(float(np.mean(max_z >= 2.0)), 6),
        "median_max_z": round(float(np.median(max_z)), 6),
        "max_z_range": [round(float(max_z.min()), 6), round(float(max_z.max()), 6)],
        "median_bridge_clusters": round(float(np.median(bridge_counts)), 6),
        "median_diverse_top_bridges": round(float(np.median(diverse)), 6),
        "median_duplicate_dominated_top_bridges": round(float(np.median(dup_dom)), 6),
    }


def load_inputs(
    db_path: Path,
    ids_path: Path,
    raw_embeddings_path: Path,
) -> tuple[list[dict[str, Any]], np.ndarray, list[dict[str, Any]], np.ndarray, dict[str, Any]]:
    memory_ids = json.loads(ids_path.read_text(encoding="utf-8"))
    if not isinstance(memory_ids, list):
        raise ValueError(f"Expected sampled ids list in {ids_path}")
    raw_embeddings = np.load(raw_embeddings_path)
    if raw_embeddings.shape[0] != len(memory_ids):
        raise ValueError(f"Raw embedding count {raw_embeddings.shape[0]} does not match id count {len(memory_ids)}")
    row_by_id = load_db_rows(db_path, [str(mid) for mid in memory_ids])
    rows: list[dict[str, Any]] = []
    raw_kept = []
    for index, memory_id in enumerate(memory_ids):
        row = row_by_id.get(str(memory_id))
        if not row or not row.get("db_embedding"):
            continue
        rows.append(row)
        raw_kept.append(raw_embeddings[index])
    raw = np.array(raw_kept, dtype=np.float32)
    keep_indices = exact_dedup_indices(rows)
    dedup_rows = [rows[index] for index in keep_indices]
    raw_dedup = raw[keep_indices]
    metadata = {
        "sampled_id_count": len(memory_ids),
        "usable_row_count": len(rows),
        "exact_dedup_row_count": len(dedup_rows),
        "exact_dedup_removed_count": len(rows) - len(dedup_rows),
        "duplicate_summary": duplicate_summary(rows),
    }
    return rows, raw, dedup_rows, raw_dedup, metadata


def config_grid() -> list[dict[str, Any]]:
    return [
        {"group": "raw_full", "n_clusters": 40, "rank_k": 8, "neighbors": 5},
        {"group": "raw_full", "n_clusters": 60, "rank_k": 8, "neighbors": 5},
        {"group": "raw_full", "n_clusters": 80, "rank_k": 8, "neighbors": 5},
        {"group": "raw_full", "n_clusters": 60, "rank_k": 6, "neighbors": 5},
        {"group": "raw_full", "n_clusters": 60, "rank_k": 12, "neighbors": 5},
        {"group": "raw_full", "n_clusters": 60, "rank_k": 8, "neighbors": 4},
        {"group": "raw_full", "n_clusters": 60, "rank_k": 8, "neighbors": 6},
        {"group": "raw_exact_dedup", "n_clusters": 4, "rank_k": 6, "neighbors": 4},
        {"group": "raw_exact_dedup", "n_clusters": 6, "rank_k": 6, "neighbors": 4},
        {"group": "raw_exact_dedup", "n_clusters": 8, "rank_k": 6, "neighbors": 4},
        {"group": "raw_exact_dedup", "n_clusters": 10, "rank_k": 6, "neighbors": 5},
        {"group": "raw_exact_dedup", "n_clusters": 12, "rank_k": 8, "neighbors": 5},
    ]


def run_sweep(
    db_path: Path,
    ids_path: Path,
    raw_embeddings_path: Path,
    *,
    random_baselines: int,
) -> dict[str, Any]:
    rows, raw, dedup_rows, raw_dedup, metadata = load_inputs(db_path, ids_path, raw_embeddings_path)
    results = []
    for index, config in enumerate(config_grid(), start=1):
        group = config["group"]
        active_rows = rows if group == "raw_full" else dedup_rows
        active_embeddings = raw if group == "raw_full" else raw_dedup
        variant = run_geometry_variant(
            f"{group}_c{config['n_clusters']}_r{config['rank_k']}_n{config['neighbors']}",
            active_rows,
            active_embeddings,
            db_path,
            n_clusters=int(config["n_clusters"]),
            rank_k=int(config["rank_k"]),
            neighbors=int(config["neighbors"]),
            random_baselines=random_baselines,
        )
        variant["sweep_index"] = index
        variant["group"] = group
        variant["bridge_metrics"] = bridge_cluster_metrics(variant)
        results.append(variant)
    by_group = {
        group: [item for item in results if item["group"] == group]
        for group in sorted({item["group"] for item in results})
    }
    group_summaries = [summarize_group(group, items) for group, items in by_group.items()]
    raw_summary = next((item for item in group_summaries if item["name"] == "raw_full"), {})
    dedup_summary = next((item for item in group_summaries if item["name"] == "raw_exact_dedup"), {})
    interpretation = {
        "raw_interaction_signal_is_stable": float(raw_summary.get("interaction_trigger_rate") or 0.0) >= 0.7,
        "raw_signal_is_duplicate_dominated": float(raw_summary.get("median_duplicate_dominated_top_bridges") or 0.0) >= 3.0,
        "dedup_interpretable_bridge_signal_exists": float(dedup_summary.get("median_diverse_top_bridges") or 0.0) >= 1.0,
        "recommended_next_gate": "raw-embedding bridge trigger followed by exact/semantic dedup and diverse-bridge review",
    }
    return {
        "schema": "ogcf_bridge_stability_sweep/v1",
        "description": "Sweeps OGCF geometry settings for raw Gemma embeddings before and after exact deduplication.",
        "db_path": str(db_path),
        "ids_path": str(ids_path),
        "raw_embeddings_path": str(raw_embeddings_path),
        "random_baselines": random_baselines,
        **metadata,
        "group_summaries": group_summaries,
        "interpretation": interpretation,
        "runs": results,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Bridge Stability Sweep",
        "",
        f"DB: `{report['db_path']}`",
        f"Usable rows: `{report['usable_row_count']}`",
        f"Exact-dedup rows: `{report['exact_dedup_row_count']}`",
        f"Exact duplicates removed: `{report['exact_dedup_removed_count']}`",
        f"Random baselines per run: `{report['random_baselines']}`",
        "",
        "## Interpretation",
        "",
        "```json",
        json.dumps(report["interpretation"], indent=2),
        "```",
        "",
        "## Group Summary",
        "",
        "| group | runs | trigger rate | median max z | max z range | median bridge clusters | median diverse top bridges | median duplicate-dominated top bridges |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in report["group_summaries"]:
        lines.append(
            "| `{name}` | {runs} | {rate:.2f} | {median_z:.4f} | {zmin:.4f}-{zmax:.4f} | {bridges:.1f} | {diverse:.1f} | {dup:.1f} |".format(
                name=summary["name"],
                runs=summary["run_count"],
                rate=summary["interaction_trigger_rate"],
                median_z=summary["median_max_z"],
                zmin=summary["max_z_range"][0],
                zmax=summary["max_z_range"][1],
                bridges=summary["median_bridge_clusters"],
                diverse=summary["median_diverse_top_bridges"],
                dup=summary["median_duplicate_dominated_top_bridges"],
            )
        )
    lines.extend(
        [
            "",
            "## Run Details",
            "",
            "| run | rows | clusters | rank | neighbors | loops | max z | bridge clusters | diverse top bridges | duplicate-dominated top bridges | top bridge signature |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for run in report["runs"]:
        metrics = run["bridge_metrics"]
        signature = (metrics.get("top_bridge_signatures") or [""])[0]
        lines.append(
            "| `{name}` | {rows} | {clusters} | {rank} | {neighbors} | {loops} | {max_z:.4f} | {bridges} | {diverse} | {dup} | {signature} |".format(
                name=run["name"],
                rows=run["row_count"],
                clusters=run["n_clusters"],
                rank=run["rank_k"],
                neighbors=run["neighbors"],
                loops=run["loop_count"],
                max_z=run["max_interaction_z"],
                bridges=run["bridge_cluster_count"],
                diverse=metrics["diverse_top_bridge_count"],
                dup=metrics["duplicate_dominated_top_bridge_count"],
                signature=clean_cell(signature, 110),
            )
        )
    lines.extend(["", "## Duplicate Pressure", "", "```json", json.dumps(report["duplicate_summary"], indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep OGCF raw-embedding bridge stability across geometry configs.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ids", default=str(DEFAULT_IDS))
    parser.add_argument("--raw-embeddings", default=str(DEFAULT_RAW))
    parser.add_argument("--random-baselines", type=int, default=10)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = run_sweep(
        Path(args.db),
        Path(args.ids),
        Path(args.raw_embeddings),
        random_baselines=max(1, int(args.random_baselines)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "usable_row_count": report["usable_row_count"],
                "exact_dedup_row_count": report["exact_dedup_row_count"],
                "interpretation": report["interpretation"],
                "group_summaries": report["group_summaries"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
