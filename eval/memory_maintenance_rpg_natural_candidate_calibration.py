from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_calibration_report.md"
DEFAULT_DBS = [ROOT / "memory_experiment_clean.db", ROOT / "memory_gemma.db", ROOT / "memory.db"]
FIXTURE_ROOT = REPO_ROOT / "experiments" / "memory_maintenance_rpg_fixture_dbs"

import sys

sys.path.insert(0, str(ROOT))
from core.rpg_memory import RPGMemoryRecord, build_relational_substrate, island_ratio  # noqa: E402


STALE_MARKERS = (
    "old",
    "previous",
    "legacy",
    "used to",
    "before",
    "deprecated",
    "superseded",
    "no longer",
    "outdated",
    "stale",
)
BRIDGE_MARKERS = ("bridge", "connects", "cross-domain", "cross domain", "selector", "ogcf", "erg", "g-cl", "csd")


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def tokens(value: Any) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
    return {part for part in cleaned.split() if part}


def jaccard(left: str, right: str) -> float:
    a = tokens(left)
    b = tokens(right)
    return len(a & b) / max(len(a | b), 1)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    return float(np.dot(a, b) / max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-12))


def lexical_embedding(text: str, dim: int = 24) -> tuple[float, ...]:
    vector = [0.0] * dim
    for token in tokens(text):
        vector[sum(ord(ch) for ch in token) % dim] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return tuple(value / norm for value in vector) if norm > 1e-12 else tuple(vector)


def parse_embedding(value: Any) -> tuple[float, ...]:
    raw = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value or "")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(loaded, list):
        return ()
    try:
        return tuple(float(item) for item in loaded)
    except (TypeError, ValueError):
        return ()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def create_fixture_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                domain_id TEXT,
                namespace TEXT,
                importance REAL,
                confidence REAL,
                created_at TEXT,
                updated_at TEXT,
                deprecated INTEGER DEFAULT 0
            )
            """
        )
        rows = [
            (
                "fixture_dup_a",
                "Atlas project codename is blue nova and the status is ready for review.",
                "project_atlas",
            ),
            (
                "fixture_dup_b",
                "Atlas project codename is blue nova and the status is ready for review.",
                "project_atlas",
            ),
            (
                "fixture_near_a",
                "The pizza preference memory says the user likes thin crust with basil.",
                "food_profile",
            ),
            (
                "fixture_near_b",
                "The pizza preference memory says the user likes thin crust pizza with fresh basil.",
                "food_profile",
            ),
            (
                "fixture_stale_new",
                "Current radar route uses beta corridor after the route update.",
                "navigation",
            ),
            (
                "fixture_stale_old",
                "Old radar route used to use alpha corridor before the route update.",
                "navigation",
            ),
            (
                "fixture_bridge_a",
                "CSD selector bridge connects retrieval evidence with memory maintenance review.",
                "selector",
            ),
            (
                "fixture_bridge_b",
                "OGCF ERG bridge connects graph pressure with cross-domain memory review.",
                "maintenance",
            ),
            (
                "fixture_cross_a",
                "Travel preference says morning train plans should preserve station context.",
                "travel",
            ),
            (
                "fixture_cross_b",
                "Planner memory says station context is useful when scheduling morning train trips.",
                "planner",
            ),
        ]
        for index, (memory_id, text, domain) in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO memories (
                    id, text, domain_id, namespace, importance, confidence,
                    created_at, updated_at, deprecated
                )
                VALUES (?, ?, ?, 'fixture', 0.6, 0.8, ?, ?, 0)
                """,
                (memory_id, text, domain, f"2026-06-05T00:00:{index:02d}Z", f"2026-06-05T00:00:{index:02d}Z"),
            )
        conn.commit()
    finally:
        conn.close()


