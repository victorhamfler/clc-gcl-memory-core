from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"\S+")


def clean_text(text: str) -> str:
    out = str(text or "").replace("\ufeff", "")
    try:
        fixed = out.encode("latin1").decode("utf-8")
        if fixed.count("\ufffd") <= out.count("\ufffd"):
            out = fixed
    except UnicodeError:
        pass
    replacements = {
        "\u00e2\u20ac\u201d": "-",
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u2020\u2019": "->",
        "\u00e2\u20ac\u0153": '"',
        "\u00e2\u20ac\u009d": '"',
        "\u00e2\u20ac\u02dc": "'",
        "\u00e2\u20ac\u2122": "'",
        "\u00c2": "",
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def chunk_text(text: str, max_words: int = 120, overlap_words: int = 20) -> list[str]:
    text = clean_text(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]

    chunks: list[str] = []
    pending: list[str] = []
    for paragraph in paragraphs:
        words = WORD_RE.findall(paragraph)
        if not words:
            continue
        if len(words) > max_words:
            if pending:
                chunks.append(" ".join(pending).strip())
                pending = []
            chunks.extend(_window_words(words, max_words=max_words, overlap_words=overlap_words))
            continue
        if pending and len(pending) + len(words) > max_words:
            chunks.append(" ".join(pending).strip())
            pending = pending[-overlap_words:] if overlap_words > 0 else []
        pending.extend(words)
    if pending:
        chunks.append(" ".join(pending).strip())
    return [c for c in chunks if c]


def load_texts_from_file(path: str | Path, max_words: int = 120, overlap_words: int = 20) -> list[str]:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".jsonl":
        return _load_jsonl(file_path, max_words=max_words, overlap_words=overlap_words)
    if suffix == ".json":
        return _load_json(file_path, max_words=max_words, overlap_words=overlap_words)
    return chunk_text(file_path.read_text(encoding="utf-8"), max_words=max_words, overlap_words=overlap_words)


def _window_words(words: list[str], max_words: int, overlap_words: int) -> list[str]:
    out: list[str] = []
    step = max(1, max_words - max(0, overlap_words))
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if window:
            out.append(" ".join(window).strip())
        if start + max_words >= len(words):
            break
    return out


def _load_jsonl(path: Path, max_words: int, overlap_words: int) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out.extend(chunk_text(line, max_words=max_words, overlap_words=overlap_words))
            continue
        text = _text_from_obj(obj)
        if text:
            out.extend(chunk_text(text, max_words=max_words, overlap_words=overlap_words))
    return out


def _load_json(path: Path, max_words: int, overlap_words: int) -> list[str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    texts = _texts_from_any(obj)
    out: list[str] = []
    for text in texts:
        out.extend(chunk_text(text, max_words=max_words, overlap_words=overlap_words))
    return out


def _texts_from_any(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_texts_from_any(item))
        return out
    if isinstance(value, dict):
        text = _text_from_obj(value)
        if text:
            return [text]
        out: list[str] = []
        for item in value.values():
            out.extend(_texts_from_any(item))
        return out
    return []


def _text_from_obj(obj: Any) -> str:
    if isinstance(obj, str):
        return obj.strip()
    if not isinstance(obj, dict):
        return ""
    for key in ("text", "content", "message", "body", "summary"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = []
    for key in ("role", "title", "name"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return ": ".join(parts)
