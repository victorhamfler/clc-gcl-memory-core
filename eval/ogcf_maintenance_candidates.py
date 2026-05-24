from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer  # noqa: E402


DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_report.md"
STALE_MARKERS = (
    "old",
    "previous",
    "legacy",
    "used to",
    "once",
    "before",
    "was",
    "did",
    "retired",
    "deprecated",
    "superseded",
    "no longer",
)
CONFLICT_MARKERS = (
    "not",
    "no",
    "never",
    "without",
    "false",
    "wrong",
    "drops",
    "drop",
    "excludes",
    "rejects",
    "avoids",
    "stopped",
    "removed",
    "deprecated",
    "outdated",
)
UPDATE_MARKERS = (
    "correction",
    "current",
    "latest",
    "changed",
    "replace",
    "instead",
    "anymore",
    "no longer",
    "previous",
    "old",
    "legacy",
)


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return {part for part in cleaned.split() if part}


def jaccard(a: str, b: str) -> float:
    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)


def parse_embedding(value: Any) -> list[float]:
    raw = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value or "")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [float(x) for x in loaded]


def has_stale_marker(text: str) -> bool:
    lowered = normalize_text(text)
    return any(marker in lowered for marker in STALE_MARKERS)


def marker_hits(text: str, markers: tuple[str, ...]) -> set[str]:
    lowered = normalize_text(text)
    return {marker for marker in markers if marker in lowered}


def possible_conflict_or_update(left: str, right: str) -> bool:
    """Flag near-duplicate pairs that may encode a correction, negation, or temporal update."""
    left_conflict = marker_hits(left, CONFLICT_MARKERS)
    right_conflict = marker_hits(right, CONFLICT_MARKERS)
    left_update = marker_hits(left, UPDATE_MARKERS)
    right_update = marker_hits(right, UPDATE_MARKERS)
    if left_conflict != right_conflict:
        return True
    if left_update != right_update:
        return True
    return False


def quality_score(row: dict[str, Any]) -> tuple[float, str, str]:
    score = float(row.get("confidence") or 0.0) * float(row.get("importance") or 0.0)
    return score, str(row.get("created_at") or ""), str(row.get("id") or "")


