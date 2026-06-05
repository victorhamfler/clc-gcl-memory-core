from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_apply_backend import apply_memory_maintenance_plan_to_sqlite  # noqa: E402
from core.maintenance_candidate_contract import build_manual_apply_decisions, build_manual_apply_plan  # noqa: E402
from core.rpg_memory import RPGMemoryRecord, build_relational_substrate, island_ratio, run_rpg_memory_probe  # noqa: E402
from eval.memory_maintenance_review_outcome_log_regression import (  # noqa: E402
    OUTCOMES_JSON,
    PLAN_JSON,
    build_outcome_fixture,
)
from storage.db import MemoryDB  # noqa: E402


E_REHEARSAL_ROOT = Path("E:/projcod2_artifacts_archive/current_rehearsals")
DEFAULT_WORK_DIR = E_REHEARSAL_ROOT if E_REHEARSAL_ROOT.drive and Path("E:/").exists() else REPO_ROOT / "experiments"
OUT_JSON_NAME = "memory_maintenance_copied_db_rehearsal_results.json"
OUT_MD_NAME = "memory_maintenance_copied_db_rehearsal_report.md"
SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def setup_fixture_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDB(path)
    db.init_schema(SCHEMA_PATH)
    rows = [
        ("dup_alpha_r1", "Alpha duplicate maintenance fixture stores the canonical duplicate fact."),
        ("dup_alpha_r2", "Alpha duplicate maintenance fixture stores the canonical duplicate fact."),
        ("stale_beta_r1", "Beta stale fixture row one should not be touched by duplicate backend."),
        ("stale_beta_r2", "Beta stale fixture row two should not be touched by duplicate backend."),
    ]
    for memory_id, text in rows:
        db.conn.execute(
            """
            INSERT INTO memories (
                id, text, domain_id, memory_type, namespace, importance, stability, confidence,
                csd_score, surprise, recall_score, curiosity, focus, clc_state,
                created_at, updated_at, deprecated
            )
            VALUES (?, ?, 'maintenance_rehearsal', 'fact', 'global', 0.5, 0.0, 0.8,
                0.0, 0.0, 0.0, 0.0, 0.0, 'stored',
                '2026-06-04T00:00:00Z', '2026-06-04T00:00:00Z', 0)
            """,
            (memory_id, text),
        )
    db.conn.commit()
    db.close()


def deprecated_map(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    try:
        return {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT id, deprecated FROM memories ORDER BY id").fetchall()
        }
    finally:
        conn.close()


def memory_ids(path: Path) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        return {str(row[0]) for row in conn.execute("SELECT id FROM memories").fetchall()}
    finally:
        conn.close()


def memory_rows_by_id(path: Path, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", ids).fetchall()
        return {str(row["id"]): dict(row) for row in rows}
    finally:
        conn.close()


def audit_count(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_maintenance_apply_audit'"
        ).fetchone()
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM memory_maintenance_apply_audit").fetchone()[0])
    finally:
        conn.close()


def build_fixture_plan(path: Path) -> dict[str, Any]:
    build_outcome_fixture()
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_JSON.read_text(encoding="utf-8"))
    decisions = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    apply_plan = build_manual_apply_plan(decisions, dry_run=True, operator_id="copied_db_rehearsal")
    path.write_text(json.dumps(apply_plan, indent=2), encoding="utf-8")
    return apply_plan


def load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def token_set(value: Any) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
    return {token for token in cleaned.split() if token}


def lexical_embedding(text: str, dim: int = 24) -> tuple[float, ...]:
    vector = [0.0] * dim
    for token in token_set(text):
        bucket = sum(ord(ch) for ch in token) % dim
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def parse_vector_blob(value: Any) -> tuple[float, ...]:
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


def load_rpg_records(db_path: Path, target_ids: set[str], *, context_limit: int = 200) -> list[RPGMemoryRecord]:
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
        # RPG island ratios need boundary context, so include the broader DB
        # instead of only the operation targets.
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_columns)}
            FROM memories
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (int(context_limit),),
        ).fetchall()
        vectors: dict[str, tuple[float, ...]] = {}
        if table_exists(conn, "vectors"):
            row_ids = [str(row["id"]) for row in rows]
            if not row_ids:
                return []
            placeholders = ",".join("?" for _ in row_ids)
            vector_rows = conn.execute(
                f"SELECT memory_id, embedding FROM vectors WHERE memory_id IN ({placeholders})",
                row_ids,
            ).fetchall()
            vectors = {str(row["memory_id"]): parse_vector_blob(row["embedding"]) for row in vector_rows}
        records = []
        for row in rows:
            memory_id = str(row["id"])
            text = str(row["text"] or "")
            confidence = float(row["confidence"] or 0.0)
            importance = float(row["importance"] or 0.0)
            authority = max(confidence, importance, confidence * importance)
            embedding = vectors.get(memory_id) or lexical_embedding(text)
            records.append(
                RPGMemoryRecord(
                    memory_id=memory_id,
                    text=text,
                    domain=str(row["domain_id"] or row["namespace"] or ""),
                    source=str(row["namespace"] or "memory_db"),
                    timestamp=str(row["updated_at"] or row["created_at"] or ""),
                    authority=authority,
                    status="deprecated" if int(row["deprecated"] or 0) else "active",
                    retrieval_count=float(row["importance"] or 0.0),
                    embedding=embedding,
                )
            )
        return records
    finally:
        conn.close()


