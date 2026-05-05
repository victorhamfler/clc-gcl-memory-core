from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _validate_database(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"database does not exist: {path}")
    conn = sqlite3.connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"database integrity check failed: {integrity}")
        memories = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        domains = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        dimensions = [
            int(row[0])
            for row in conn.execute("SELECT DISTINCT dim FROM vectors ORDER BY dim").fetchall()
        ]
    finally:
        conn.close()
    return {"memories": memories, "domains": domains, "vector_dimensions": dimensions}


def promote_database(db_path: Path, config_path: Path, make_backup: bool = True) -> dict[str, object]:
    stats = _validate_database(db_path)
    replacement = f"database_path: {_display_path(db_path)}"
    lines = config_path.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("database_path:"):
            new_lines.append(replacement)
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.insert(0, replacement)

    backup_path = None
    if make_backup:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.bak_{suffix}")
        shutil.copy2(config_path, backup_path)
    config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "active_database": _display_path(db_path),
        "config": str(config_path),
        "backup": str(backup_path) if backup_path else None,
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote an experiment database into the active config")
    parser.add_argument("db_path", nargs="?", default="memory_experiment_180_best.db")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    result = promote_database(db_path, config_path, make_backup=not args.no_backup)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
