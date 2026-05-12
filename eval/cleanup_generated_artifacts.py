from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def remove_file(path: Path, removed: list[str]) -> None:
    if path.exists() and path.is_file():
        path.unlink()
        removed.append(str(path.relative_to(ROOT)))


def remove_dir(path: Path, removed: list[str]) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        removed.append(str(path.relative_to(ROOT)))


def main() -> None:
    removed: list[str] = []
    logs = ROOT / "logs"
    if logs.exists():
        for path in logs.glob("long_memory_*"):
            if path.name == ".gitkeep":
                continue
            if path.is_file():
                remove_file(path, removed)
        for name in ("embedding_cache.sqlite", "memory_events.jsonl"):
            remove_file(logs / name, removed)

    for path in ROOT.rglob("__pycache__"):
        if ".git" not in path.parts:
            remove_dir(path, removed)
    for path in ROOT.rglob("*.pyc"):
        if ".git" not in path.parts:
            remove_file(path, removed)

    payload = {
        "ok": True,
        "removed_count": len(removed),
        "removed": removed,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        raise SystemExit(1)