def load_records(db_path: Path, *, limit: int = 220) -> list[RPGMemoryRecord]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        select_columns = [
            "id",
            "text",
            "domain_id" if "domain_id" in columns else "'' AS domain_id",
            "namespace" if "namespace" in columns else "'memory_db' AS namespace",
            "importance" if "importance" in columns else "0.5 AS importance",
            "confidence" if "confidence" in columns else "0.5 AS confidence",
            "created_at" if "created_at" in columns else "'' AS created_at",
            "updated_at" if "updated_at" in columns else "'' AS updated_at",
            "deprecated" if "deprecated" in columns else "0 AS deprecated",
        ]
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_columns)}
            FROM memories
            WHERE COALESCE(deprecated, 0) = 0 AND COALESCE(text, '') != ''
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        vectors: dict[str, tuple[float, ...]] = {}
        if table_exists(conn, "vectors") and rows:
            ids = [str(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in ids)
            for row in conn.execute(f"SELECT memory_id, embedding FROM vectors WHERE memory_id IN ({placeholders})", ids):
                vectors[str(row["memory_id"])] = parse_embedding(row["embedding"])
        records = []
        for row in rows:
            text = str(row["text"] or "")
            memory_id = str(row["id"])
            confidence = float(row["confidence"] or 0.0)
            importance = float(row["importance"] or 0.0)
            records.append(
                RPGMemoryRecord(
                    memory_id=memory_id,
                    text=text,
                    domain=str(row["domain_id"] or row["namespace"] or ""),
                    source=str(row["namespace"] or "memory_db"),
                    timestamp=str(row["updated_at"] or row["created_at"] or ""),
                    authority=max(confidence, importance, confidence * importance),
                    status="deprecated" if int(row["deprecated"] or 0) else "active",
                    retrieval_count=importance,
                    embedding=vectors.get(memory_id) or lexical_embedding(text),
                )
            )
        return [record for record in records if record.embedding]
    finally:
        conn.close()


def has_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = normalize_text(text)
    return any(marker in lowered for marker in markers)


def candidate_class(left: RPGMemoryRecord, right: RPGMemoryRecord, *, cos: float, jac: float) -> str:
    same_text = normalize_text(left.text) == normalize_text(right.text)
    same_domain = left.domain == right.domain
    stale = has_marker(left.text, STALE_MARKERS) or has_marker(right.text, STALE_MARKERS)
    bridge = has_marker(left.text, BRIDGE_MARKERS) or has_marker(right.text, BRIDGE_MARKERS)
    if same_text:
        return "exact_duplicate"
    if stale and (cos >= 0.70 or jac >= 0.12):
        return "stale_or_update_like"
    if bridge and (not same_domain or cos >= 0.70 or jac >= 0.12):
        return "bridge_like"
    if same_domain and cos >= 0.86 and jac >= 0.20:
        return "near_duplicate_like"
    if not same_domain and cos >= 0.72 and jac >= 0.12:
        return "cross_domain_related"
    return ""


def pair_metrics(records: list[RPGMemoryRecord], *, max_pairs: int = 40) -> dict[str, Any]:
    substrate = build_relational_substrate(records)["A"]
    by_id = {record.memory_id: idx for idx, record in enumerate(records)}
    candidates = []
    class_counts: Counter[str] = Counter()
    for i, left in enumerate(records):
        for j in range(i + 1, len(records)):
            right = records[j]
            cos = cosine(left.embedding, right.embedding)
            jac = jaccard(left.text, right.text)
            klass = candidate_class(left, right, cos=cos, jac=jac)
            if not klass:
                continue
            class_counts[klass] += 1
            idxs = [by_id[left.memory_id], by_id[right.memory_id]]
            candidates.append(
                {
                    "schema": "memory_maintenance_rpg_natural_candidate_pair/v1",
                    "candidate_class": klass,
                    "left_id": left.memory_id,
                    "right_id": right.memory_id,
                    "same_domain": left.domain == right.domain,
                    "left_domain": left.domain,
                    "right_domain": right.domain,
                    "cosine": round(cos, 6),
                    "jaccard": round(jac, 6),
                    "rpg_target_relation": round(float(substrate[idxs[0], idxs[1]]), 6),
                    "rpg_target_island_ratio": round(island_ratio(substrate, idxs), 6),
                    "left_preview": left.text[:140],
                    "right_preview": right.text[:140],
                    "report_only": True,
                }
            )
    candidates.sort(
        key=lambda item: (
            item["candidate_class"] != "exact_duplicate",
            item["candidate_class"] != "near_duplicate_like",
            -float(item["rpg_target_relation"]),
            -float(item["rpg_target_island_ratio"]),
        )
    )
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        if len(by_class[item["candidate_class"]]) < max_pairs:
            by_class[item["candidate_class"]].append(item)
    kept = [item for group in by_class.values() for item in group]
    return {
        "candidate_pair_count": len(candidates),
        "candidate_class_counts": dict(sorted(class_counts.items())),
        "kept_pair_count": len(kept),
        "pairs": kept,
    }


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        grouped[str(pair.get("candidate_class") or "unknown")].append(pair)
    summaries = {}
    for klass, rows in sorted(grouped.items()):
        relations = [float(row.get("rpg_target_relation") or 0.0) for row in rows]
        islands = [float(row.get("rpg_target_island_ratio") or 0.0) for row in rows]
        summaries[klass] = {
            "count": len(rows),
            "relation_mean": round(sum(relations) / max(len(relations), 1), 6),
            "relation_max": round(max(relations), 6) if relations else 0.0,
            "island_mean": round(sum(islands) / max(len(islands), 1), 6),
            "island_max": round(max(islands), 6) if islands else 0.0,
        }
    return summaries


def build_report(db_paths: list[Path], *, limit: int = 220) -> dict[str, Any]:
    db_reports = []
    all_pairs = []
    for db_path in db_paths:
        if not db_path.exists():
            continue
        records = load_records(db_path, limit=limit)
        metrics = pair_metrics(records)
        all_pairs.extend([{**pair, "source_db": str(db_path)} for pair in metrics["pairs"]])
        db_reports.append(
            {
                "schema": "memory_maintenance_rpg_natural_candidate_db_report/v1",
                "db_path": str(db_path),
                "record_count": len(records),
                **metrics,
            }
        )
    summary = summarize_pairs(all_pairs)
    near_relation = float((summary.get("near_duplicate_like") or {}).get("relation_mean") or 0.0)
    stale_relation = float((summary.get("stale_or_update_like") or {}).get("relation_mean") or 0.0)
    bridge_relation = float((summary.get("bridge_like") or {}).get("relation_mean") or 0.0)
    return {
        "schema": "memory_maintenance_rpg_natural_candidate_calibration/v1",
        "description": "Report-only RPG metrics for naturally mined memory maintenance candidate pairs.",
        "db_count": len(db_reports),
        "limit_per_db": int(limit),
        "db_reports": db_reports,
        "candidate_class_summary": summary,
        "all_pair_count": len(all_pairs),
        "sample_pairs": all_pairs[:60],
        "checks": {
            "has_natural_pairs": len(all_pairs) > 0,
            "has_near_duplicate_like_pairs": (summary.get("near_duplicate_like") or {}).get("count", 0) > 0,
            "near_relation_nonzero": near_relation > 0.0,
            "risk_or_bridge_classes_observed": bool(stale_relation > 0.0 or bridge_relation > 0.0),
        },
        "ready_for_policy_use": False,
        "next_action": "compare_natural_rpg_candidates_with_human_or_hermes_review_labels",
        "report_only": True,
        "mutates_source_db": False,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    report["ok"] = all((report.get("checks") or {}).values())
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Natural Candidate Calibration",
        "",
        f"Passed: **{report['ok']}**",
        f"DBs: `{report['db_count']}`",
        f"Pairs: `{report['all_pair_count']}`",
        f"Ready for policy use: `{report['ready_for_policy_use']}`",
        "",
        "## Candidate Class Summary",
        "",
        "| class | count | relation mean | island mean |",
        "| --- | ---: | ---: | ---: |",
    ]
    for klass, summary in (report.get("candidate_class_summary") or {}).items():
        lines.append(
            f"| `{klass}` | {summary.get('count')} | {summary.get('relation_mean')} | {summary.get('island_mean')} |"
        )
    lines.extend(["", "## Sample Pairs", "", "| class | relation | island | db | left | right |", "| --- | ---: | ---: | --- | --- | --- |"])
    for pair in report.get("sample_pairs") or []:
        lines.append(
            f"| `{pair.get('candidate_class')}` | {pair.get('rpg_target_relation')} | "
            f"{pair.get('rpg_target_island_ratio')} | `{clean_cell(pair.get('source_db'), 50)}` | "
            f"{clean_cell(pair.get('left_preview'), 70)} | {clean_cell(pair.get('right_preview'), 70)} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_db_args(values: list[str] | None) -> list[Path]:
    if not values:
        existing = [path for path in DEFAULT_DBS if path.exists()]
        if existing:
            return existing
        fixture = FIXTURE_ROOT / "natural_candidate_fixture.db"
        create_fixture_db(fixture)
        return [fixture]
    paths = []
    for value in values:
        for part in str(value).split(";"):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate RPG metrics on naturally mined memory candidate pairs.")
    parser.add_argument("--db", action="append", help="Memory DB path. Repeat or separate with ';'.")
    parser.add_argument("--limit", type=int, default=220)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(parse_db_args(args.db), limit=max(2, int(args.limit)))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "db_count": report["db_count"],
                "all_pair_count": report["all_pair_count"],
                "class_summary": report["candidate_class_summary"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_source_db": False,
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
