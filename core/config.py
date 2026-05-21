from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(root: Path) -> dict[str, Any]:
    path = root / "config.yaml"
    if not path.exists():
        return {}
    return _parse_simple_yaml(path.read_text(encoding="utf-8"))


def resolve_project_path(root: Path, value: str | None, default_name: str) -> Path:
    raw = str(value or default_name).strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    return root / path


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by this project config.

    This keeps the core dependency-free while still letting the config remain
    human-editable. It supports nested indented maps with scalar values.
    """

    out: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, out)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        target = stack[-1][1] if stack else out
        if value == "":
            child: dict[str, Any] = {}
            target[key] = child
            stack.append((indent, child))
            continue
        target[key] = _coerce_value(value)
    return out


def _coerce_value(value: str) -> Any:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    token = value.strip()
    low = token.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none"):
        return None
    try:
        if any(ch in token for ch in (".", "e", "E")):
            return float(token)
        return int(token)
    except ValueError:
        return token
