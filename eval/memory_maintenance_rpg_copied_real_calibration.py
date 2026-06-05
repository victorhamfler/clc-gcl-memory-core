from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rehearsal_review_memory_bank import build_memory_bank  # noqa: E402
from eval.memory_maintenance_rpg_rehearsal_calibration import calibrate_bank  # noqa: E402


DEFAULT_DBS = [
    ROOT / "memory.db",
    ROOT / "memory_experiment_clean.db",
    ROOT / "memory_gemma.db",
]
WORK_ROOT = Path("E:/projcod2_artifacts_archive/current_rehearsals/rpg_copied_real_calibration")
if not Path("E:/").exists():
    WORK_ROOT = REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_copied_real_calibration_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def memory_columns(conn: sqlite3.Connection) -> list[str]:
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(memories)").fetchall()]


def active_seed_row(conn: sqlite3.Connection) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT * FROM memories
        WHERE COALESCE(deprecated, 0) = 0 AND COALESCE(text, '') != ''
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def clone_memory_row(conn: sqlite3.Connection, seed: dict[str, Any], *, memory_id: str, text: str, domain: str) -> None:
    columns = memory_columns(conn)
    row = {column: seed.get(column) for column in columns}
    row["id"] = memory_id
    row["text"] = text
    if "domain_id" in row:
        row["domain_id"] = domain
    if "namespace" in row and not row.get("namespace"):
        row["namespace"] = "global"
    if "deprecated" in row:
        row["deprecated"] = 0
    if "created_at" in row:
        row["created_at"] = "2026-06-05T00:00:00Z"
    if "updated_at" in row:
        row["updated_at"] = "2026-06-05T00:00:00Z"
    placeholders = ",".join("?" for _ in columns)
    quoted = ",".join(columns)
    conn.execute(f"INSERT OR REPLACE INTO memories ({quoted}) VALUES ({placeholders})", [row.get(column) for column in columns])


def clone_vector(conn: sqlite3.Connection, source_id: str, target_id: str) -> None:
    if not table_exists(conn, "vectors"):
        return
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM vectors WHERE memory_id=? LIMIT 1", (source_id,)).fetchone()
    if not row:
        return
    item = dict(row)
    item["memory_id"] = target_id
    columns = [str(col[1]) for col in conn.execute("PRAGMA table_info(vectors)").fetchall()]
    placeholders = ",".join("?" for _ in columns)
    quoted = ",".join(columns)
    conn.execute(f"INSERT OR REPLACE INTO vectors ({quoted}) VALUES ({placeholders})", [item.get(column) for column in columns])


def augment_copied_real_db(source_db: Path, target_db: Path, *, run_id: str) -> dict[str, Any]:
    if target_db.exists():
        target_db.unlink()
    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, target_db)
    conn = sqlite3.connect(str(target_db))
    conn.row_factory = sqlite3.Row
    try:
        seed = active_seed_row(conn)
        if not seed:
            raise ValueError(f"No active seed memory found in {source_db}")
        source_id = str(seed["id"])
        base_text = "Copied-real RPG calibration exact duplicate fact for safe rehearsal."
        safe_keep = f"rpg_safe_keep_{run_id}"
        safe_dup = f"rpg_safe_dup_{run_id}"
        stale_keep = f"rpg_stale_keep_{run_id}"
        stale_old = f"rpg_stale_old_{run_id}"
        clone_memory_row(conn, seed, memory_id=safe_keep, text=base_text, domain="rpg_calibration_safe")
        clone_memory_row(conn, seed, memory_id=safe_dup, text=base_text, domain="rpg_calibration_safe")
        clone_memory_row(
            conn,
            seed,
            memory_id=stale_keep,
            text="Current copied-real RPG calibration fact uses the beta route.",
            domain="rpg_calibration_current",
        )
        clone_memory_row(
            conn,
            seed,
            memory_id=stale_old,
            text="Old stale copied-real RPG calibration fact used the alpha route before the update.",
            domain="rpg_calibration_stale",
        )
        for target_id in (safe_keep, safe_dup, stale_keep, stale_old):
            clone_vector(conn, source_id, target_id)
        conn.commit()
        return {
            "source_db": str(source_db),
            "augmented_db": str(target_db),
            "seed_memory_id": source_id,
            "safe_keep": safe_keep,
            "safe_dup": safe_dup,
            "stale_keep": stale_keep,
            "stale_old": stale_old,
        }
    finally:
        conn.close()