def choose_keeper(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(rows, key=quality_score)


def connected_components(edges: dict[str, set[str]]) -> list[set[str]]:
    seen: set[str] = set()
    components: list[set[str]] = []
    for node in sorted(edges):
        if node in seen:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.add(current)
            stack.extend(sorted(edges.get(current, set()) - seen))
        if len(component) > 1:
            components.append(component)
    return components


def load_rows(db_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT m.id, m.text, m.domain_id, m.namespace, m.importance, m.confidence,
               m.created_at, m.updated_at, m.deprecated, v.embedding
        FROM memories m
        JOIN vectors v ON v.memory_id = m.id
        WHERE COALESCE(m.deprecated, 0) = 0
        ORDER BY m.created_at ASC, m.id ASC
    """
    if limit:
        sql += " LIMIT ?"
        raw_rows = conn.execute(sql, (int(limit),)).fetchall()
    else:
        raw_rows = conn.execute(sql).fetchall()
    conn.close()
    rows = []
    for row in raw_rows:
        item = dict(row)
        item["embedding"] = parse_embedding(row["embedding"])
        item["normalized_text"] = normalize_text(row["text"])
        rows.append(item)
    return [row for row in rows if row["embedding"]]


def exact_duplicate_candidates(rows: list[dict[str, Any]], max_examples: int = 6) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["normalized_text"]].append(row)
    candidates = []
    for text_key, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(group) < 2:
            continue
        keeper = choose_keeper(group)
        deprecated = [row for row in group if row["id"] != keeper["id"]]
        candidates.append(
            {
                "id": f"exact_duplicate:{keeper['id']}",
                "action": "exact_duplicate_group",
                "recommendation": "review_or_deprecate_duplicates",
                "keeper_memory_id": keeper["id"],
                "candidate_memory_ids": [row["id"] for row in deprecated],
                "group_size": len(group),
                "domain_count": len({row.get("domain_id") for row in group}),
                "support": len(group),
                "confidence": 1.0,
                "sample_text": text_key[:300],
                "examples": [
                    {
                        "memory_id": row["id"],
                        "domain_id": row.get("domain_id"),
                        "confidence": row.get("confidence"),
                        "importance": row.get("importance"),
                        "created_at": row.get("created_at"),
                    }
                    for row in group[:max_examples]
                ],
            }
        )
    return candidates


def semantic_duplicate_candidates(
    rows: list[dict[str, Any]],
    *,
    similarity_threshold: float,
    jaccard_min: float,
    max_pairs: int,
) -> list[dict[str, Any]]:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_domain[str(row.get("domain_id") or "")].append(row)
    candidates = []
    for domain_id, group in by_domain.items():
        if len(group) < 2:
            continue
        edges: dict[str, set[str]] = {row["id"]: set() for row in group}
        pair_examples = []
        conflict_pairs = []
        pairs_checked = 0
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                pairs_checked += 1
                if pairs_checked > max_pairs:
                    break
                if left["normalized_text"] == right["normalized_text"]:
                    continue
                sim = cosine(left["embedding"], right["embedding"])
                jac = jaccard(left["text"], right["text"])
                if sim >= similarity_threshold and jac >= jaccard_min:
                    edges[left["id"]].add(right["id"])
                    edges[right["id"]].add(left["id"])
                    has_conflict = possible_conflict_or_update(left["text"], right["text"])
                    if len(pair_examples) < 8:
                        pair_examples.append(
                            {
                                "left": left["id"],
                                "right": right["id"],
                                "cosine": round(sim, 6),
                                "jaccard": round(jac, 6),
                                "possible_conflict_or_update": has_conflict,
                            }
                        )
                    if has_conflict and len(conflict_pairs) < 8:
                        conflict_pairs.append(
                            {
                                "left": left["id"],
                                "right": right["id"],
                                "left_text": left["text"][:240],
                                "right_text": right["text"][:240],
                            }
                        )
            if pairs_checked > max_pairs:
                break
        row_by_id = {row["id"]: row for row in group}
        for component in connected_components(edges):
            component_rows = [row_by_id[mid] for mid in sorted(component)]
            keeper = choose_keeper(component_rows)
            component_ids = {row["id"] for row in component_rows}
            component_conflicts = [
                pair
                for pair in conflict_pairs
                if pair["left"] in component_ids and pair["right"] in component_ids
            ]
            has_component_conflict = bool(component_conflicts)
            sample_texts = [
                {
                    "memory_id": row["id"],
                    "role": "keeper" if row["id"] == keeper["id"] else "duplicate_candidate",
                    "text": row["text"][:240],
                }
                for row in component_rows[:6]
            ]
            candidates.append(
                {
                    "id": f"semantic_duplicate:{keeper['id']}",
                    "action": "semantic_conflict_or_update_group" if has_component_conflict else "semantic_duplicate_group",
                    "recommendation": "review_conflict_or_temporal_update_before_merge"
                    if has_component_conflict
                    else "review_or_merge_paraphrases",
                    "keeper_memory_id": keeper["id"],
                    "candidate_memory_ids": [row["id"] for row in component_rows if row["id"] != keeper["id"]],
                    "group_size": len(component_rows),
                    "domain_id": domain_id,
                    "support": len(component_rows),
                    "confidence": 0.74 if has_component_conflict else 0.82,
                    "thresholds": {"cosine": similarity_threshold, "jaccard": jaccard_min},
                    "sample_text": keeper["normalized_text"][:300],
                    "pair_examples": pair_examples[:6],
                    "conflict_examples": component_conflicts[:4],
                    "examples": sample_texts,
                }
            )
    return candidates


def stale_version_candidates(rows: list[dict[str, Any]], *, jaccard_min: float) -> list[dict[str, Any]]:
    candidates = []
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_domain[str(row.get("domain_id") or "")].append(row)
    for domain_id, group in by_domain.items():
        stale_rows = [row for row in group if has_stale_marker(row["text"])]
        current_rows = [row for row in group if not has_stale_marker(row["text"])]
        for stale in stale_rows:
            matches = []
            for current in current_rows:
                jac = jaccard(stale["text"], current["text"])
                sim = cosine(stale["embedding"], current["embedding"])
                if jac >= jaccard_min or sim >= 0.88:
                    matches.append((current, sim, jac))
            if not matches:
                continue
            current, sim, jac = max(matches, key=lambda item: (quality_score(item[0]), item[1], item[2]))
            candidates.append(
                {
                    "id": f"stale_version:{stale['id']}:{current['id']}",
                    "action": "stale_version_candidate",
                    "recommendation": "review_or_deprecate_stale",
                    "keeper_memory_id": current["id"],
                    "candidate_memory_ids": [stale["id"]],
                    "group_size": 2,
                    "domain_id": domain_id,
                    "support": 2,
                    "confidence": 0.72,
                    "similarity": {"cosine": round(sim, 6), "jaccard": round(jac, 6)},
                    "sample_text": stale["normalized_text"][:300],
                    "examples": [
                        {"memory_id": stale["id"], "role": "stale_candidate", "text": stale["text"][:240]},
                        {"memory_id": current["id"], "role": "current_candidate", "text": current["text"][:240]},
                    ],
                }
            )
    return candidates


def bridge_cluster_candidates(
    rows: list[dict[str, Any]],
    db_path: Path,
    *,
    n_clusters: int,
    rank_k: int,
    neighbors: int,
    random_baselines: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if len(rows) < max(3, n_clusters):
        return [], {"skipped": True, "reason": f"not enough rows for {n_clusters} clusters", "row_count": len(rows)}
    memory_ids = [row["id"] for row in rows]
    embeddings = np.array([row["embedding"] for row in rows], dtype=np.float32)
    engine = OGCFGeometryEngine(
        n_clusters=n_clusters,
        rank_k=rank_k,
        neighbors=neighbors,
        random_baselines=random_baselines,
    )
    reviewer = OGCFMemoryReviewer(engine)
    report = reviewer.review(embeddings, memory_ids, db_path)
    candidates = []
    for bridge in report.get("bridge_clusters") or []:
        candidates.append(
            {
                "id": f"bridge_cluster:{bridge.get('cluster_id')}",
                "action": "bridge_cluster_review",
                "recommendation": "review_split_or_canonicalize_cross_domain_cluster",
                "cluster_id": bridge.get("cluster_id"),
                "group_size": bridge.get("size"),
                "domain_count": bridge.get("unique_domains"),
                "support": bridge.get("size"),
                "confidence": min(0.95, max(0.35, float(bridge.get("unique_domains") or 0) / max(1.0, float(bridge.get("size") or 1)))),
                "domain_counts": bridge.get("domain_counts"),
                "local_defect": bridge.get("local_defect"),
            }
        )
    return candidates, {
        "skipped": False,
        "loop_count": report.get("loop_count"),
        "max_interaction_z": report.get("max_interaction_z"),
        "bridge_overload_score": report.get("bridge_overload_score"),
        "embedding_norm_stats": report.get("embedding_norm_stats"),
    }


def build_report(
    db_path: Path,
    *,
    limit: int | None = None,
    n_clusters: int = 30,
    rank_k: int = 8,
    neighbors: int = 5,
    random_baselines: int = 10,
    semantic_threshold: float = 0.90,
    jaccard_min: float = 0.35,
    stale_jaccard_min: float = 0.40,
    max_semantic_pairs_per_domain: int = 20000,
    skip_geometry: bool = False,
) -> dict[str, Any]:
    rows = load_rows(db_path, limit=limit)
    exact = exact_duplicate_candidates(rows)
    semantic = semantic_duplicate_candidates(
        rows,
        similarity_threshold=semantic_threshold,
        jaccard_min=jaccard_min,
        max_pairs=max_semantic_pairs_per_domain,
    )
    stale = stale_version_candidates(rows, jaccard_min=stale_jaccard_min)
    if skip_geometry:
        bridge, geometry_summary = [], {"skipped": True, "reason": "skip_geometry enabled", "row_count": len(rows)}
    else:
        bridge, geometry_summary = bridge_cluster_candidates(
            rows,
            db_path,
            n_clusters=n_clusters,
            rank_k=rank_k,
            neighbors=neighbors,
            random_baselines=random_baselines,
        )

    candidates = exact + semantic + stale + bridge
    counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        counts[str(candidate.get("action"))] += 1
    return {
        "schema": "ogcf_maintenance_candidates/v1",
        "description": "Dry-run OGCF maintenance candidates. This report never mutates the database.",
        "mutates_db": False,
        "db_path": str(db_path),
        "row_count": len(rows),
        "config": {
            "limit": limit,
            "n_clusters": n_clusters,
            "rank_k": rank_k,
            "neighbors": neighbors,
            "random_baselines": random_baselines,
            "semantic_threshold": semantic_threshold,
            "jaccard_min": jaccard_min,
            "stale_jaccard_min": stale_jaccard_min,
            "max_semantic_pairs_per_domain": max_semantic_pairs_per_domain,
            "skip_geometry": skip_geometry,
        },
        "candidate_count": len(candidates),
        "candidate_counts": dict(sorted(counts.items())),
        "geometry_summary": geometry_summary,
        "candidates": candidates,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Candidates",
        "",
        "Dry-run only. This report does not mutate the memory database.",
        "",
        f"DB: `{report['db_path']}`",
        f"Rows analyzed: `{report['row_count']}`",
        f"Candidate count: **{report['candidate_count']}**",
        "",
        "## Candidate Counts",
        "",
        "```json",
        json.dumps(report["candidate_counts"], indent=2),
        "```",
        "",
        "## Geometry Summary",
        "",
        "```json",
        json.dumps(report["geometry_summary"], indent=2),
        "```",
        "",
        "## Candidates",
        "",
        "| action | recommendation | support | confidence | keeper | candidates | detail |",
        "| --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    if not report["candidates"]:
        lines.append("| none | no candidates | 0 | 0 |  | 0 |  |")
    for candidate in report["candidates"]:
        lines.append(
            "| `{action}` | `{rec}` | {support} | {conf:.2f} | `{keeper}` | {count} | {detail} |".format(
                action=candidate.get("action"),
                rec=candidate.get("recommendation"),
                support=int(candidate.get("support") or 0),
                conf=float(candidate.get("confidence") or 0.0),
                keeper=clean_cell(candidate.get("keeper_memory_id") or candidate.get("cluster_id") or ""),
                count=len(candidate.get("candidate_memory_ids") or []),
                detail=clean_cell(candidate.get("sample_text") or candidate.get("domain_id") or candidate.get("id")),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dry-run OGCF maintenance candidates from a memory DB.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--n-clusters", type=int, default=30)
    parser.add_argument("--rank-k", type=int, default=8)
    parser.add_argument("--neighbors", type=int, default=5)
    parser.add_argument("--random-baselines", type=int, default=10)
    parser.add_argument("--semantic-threshold", type=float, default=0.90)
    parser.add_argument("--jaccard-min", type=float, default=0.35)
    parser.add_argument("--stale-jaccard-min", type=float, default=0.40)
    parser.add_argument("--max-semantic-pairs-per-domain", type=int, default=20000)
    parser.add_argument("--skip-geometry", action="store_true")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(
        Path(args.db),
        limit=args.limit,
        n_clusters=max(2, int(args.n_clusters)),
        rank_k=max(1, int(args.rank_k)),
        neighbors=max(1, int(args.neighbors)),
        random_baselines=max(1, int(args.random_baselines)),
        semantic_threshold=max(0.0, min(1.0, float(args.semantic_threshold))),
        jaccard_min=max(0.0, min(1.0, float(args.jaccard_min))),
        stale_jaccard_min=max(0.0, min(1.0, float(args.stale_jaccard_min))),
        max_semantic_pairs_per_domain=max(1, int(args.max_semantic_pairs_per_domain)),
        skip_geometry=bool(args.skip_geometry),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "mutates_db": report["mutates_db"],
                "row_count": report["row_count"],
                "candidate_count": report["candidate_count"],
                "candidate_counts": report["candidate_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
