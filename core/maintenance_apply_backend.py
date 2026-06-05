from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


APPLY_BACKEND_RESULT_SCHEMA = "memory_maintenance_apply_backend_result/v1"
AUDIT_EVENT_SCHEMA = "memory_maintenance_apply_audit_event/v1"


def _string(value: Any) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


class MaintenanceApplyStore(Protocol):
    """Small memory-store adapter needed by maintenance apply backends."""

    def fetch_memory_rows(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        ...

    def mark_memories_deprecated(self, memory_ids: list[str], *, updated_at: str) -> None:
        ...

    def write_apply_audit_event(self, event: dict[str, Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def close(self) -> None:
        ...


class SQLiteMaintenanceApplyStore:
    """SQLite adapter for the memory maintenance apply backend.

    This adapter is intentionally tiny so the real memory program can later
    provide the same contract without coupling the backend to its full DB class.
    """

    def __init__(self, db_path: Path | str):
        self.conn = _connect(db_path)

    def fetch_memory_rows(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        return _fetch_memory_rows(self.conn, memory_ids)

    def mark_memories_deprecated(self, memory_ids: list[str], *, updated_at: str) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        self.conn.execute(
            f"UPDATE memories SET deprecated=1, updated_at=? WHERE id IN ({placeholders})",
            [updated_at, *memory_ids],
        )

    def write_apply_audit_event(self, event: dict[str, Any]) -> None:
        _write_audit_event(self.conn, event)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class MemoryDBMaintenanceApplyStore:
    """Adapter for the memory program's DB object.

    The wrapped object is expected to expose a SQLite `conn` attribute and a
    `close()` method, which matches `storage.db.MemoryDB`. The adapter does not
    own schema creation; callers should initialize the memory DB first.
    """

    def __init__(self, memory_db: Any, *, close_wrapped_db: bool = False):
        self.memory_db = memory_db
        self.conn = memory_db.conn
        self.close_wrapped_db = bool(close_wrapped_db)

    def fetch_memory_rows(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        return _fetch_memory_rows(self.conn, memory_ids)

    def mark_memories_deprecated(self, memory_ids: list[str], *, updated_at: str) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        self.conn.execute(
            f"UPDATE memories SET deprecated=1, updated_at=? WHERE id IN ({placeholders})",
            [updated_at, *memory_ids],
        )

    def write_apply_audit_event(self, event: dict[str, Any]) -> None:
        _write_audit_event(self.conn, event)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        if self.close_wrapped_db:
            self.memory_db.close()


def ensure_apply_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_maintenance_apply_audit (
            id TEXT PRIMARY KEY,
            schema TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            operation_kind TEXT NOT NULL,
            operator_id TEXT,
            dry_run INTEGER NOT NULL,
            mutation_enabled INTEGER NOT NULL,
            applied INTEGER NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def _fetch_memory_rows(conn: sqlite3.Connection, memory_ids: list[str]) -> list[dict[str, Any]]:
    if not memory_ids:
        return []
    placeholders = ",".join("?" for _ in memory_ids)
    rows = conn.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", memory_ids).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    return [by_id[memory_id] for memory_id in memory_ids if memory_id in by_id]


def _write_audit_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    ensure_apply_audit_table(conn)
    conn.execute(
        """
        INSERT INTO memory_maintenance_apply_audit
            (id, schema, candidate_id, operation_kind, operator_id, dry_run, mutation_enabled, applied, event_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["audit_event_id"],
            event["schema"],
            event["candidate_id"],
            event["operation_kind"],
            event.get("operator_id"),
            1 if event.get("dry_run") else 0,
            1 if event.get("mutation_enabled") else 0,
            1 if event.get("applied") else 0,
            json.dumps(event, sort_keys=True),
            event["created_at"],
        ),
    )


def _operation_blockers(
    operation: dict[str, Any],
    *,
    operator_confirmed: bool,
    mutation_enabled: bool,
    dry_run: bool,
) -> list[str]:
    blockers = []
    if operation.get("operation_kind") != "duplicate_deprecation":
        blockers.append("unsupported_operation_kind")
    if not _string(operation.get("keeper_memory_id")):
        blockers.append("missing_keeper_memory_id")
    if not operation.get("deprecate_memory_ids"):
        blockers.append("missing_deprecate_memory_ids")
    if not operator_confirmed:
        blockers.append("operator_confirmation_required")
    if dry_run:
        blockers.append("dry_run_enabled")
    if not mutation_enabled:
        blockers.append("mutation_backend_disabled")
    return blockers


def apply_duplicate_deprecation_operation(
    store: MaintenanceApplyStore,
    operation: dict[str, Any],
    *,
    operator_id: str,
    operator_confirmed: bool = False,
    mutation_enabled: bool = False,
    dry_run: bool = True,
    write_audit: bool = False,
) -> dict[str, Any]:
    """Apply or simulate one duplicate-deprecation operation.

    The production-safe default is dry-run and mutation-disabled. A real update
    requires both operator confirmation and mutation_enabled=True.
    """

    candidate_id = _string(operation.get("candidate_id"))
    operation_kind = _string(operation.get("operation_kind"))
    keeper_id = _string(operation.get("keeper_memory_id"))
    deprecate_ids = [_string(item) for item in operation.get("deprecate_memory_ids") or [] if _string(item)]
    target_ids = [keeper_id, *deprecate_ids] if keeper_id else deprecate_ids
    blockers = _operation_blockers(
        operation,
        operator_confirmed=operator_confirmed,
        mutation_enabled=mutation_enabled,
        dry_run=dry_run,
    )
    audit_event_id = f"maintenance_apply:{candidate_id or 'unknown'}:{int(datetime.now(timezone.utc).timestamp() * 1000000)}"
    before_rows = store.fetch_memory_rows(target_ids)
    missing_ids = [memory_id for memory_id in target_ids if memory_id not in {str(row.get("id")) for row in before_rows}]
    if missing_ids:
        blockers.append("target_memory_ids_missing")
    applied = not blockers
    if applied:
        store.mark_memories_deprecated(deprecate_ids, updated_at=_utc_now())
    after_rows = store.fetch_memory_rows(target_ids)
    event = {
        "schema": AUDIT_EVENT_SCHEMA,
        "audit_event_id": audit_event_id,
        "candidate_id": candidate_id,
        "operation_kind": operation_kind,
        "operator_id": _string(operator_id),
        "operator_confirmed": bool(operator_confirmed),
        "dry_run": bool(dry_run),
        "mutation_enabled": bool(mutation_enabled),
        "applied": bool(applied),
        "blocked_reasons": blockers,
        "keeper_memory_id": keeper_id,
        "deprecate_memory_ids": deprecate_ids,
        "before_memory_rows": before_rows,
        "after_memory_rows": after_rows,
        "rollback": {
            "required": bool(applied),
            "strategy": "restore_deprecated_flags_from_before_memory_rows",
            "candidate_id": candidate_id,
            "audit_event_id": audit_event_id,
        },
        "created_at": _utc_now(),
        "mutates_db": bool(applied),
    }
    if write_audit:
        store.write_apply_audit_event(event)
    store.commit()
    return {
        "schema": APPLY_BACKEND_RESULT_SCHEMA,
        "ok": True,
        "candidate_id": candidate_id,
        "operation_kind": operation_kind,
        "blocked": bool(blockers),
        "blocked_reasons": blockers,
        "applied": bool(not blockers),
        "audit_event": event,
        "report_only": bool(dry_run or not mutation_enabled),
        "mutates_db": bool(not blockers),
        "mutates_runtime": False,
        "mutates_config": False,
    }


def apply_memory_maintenance_plan(
    store: MaintenanceApplyStore,
    apply_plan: dict[str, Any],
    *,
    operator_id: str,
    operator_confirmed: bool = False,
    mutation_enabled: bool = False,
    dry_run: bool = True,
    write_audit: bool = False,
) -> dict[str, Any]:
    results = [
        apply_duplicate_deprecation_operation(
            store,
            operation,
            operator_id=operator_id,
            operator_confirmed=operator_confirmed,
            mutation_enabled=mutation_enabled,
            dry_run=dry_run,
            write_audit=write_audit,
        )
        for operation in apply_plan.get("planned_operations") or []
        if isinstance(operation, dict)
    ]
    applied_count = sum(1 for item in results if item.get("applied"))
    return {
        "schema": "memory_maintenance_apply_backend_batch_result/v1",
        "source_apply_plan_schema": apply_plan.get("schema"),
        "operation_count": len(results),
        "applied_count": applied_count,
        "blocked_count": sum(1 for item in results if item.get("blocked")),
        "results": results,
        "dry_run": bool(dry_run),
        "mutation_enabled": bool(mutation_enabled),
        "operator_confirmed": bool(operator_confirmed),
        "report_only": bool(dry_run or not mutation_enabled),
        "mutates_db": bool(applied_count),
        "mutates_runtime": False,
        "mutates_config": False,
    }


def apply_memory_maintenance_plan_to_sqlite(
    db_path: Path | str,
    apply_plan: dict[str, Any],
    *,
    operator_id: str,
    operator_confirmed: bool = False,
    mutation_enabled: bool = False,
    dry_run: bool = True,
    write_audit: bool = False,
) -> dict[str, Any]:
    store = SQLiteMaintenanceApplyStore(db_path)
    try:
        return apply_memory_maintenance_plan(
            store,
            apply_plan,
            operator_id=operator_id,
            operator_confirmed=operator_confirmed,
            mutation_enabled=mutation_enabled,
            dry_run=dry_run,
            write_audit=write_audit,
        )
    finally:
        store.close()
