from __future__ import annotations

import re
from typing import Any

from core.models import SignalPacket


ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_-]{2,}\b|`([^`]+)`")
CODE_RE = re.compile(r"\b(error|exception|traceback|failed|failure|bug|regression|timeout|crash)\b", re.I)
INSTRUCTION_RE = re.compile(r"\b(should|must|need|build|implement|remember|use|create|fix|design)\b", re.I)

DEFAULT_DOMAIN_ALIASES = {
    "clc": "CLC",
    "csd": "CSD",
    "g-cl": "G-CL",
    "gcl": "G-CL",
    "geometry controller": "OpenClaw",
    "lcm geometry": "OpenClaw",
    "openclaw": "OpenClaw",
    "clgk": "CLGK",
    "robot": "robotics",
    "webots": "robotics",
    "lora": "model_training",
    "memory": "agent_memory",
}

DEFAULT_TYPE_KEYWORDS = {
    "preference": (
        "prefer",
        "preference",
        "likes",
        "loves",
        "hates",
        "dislikes",
        "values",
        "wants",
    ),
    "design_rule": ("should", "must", "design"),
    "procedure": ("how to", "steps"),
}


def classify_memory_type(text: str, symbolic_config: dict[str, Any] | None = None) -> str:
    lower = text.lower()
    keywords = _memory_type_keywords(symbolic_config)
    if CODE_RE.search(text):
        return "error_memory"
    if _contains_any(lower, keywords["preference"]):
        return "preference"
    if _contains_any(lower, keywords["design_rule"]):
        return "design_rule"
    if _contains_any(lower, keywords["procedure"]):
        return "procedure"
    return "semantic_note"


def infer_domains(text: str, symbolic_config: dict[str, Any] | None = None) -> list[str]:
    lower = text.lower()
    domains: list[str] = []
    for needle, label in _domain_aliases(symbolic_config).items():
        if needle in lower and label not in domains:
            domains.append(label)
    return domains or ["general"]


def extract_entities(text: str) -> list[str]:
    out: list[str] = []
    for match in ENTITY_RE.finditer(text):
        value = match.group(1) or match.group(0)
        value = value.strip("` ")
        if value and value not in out:
            out.append(value)
    return out[:24]


def estimate_importance(text: str) -> float:
    score = 0.35
    if INSTRUCTION_RE.search(text):
        score += 0.25
    if CODE_RE.search(text):
        score += 0.20
    if len(text) > 240:
        score += 0.10
    if "important" in text.lower() or "reference" in text.lower():
        score += 0.15
    return min(1.0, score)


def build_signal_packet(
    text: str,
    embedding: list[float],
    symbolic_config: dict[str, Any] | None = None,
) -> SignalPacket:
    return SignalPacket(
        text=text,
        embedding=embedding,
        memory_type=classify_memory_type(text, symbolic_config),
        domains=infer_domains(text, symbolic_config),
        entities=extract_entities(text),
        importance=estimate_importance(text),
        confidence=0.55,
        error_signal=1.0 if CODE_RE.search(text) else 0.0,
        user_instruction=1.0 if INSTRUCTION_RE.search(text) else 0.0,
    )


def symbolic_vocabulary(symbolic_config: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "domain_aliases": _domain_aliases(symbolic_config),
        "memory_type_keywords": {
            key: list(values)
            for key, values in _memory_type_keywords(symbolic_config).items()
        },
    }


def _domain_aliases(symbolic_config: dict[str, Any] | None) -> dict[str, str]:
    aliases = dict(DEFAULT_DOMAIN_ALIASES)
    aliases.update(_parse_alias_map((symbolic_config or {}).get("domain_aliases")))
    for disabled in _parse_csv((symbolic_config or {}).get("disabled_domain_aliases")):
        aliases.pop(disabled.lower(), None)
    return {str(needle).lower(): str(label) for needle, label in aliases.items() if str(needle).strip() and str(label).strip()}


def _memory_type_keywords(symbolic_config: dict[str, Any] | None) -> dict[str, tuple[str, ...]]:
    cfg = symbolic_config or {}
    out: dict[str, tuple[str, ...]] = {}
    for memory_type, defaults in DEFAULT_TYPE_KEYWORDS.items():
        configured = _parse_csv(cfg.get(f"{memory_type}_keywords"))
        out[memory_type] = tuple(configured or defaults)
    return out


def _parse_alias_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k).strip().lower(): str(v).strip() for k, v in value.items() if str(k).strip() and str(v).strip()}
    out: dict[str, str] = {}
    for item in _parse_csv(value):
        if "=" not in item:
            continue
        key, label = item.split("=", 1)
        key = key.strip().lower()
        label = label.strip()
        if key and label:
            out[key] = label
    return out


def _parse_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle and needle in text for needle in needles)
