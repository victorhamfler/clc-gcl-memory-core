from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
OUT_DB = REPO_ROOT / "experiments" / "ogcf_exact_unique_memory_test.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_duplicate_origin_and_dedup_effect_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_duplicate_origin_and_dedup_effect_report.md"
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_candidates import build_report as build_maintenance_report  # noqa: E402


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def quality(row: dict[str, Any]) -> tuple[float, str, str]:
    return (
        float(row.get("confidence") or 0.0) * float(row.get("importance") or 0.0),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def clean_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def namespace_family(namespace: str) -> str:
    parts = str(namespace or "global").split(":")
    if len(parts) >= 3 and parts[0] == "agent":
        return ":".join(parts[:3])
    if len(parts) >= 2:
        return ":".join(parts[:2])
    return parts[0] if parts else "global"


def load_rows(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT m.*, v.embedding, v.dim
            FROM memories m
            JOIN vectors v ON v.memory_id = m.id
            WHERE COALESCE(m.deprecated, 0) = 0
            ORDER BY m.created_at ASC, m.id ASC
            """
        )
    ]
    conn.close()
    for row in rows:
        row["normalized_text"] = normalize_text(row.get("text"))
        row["namespace_family"] = namespace_family(str(row.get("namespace") or ""))
    return rows


def group_exact(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["normalized_text"]].append(row)
    return groups


def create_exact_unique_db(source_db: Path, out_db: Path, groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if out_db.exists():
        out_db.unlink()
    conn = sqlite3.connect(str(source_db))
    target = sqlite3.connect(str(out_db))
    conn.backup(target)
    conn.close()
    target.row_factory = sqlite3.Row
    keepers = {max(group, key=quality)["id"] for group in groups.values()}
    removed_ids = [
        row["id"]
        for group in groups.values()
        for row in group
        if row["id"] not in keepers
    ]
    with target:
        if removed_ids:
            for start in range(0, len(removed_ids), 500):
                chunk = removed_ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                target.execute(f"DELETE FROM vectors WHERE memory_id IN ({placeholders})", chunk)
                target.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", chunk)
    remaining = target.execute(
        "SELECT COUNT(*) FROM memories m JOIN vectors v ON v.memory_id = m.id WHERE COALESCE(m.deprecated,0)=0"
    ).fetchone()[0]
    target.close()
    return {
        "out_db": str(out_db),
        "keeper_count": len(keepers),
        "removed_exact_duplicate_count": len(removed_ids),
        "remaining_active_vector_rows": int(remaining),
    }


def duplicate_origin_summary(rows: list[dict[str, Any]], groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    namespace_counts = Counter()
    duplicate_namespace_counts = Counter()
    for row in rows:
        namespace_counts[row["namespace_family"]] += 1
    for group in duplicate_groups:
        for row in group:
            duplicate_namespace_counts[row["namespace_family"]] += 1
    top_groups = []
    for text_key, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:20]:
        if len(group) < 2:
            continue
        top_groups.append(
            {
                "text": text_key[:260],
                "count": len(group),
                "domain_count": len({row.get("domain_id") for row in group}),
                "namespace_family_count": len({row.get("namespace_family") for row in group}),
                "top_namespace_families": dict(Counter(row["namespace_family"] for row in group).most_common(5)),
                "first_created_at": min(str(row.get("created_at") or "") for row in group),
                "last_created_at": max(str(row.get("created_at") or "") for row in group),
            }
        )
    return {
        "active_row_count": len(rows),
        "exact_distinct_text_count": len(groups),
        "exact_duplicate_group_count": len(duplicate_groups),
        "exact_duplicate_extra_row_count": sum(len(group) - 1 for group in duplicate_groups),
        "duplicate_extra_ratio": round(
            sum(len(group) - 1 for group in duplicate_groups) / max(1, len(rows)),
            6,
        ),
        "namespace_family_counts": dict(namespace_counts.most_common(15)),
        "duplicate_namespace_family_counts": dict(duplicate_namespace_counts.most_common(15)),
        "top_exact_duplicate_groups": top_groups,
    }


def dedup_value_summary(groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    cross_domain = sum(1 for group in duplicate_groups if len({row.get("domain_id") for row in group}) > 1)
    cross_namespace = sum(1 for group in duplicate_groups if len({row.get("namespace") for row in group}) > 1)
    metadata_conflicts = 0
    for group in duplicate_groups:
        qualities = {quality(row)[0] for row in group}
        if len(qualities) > 1:
            metadata_conflicts += 1
    return {
        "exact_dedup_text_information_loss": "none_for_text_content",
        "exact_dedup_metadata_loss_if_deleted": [
            "support_count",
            "domain_spread",
            "namespace/source_provenance",
            "first_seen_last_seen_timestamps",
        ],
        "recommended_exact_dedup_behavior": "canonicalize_or_deprecate_redundant_rows_only_after preserving support/provenance metadata",
        "duplicate_groups_crossing_domains": cross_domain,
        "duplicate_groups_crossing_namespaces": cross_namespace,
        "duplicate_groups_with_quality_metadata_variation": metadata_conflicts,
    }


def compact_maintenance(report: dict[str, Any]) -> dict[str, Any]:
    examples = []
    for candidate in report.get("candidates", [])[:12]:
        examples.append(
            {
                "action": candidate.get("action"),
                "recommendation": candidate.get("recommendation"),
                "support": candidate.get("support"),
                "group_size": candidate.get("group_size"),
                "sample_text": candidate.get("sample_text"),
                "domain_id": candidate.get("domain_id"),
                "candidate_count": len(candidate.get("candidate_memory_ids") or []),
            }
        )
    return {
        "row_count": report.get("row_count"),
        "candidate_count": report.get("candidate_count"),
        "candidate_counts": report.get("candidate_counts"),
        "geometry_summary": report.get("geometry_summary"),
        "examples": examples,
    }


def build_report(
    db_path: Path,
    out_db: Path,
    *,
    n_clusters: int,
    random_baselines: int,
) -> dict[str, Any]:
    rows = load_rows(db_path)
    groups = group_exact(rows)
    origin = duplicate_origin_summary(rows, groups)
    value = dedup_value_summary(groups)
    shadow = create_exact_unique_db(db_path, out_db, groups)
    original_maintenance = build_maintenance_report(
        db_path,
        limit=None,
        n_clusters=n_clusters,
        random_baselines=random_baselines,
        max_semantic_pairs_per_domain=5000,
    )
    unique_maintenance = build_maintenance_report(
        out_db,
        limit=None,
        n_clusters=min(n_clusters, max(2, shadow["keeper_count"] // 4)),
        random_baselines=random_baselines,
        max_semantic_pairs_per_domain=5000,
    )
    return {
        "schema": "ogcf_duplicate_origin_and_dedup_effect/v1",
        "description": "Diagnoses duplicate origin, creates an exact-unique shadow DB, and compares dry-run maintenance behavior.",
        "mutates_source_db": False,
        "source_db": str(db_path),
        "exact_unique_shadow_db": shadow,
        "duplicate_origin": origin,
        "dedup_value_summary": value,
        "original_db_maintenance": compact_maintenance(original_maintenance),
        "exact_unique_db_maintenance": compact_maintenance(unique_maintenance),
        "selector_memory_implications": {
            "exact_dedup_effect": "reduces repeated retrieval pressure and bridge false positives without removing unique text facts if support/provenance is retained",
            "semantic_dedup_effect": "groups paraphrases for review/merge and can remove noise, but should not auto-delete because paraphrases may encode corrections, polarity, or temporal status",
            "ogcf_policy": "run OGCF bridge detection on raw embeddings, then apply exact/semantic dedup as a maintenance-review layer before selector actions",
        },
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    origin = report["duplicate_origin"]
    shadow = report["exact_unique_shadow_db"]
    lines = [
        "# OGCF Duplicate Origin And Dedup Effect",
        "",
        "This diagnostic is dry-run for the source DB. It creates a separate exact-unique shadow DB for testing.",
        "",
        f"Source DB: `{report['source_db']}`",
        f"Shadow DB: `{shadow['out_db']}`",
        "",
        "## Duplicate Origin",
        "",
        f"- Active rows: `{origin['active_row_count']}`",
        f"- Exact-distinct texts: `{origin['exact_distinct_text_count']}`",
        f"- Exact duplicate groups: `{origin['exact_duplicate_group_count']}`",
        f"- Extra duplicate rows: `{origin['exact_duplicate_extra_row_count']}`",
        f"- Duplicate extra ratio: `{origin['duplicate_extra_ratio']}`",
        "",
        "Top duplicate namespace families:",
        "",
        "```json",
        json.dumps(origin["duplicate_namespace_family_counts"], indent=2),
        "```",
        "",
        "## Top Exact Duplicate Groups",
        "",
        "| count | domains | namespace families | first | last | text |",
        "| ---: | ---: | ---: | --- | --- | --- |",
    ]
    for group in origin["top_exact_duplicate_groups"][:12]:
        lines.append(
            f"| {group['count']} | {group['domain_count']} | {group['namespace_family_count']} | {clean_cell(group['first_created_at'], 32)} | {clean_cell(group['last_created_at'], 32)} | {clean_cell(group['text'])} |"
        )
    lines.extend(
        [
            "",
            "## Dedup Value Assessment",
            "",
            "```json",
            json.dumps(report["dedup_value_summary"], indent=2),
            "```",
            "",
            "## Maintenance Comparison",
            "",
            "| DB | rows | candidates | counts | geometry |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for label, key in [("original", "original_db_maintenance"), ("exact_unique_shadow", "exact_unique_db_maintenance")]:
        item = report[key]
        lines.append(
            f"| `{label}` | {item['row_count']} | {item['candidate_count']} | `{json.dumps(item['candidate_counts'], sort_keys=True)}` | `{json.dumps(item['geometry_summary'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Selector And Memory Implications",
            "",
            "```json",
            json.dumps(report["selector_memory_implications"], indent=2),
            "```",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose OGCF duplicate origin and dedup effect.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out-db", default=str(OUT_DB))
    parser.add_argument("--n-clusters", type=int, default=30)
    parser.add_argument("--random-baselines", type=int, default=10)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(
        Path(args.db),
        Path(args.out_db),
        n_clusters=max(2, int(args.n_clusters)),
        random_baselines=max(1, int(args.random_baselines)),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "source_db": report["source_db"],
                "shadow_db": report["exact_unique_shadow_db"],
                "duplicate_origin": {
                    "active_row_count": report["duplicate_origin"]["active_row_count"],
                    "exact_distinct_text_count": report["duplicate_origin"]["exact_distinct_text_count"],
                    "exact_duplicate_extra_row_count": report["duplicate_origin"]["exact_duplicate_extra_row_count"],
                    "duplicate_extra_ratio": report["duplicate_origin"]["duplicate_extra_ratio"],
                },
                "maintenance_counts": {
                    "original": report["original_db_maintenance"]["candidate_counts"],
                    "exact_unique_shadow": report["exact_unique_db_maintenance"]["candidate_counts"],
                },
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