def build_rpg_rehearsal_annotations(quality: dict[str, Any], db_path: Path) -> dict[str, Any]:
    operations = [item for item in quality.get("operations") or [] if isinstance(item, dict)]
    target_ids = {
        str(memory_id)
        for operation in operations
        for memory_id in (operation.get("target_ids") or [])
        if str(memory_id)
    }
    records = load_rpg_records(db_path, target_ids)
    if len(records) < 2 or len({len(record.embedding) for record in records}) != 1:
        return {
            "schema": "memory_maintenance_rpg_rehearsal_annotations/v1",
            "available": False,
            "reason": "insufficient_same_dimension_records",
            "operation_annotations": [],
            "report_only": True,
            "mutates_db": False,
            "mutates_runtime": False,
            "mutates_config": False,
        }
    probe = run_rpg_memory_probe(records, rank_k=min(4, max(1, len(records) - 1)))
    substrate = build_relational_substrate(records)["A"]
    record_index = {record.memory_id: idx for idx, record in enumerate(records)}
    pair_reports = probe.get("constraint_pair_reports") or []
    pair_by_name = {str(item.get("pair_name")): item for item in pair_reports if isinstance(item, dict)}
    operation_annotations = []
    for operation in operations:
        operation_targets = {str(memory_id) for memory_id in operation.get("target_ids") or [] if str(memory_id)}
        target_indices = [record_index[memory_id] for memory_id in sorted(operation_targets) if memory_id in record_index]
        target_relations = [
            float(substrate[i, j])
            for pos, i in enumerate(target_indices)
            for j in target_indices[pos + 1 :]
        ]
        best_pair = None
        best_overlap = -1
        for pair in pair_reports:
            sector_ids = {str(memory_id) for memory_id in pair.get("sector_memory_ids") or []}
            overlap = len(operation_targets & sector_ids)
            if overlap > best_overlap:
                best_pair = pair
                best_overlap = overlap
        operation_annotations.append(
            {
                "schema": "memory_maintenance_rpg_operation_annotation/v1",
                "candidate_id": operation.get("candidate_id"),
                "operation_kind": operation.get("operation_kind"),
                "target_ids": sorted(operation_targets),
                "best_constraint_pair": (best_pair or {}).get("pair_name"),
                "target_sector_overlap": int(max(best_overlap, 0)),
                "target_count": len(operation_targets),
                "target_island_ratio": round(island_ratio(substrate, target_indices), 6) if len(target_indices) >= 2 else 0.0,
                "target_mean_relation": round(float(sum(target_relations) / len(target_relations)), 6)
                if target_relations
                else 0.0,
                "island_ratio": (best_pair or {}).get("island_ratio", 0.0),
                "omega_norm": (best_pair or {}).get("omega_norm", 0.0),
                "duplicate_contradiction_sector_overlap": len(
                    operation_targets
                    & set(pair_by_name.get("duplicate_vs_contradiction", {}).get("sector_memory_ids") or [])
                ),
                "active_deprecated_sector_overlap": len(
                    operation_targets & set(pair_by_name.get("active_vs_deprecated", {}).get("sector_memory_ids") or [])
                ),
                "risk_flags": operation.get("risk_flags") or [],
                "exact_duplicate_target": operation.get("exact_duplicate_target"),
                "report_only": True,
                "mutates_db": False,
            }
        )
    return {
        "schema": "memory_maintenance_rpg_rehearsal_annotations/v1",
        "available": True,
        "record_count": len(records),
        "probe_schema": probe.get("schema"),
        "max_island_ratio": probe.get("max_island_ratio"),
        "max_omega_norm": probe.get("max_omega_norm"),
        "operation_annotations": operation_annotations,
        "probe": probe,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def row_risk_flags(row: dict[str, Any]) -> list[str]:
    text = normalize_text(row.get("text"))
    domain = normalize_text(row.get("domain_id"))
    memory_type = normalize_text(row.get("memory_type"))
    flags = []
    for marker in ("stale", "bridge", "semantic", "conflict", "update"):
        if marker in text or marker in domain or marker in memory_type:
            flags.append(f"{marker}_marker")
    return flags


def target_quality(apply_plan: dict[str, Any], db_path: Path) -> dict[str, Any]:
    available_ids = memory_ids(db_path)
    operations = [item for item in apply_plan.get("planned_operations") or [] if isinstance(item, dict)]
    rows = []
    for operation in operations:
        keeper_id = str(operation.get("keeper_memory_id") or "")
        deprecate_ids = [str(item) for item in operation.get("deprecate_memory_ids") or [] if str(item)]
        target_ids = [
            keeper_id,
            *deprecate_ids,
        ]
        target_ids = [item for item in target_ids if item]
        missing = [item for item in target_ids if item not in available_ids]
        target_rows = memory_rows_by_id(db_path, target_ids)
        keeper = target_rows.get(keeper_id) or {}
        deprecate_rows = [target_rows.get(memory_id) or {} for memory_id in deprecate_ids]
        keeper_text = normalize_text(keeper.get("text"))
        duplicate_text_matches = [
            normalize_text(row.get("text")) == keeper_text and bool(keeper_text)
            for row in deprecate_rows
        ]
        namespaces = {str(row.get("namespace") or "") for row in [keeper, *deprecate_rows] if row}
        domains = {str(row.get("domain_id") or "") for row in [keeper, *deprecate_rows] if row}
        risk_flags = []
        for row in deprecate_rows:
            risk_flags.extend(row_risk_flags(row))
        if operation.get("operation_kind") == "duplicate_deprecation" and duplicate_text_matches:
            if not all(duplicate_text_matches):
                risk_flags.append("duplicate_text_mismatch")
        if len(namespaces) > 1:
            risk_flags.append("cross_namespace_target")
        if len(domains) > 1:
            risk_flags.append("cross_domain_target")
        exact_duplicate_target = (
            operation.get("operation_kind") == "duplicate_deprecation"
            and bool(deprecate_rows)
            and all(duplicate_text_matches)
            and not missing
        )
        rows.append(
            {
                "candidate_id": operation.get("candidate_id"),
                "operation_kind": operation.get("operation_kind"),
                "keeper_memory_id": keeper_id,
                "deprecate_memory_ids": deprecate_ids,
                "target_ids": target_ids,
                "missing_ids": missing,
                "all_targets_present": not missing,
                "exact_duplicate_target": exact_duplicate_target,
                "risk_flags": sorted(set(risk_flags)),
                "target_text_preview": {
                    memory_id: normalize_text((target_rows.get(memory_id) or {}).get("text"))[:160]
                    for memory_id in target_ids
                    if memory_id in target_rows
                },
            }
        )
    suspicious = [item for item in rows if item["risk_flags"] or not item["exact_duplicate_target"]]
    return {
        "operation_count": len(operations),
        "targeted_operation_count": sum(1 for item in rows if item["target_ids"]),
        "all_targets_present": all(item["all_targets_present"] for item in rows) if rows else False,
        "exact_duplicate_target_count": sum(1 for item in rows if item["exact_duplicate_target"]),
        "suspicious_operation_count": len(suspicious),
        "candidate_target_quality_ok": bool(rows)
        and all(item["all_targets_present"] and item["exact_duplicate_target"] and not item["risk_flags"] for item in rows),
        "operations": rows,
    }


def operation_review_decision(operation: dict[str, Any]) -> dict[str, Any]:
    flags = set(operation.get("risk_flags") or [])
    reasons = []
    if operation.get("operation_kind") != "duplicate_deprecation":
        decision = "blocked_unsupported_operation"
        reasons.append("unsupported_operation_kind")
    elif operation.get("missing_ids"):
        decision = "blocked_missing_targets"
        reasons.append("missing_target_ids")
    elif any(flag.startswith("stale_") for flag in flags):
        decision = "blocked_stale_risk"
        reasons.append("stale_target_marker")
    elif any(flag.startswith("semantic_") for flag in flags):
        decision = "blocked_semantic_risk"
        reasons.append("semantic_target_marker")
    elif any(flag.startswith("bridge_") for flag in flags):
        decision = "blocked_bridge_risk"
        reasons.append("bridge_target_marker")
    elif "duplicate_text_mismatch" in flags:
        decision = "blocked_duplicate_text_mismatch"
        reasons.append("duplicate_text_mismatch")
    elif "cross_namespace_target" in flags:
        decision = "blocked_cross_namespace_target"
        reasons.append("cross_namespace_target")
    elif "cross_domain_target" in flags:
        decision = "needs_operator_review_cross_domain"
        reasons.append("cross_domain_target")
    elif operation.get("exact_duplicate_target") is True:
        decision = "safe_to_review"
        reasons.append("exact_duplicate_target")
    else:
        decision = "needs_operator_review"
        reasons.append("target_quality_uncertain")
    return {
        "schema": "memory_maintenance_rehearsal_operation_review/v1",
        "candidate_id": operation.get("candidate_id"),
        "operation_kind": operation.get("operation_kind"),
        "decision": decision,
        "reasons": reasons,
        "risk_flags": sorted(flags),
        "target_ids": operation.get("target_ids") or [],
        "missing_ids": operation.get("missing_ids") or [],
        "operator_next_action": "operator_may_review_duplicate_deprecation"
        if decision == "safe_to_review"
        else "operator_must_resolve_blockers_before_apply",
        "mutation_allowed": False,
    }


def build_review_summary(quality: dict[str, Any]) -> dict[str, Any]:
    reviews = [operation_review_decision(item) for item in quality.get("operations") or []]
    counts: dict[str, int] = {}
    for review in reviews:
        decision = str(review.get("decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    blocked_count = sum(count for decision, count in counts.items() if decision.startswith("blocked_"))
    safe_count = counts.get("safe_to_review", 0)
    return {
        "schema": "memory_maintenance_rehearsal_review_summary/v1",
        "operation_review_count": len(reviews),
        "decision_counts": dict(sorted(counts.items())),
        "safe_to_review_count": safe_count,
        "blocked_count": blocked_count,
        "needs_operator_review_count": sum(
            count for decision, count in counts.items() if decision.startswith("needs_operator_review")
        ),
        "overall_decision": "safe_to_review"
        if reviews and safe_count == len(reviews)
        else "blocked_or_needs_review",
        "reviews": reviews,
        "mutation_allowed": False,
        "report_only": True,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Memory Maintenance Copied DB Rehearsal",
        "",
        f"Passed: **{report['ok']}**",
        f"Source DB: `{report['source_db']}`",
        f"Rehearsal DB: `{report['rehearsal_db']}`",
        f"Apply plan: `{report['apply_plan_path']}`",
        "",
        "## Safety",
        "",
        "| check | value |",
        "| --- | --- |",
        f"| rows unchanged | `{report['checks']['rows_unchanged']}` |",
        f"| applied count zero | `{report['checks']['applied_count_zero']}` |",
        f"| audit written | `{report['checks']['audit_written']}` |",
        f"| all targets present | `{report['checks']['all_targets_present']}` |",
        f"| candidate target quality ok | `{report['checks']['candidate_target_quality_ok']}` |",
        f"| review summary safe | `{report['checks']['review_summary_safe']}` |",
        f"| review overall decision | `{report['review_summary']['overall_decision']}` |",
        "",
        "## Target Quality",
        "",
        "```json",
        json.dumps(report["target_quality"], indent=2),
        "```",
        "",
        "## RPG Rehearsal Annotations",
        "",
        "```json",
        json.dumps(report["rpg_rehearsal_annotations"], indent=2),
        "```",
        "",
        "## Review Summary",
        "",
        "```json",
        json.dumps(report["review_summary"], indent=2),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe maintenance apply rehearsal on a copied SQLite DB.")
    parser.add_argument("--source-db", default="", help="Optional source DB to copy. If omitted, a fixture DB is generated.")
    parser.add_argument("--apply-plan", default="", help="Optional apply plan. If omitted, a fixture apply plan is generated.")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--operator-id", default="copied_db_rehearsal")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    source_db = Path(args.source_db) if args.source_db else work_dir / "memory_maintenance_rehearsal_source_fixture.db"
    rehearsal_db = work_dir / "memory_maintenance_rehearsal_copy.db"
    apply_plan_path = Path(args.apply_plan) if args.apply_plan else work_dir / "memory_maintenance_rehearsal_apply_plan.json"
    out_json = Path(args.out_json) if args.out_json else work_dir / OUT_JSON_NAME
    out_md = Path(args.out_md) if args.out_md else work_dir / OUT_MD_NAME

    generated_fixture = not bool(args.source_db)
    if generated_fixture:
        setup_fixture_db(source_db)
    if not source_db.exists():
        raise FileNotFoundError(f"Source DB does not exist: {source_db}")
    shutil.copy2(source_db, rehearsal_db)
    apply_plan = build_fixture_plan(apply_plan_path) if not args.apply_plan else load_plan(apply_plan_path)

    before = deprecated_map(rehearsal_db)
    quality = target_quality(apply_plan, rehearsal_db)
    rpg_annotations = build_rpg_rehearsal_annotations(quality, rehearsal_db)
    review_summary = build_review_summary(quality)
    result = apply_memory_maintenance_plan_to_sqlite(
        rehearsal_db,
        apply_plan,
        operator_id=args.operator_id,
        operator_confirmed=True,
        mutation_enabled=False,
        dry_run=False,
        write_audit=True,
    )
    after = deprecated_map(rehearsal_db)
    checks = {
        "rows_unchanged": before == after,
        "applied_count_zero": result.get("applied_count") == 0,
        "blocked_count_positive": int(result.get("blocked_count") or 0) > 0,
        "audit_written": audit_count(rehearsal_db) >= 1,
        "all_targets_present": quality.get("all_targets_present") is True,
        "candidate_target_quality_ok": quality.get("candidate_target_quality_ok") is True,
        "rpg_annotations_report_only": rpg_annotations.get("report_only") is True
        and rpg_annotations.get("mutates_db") is False,
        "review_summary_safe": review_summary.get("overall_decision") == "safe_to_review",
        "copy_is_not_source": source_db.resolve() != rehearsal_db.resolve(),
    }
    report = {
        "schema": "memory_maintenance_copied_db_rehearsal/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "source_db": str(source_db),
        "rehearsal_db": str(rehearsal_db),
        "apply_plan_path": str(apply_plan_path),
        "generated_fixture": generated_fixture,
        "target_quality": quality,
        "rpg_rehearsal_annotations": rpg_annotations,
        "review_summary": review_summary,
        "backend_result": result,
        "before_deprecated_map": before,
        "after_deprecated_map": after,
        "report_only": True,
        "mutates_source_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(json.dumps({"ok": report["ok"], "json": str(out_json), "markdown": str(out_md), "work_dir": str(work_dir)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