def write_apply_plan(path: Path, ids: dict[str, Any]) -> None:
    plan = {
        "schema": "memory_maintenance_apply_plan/v1",
        "source_apply_decision_schema": "copied_real_rpg_calibration/v1",
        "source_apply_decision_ok": True,
        "operation_count": 2,
        "planned_operation_count": 2,
        "duplicate_deprecation_operation_count": 2,
        "blocked_operation_count": 0,
        "ready_to_execute_count": 0,
        "applied_count": 0,
        "planned_operations": [
            {
                "schema": "memory_maintenance_apply_operation/v1",
                "candidate_id": f"copied_real:{Path(ids['source_db']).stem}:safe_duplicate",
                "operation_kind": "duplicate_deprecation",
                "memory_review_kind": "duplicate_deprecation_review",
                "keeper_memory_id": ids["safe_keep"],
                "deprecate_memory_ids": [ids["safe_dup"]],
                "operator_confirmation_required": True,
                "operator_confirmed": False,
                "dry_run": True,
                "ready_to_execute": False,
                "applied": False,
                "mutates_db": False,
            },
            {
                "schema": "memory_maintenance_apply_operation/v1",
                "candidate_id": f"copied_real:{Path(ids['source_db']).stem}:stale_as_duplicate",
                "operation_kind": "duplicate_deprecation",
                "memory_review_kind": "duplicate_deprecation_review",
                "keeper_memory_id": ids["stale_keep"],
                "deprecate_memory_ids": [ids["stale_old"]],
                "operator_confirmation_required": True,
                "operator_confirmed": False,
                "dry_run": True,
                "ready_to_execute": False,
                "applied": False,
                "mutates_db": False,
            },
        ],
        "blocked_operations": [],
        "promotion_ready": False,
        "report_only": True,
        "mutates_db": False,
    }
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def run_rehearsal(augmented_db: Path, plan_path: Path, work_dir: Path, out_json: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "eval" / "memory_maintenance_copied_db_rehearsal.py"),
            "--source-db",
            str(augmented_db),
            "--apply-plan",
            str(plan_path),
            "--work-dir",
            str(work_dir),
            "--operator-id",
            "rpg_copied_real_calibration",
            "--out-json",
            str(out_json),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    report = json.loads(out_json.read_text(encoding="utf-8"))
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "report": report}


def build_report(db_paths: list[Path], *, work_root: Path) -> dict[str, Any]:
    work_root.mkdir(parents=True, exist_ok=True)
    run_paths: list[Path] = []
    run_results = []
    for index, db_path in enumerate(db_paths, start=1):
        if not db_path.exists():
            continue
        run_id = f"run{index}_{db_path.stem}"
        run_dir = work_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        augmented_db = run_dir / f"{db_path.stem}_augmented.db"
        ids = augment_copied_real_db(db_path, augmented_db, run_id=run_id)
        plan_path = run_dir / "apply_plan.json"
        rehearsal_json = run_dir / "rehearsal_results.json"
        write_apply_plan(plan_path, ids)
        rehearsal = run_rehearsal(augmented_db, plan_path, run_dir, rehearsal_json)
        run_paths.append(rehearsal_json)
        run_results.append(
            {
                "db_path": str(db_path),
                "run_dir": str(run_dir),
                "rehearsal_json": str(rehearsal_json),
                "returncode": rehearsal["returncode"],
                "rehearsal_ok": rehearsal["report"].get("ok"),
                "overall_decision": (rehearsal["report"].get("review_summary") or {}).get("overall_decision"),
                "rpg_available": (rehearsal["report"].get("rpg_rehearsal_annotations") or {}).get("available"),
            }
        )
    bank = build_memory_bank(run_paths, min_runs=min(2, max(1, len(run_paths))), min_safe=min(2, max(1, len(run_paths))))
    calibration = calibrate_bank(bank)
    safe_relation = float(calibration.get("safe_relation_mean") or 0.0)
    blocked_relation = float(calibration.get("blocked_relation_mean") or 0.0)
    return {
        "schema": "memory_maintenance_rpg_copied_real_calibration/v1",
        "description": "Report-only RPG calibration over augmented copied-real memory DB rehearsals.",
        "db_count": len(db_paths),
        "run_count": len(run_paths),
        "work_root": str(work_root),
        "runs": run_results,
        "memory_bank": bank,
        "calibration": calibration,
        "checks": {
            "at_least_two_runs": len(run_paths) >= 2,
            "rpg_annotations_available": all(item.get("rpg_available") is True for item in run_results),
            "safe_relation_exceeds_blocked": safe_relation > blocked_relation,
            "calibration_report_only": calibration.get("report_only") is True
            and calibration.get("ready_for_policy_use") is False,
        },
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
    calibration = report.get("calibration") or {}
    lines = [
        "# Memory Maintenance RPG Copied-Real Calibration",
        "",
        f"Passed: **{report['ok']}**",
        f"Runs: `{report['run_count']}`",
        f"Work root: `{report['work_root']}`",
        "",
        "## Calibration",
        "",
        f"Safe relation mean: `{calibration.get('safe_relation_mean')}`",
        f"Blocked relation mean: `{calibration.get('blocked_relation_mean')}`",
        f"Prediction accuracy probe: `{calibration.get('prediction_accuracy')}`",
        f"Ready for policy use: `{calibration.get('ready_for_policy_use')}`",
        "",
        "## Runs",
        "",
        "| db | rehearsal ok | rpg | decision |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.get("runs") or []:
        lines.append(
            f"| `{clean_cell(item.get('db_path'), 90)}` | `{item.get('rehearsal_ok')}` | "
            f"`{item.get('rpg_available')}` | `{item.get('overall_decision')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_db_args(values: list[str] | None) -> list[Path]:
    if not values:
        return [path for path in DEFAULT_DBS if path.exists()]
    paths = []
    for value in values:
        for part in str(value).split(";"):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RPG calibration over augmented copied-real rehearsal outputs.")
    parser.add_argument("--db", action="append", help="Memory DB path. Repeat or separate with ';'.")
    parser.add_argument("--work-root", default=str(WORK_ROOT))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(parse_db_args(args.db), work_root=Path(args.work_root))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "run_count": report["run_count"],
                "safe_relation_mean": (report.get("calibration") or {}).get("safe_relation_mean"),
                "blocked_relation_mean": (report.get("calibration") or {}).get("blocked_relation_mean"),
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
