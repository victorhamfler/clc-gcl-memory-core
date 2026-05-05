from __future__ import annotations

import re

from core.models import SignalPacket


ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_-]{2,}\b|`([^`]+)`")
CODE_RE = re.compile(r"\b(error|exception|traceback|failed|failure|bug|regression|timeout|crash)\b", re.I)
INSTRUCTION_RE = re.compile(r"\b(should|must|need|build|implement|remember|use|create|fix|design)\b", re.I)


def classify_memory_type(text: str) -> str:
    lower = text.lower()
    if CODE_RE.search(text):
        return "error_memory"
    if "prefer" in lower or "preference" in lower:
        return "preference"
    if "should" in lower or "must" in lower or "design" in lower:
        return "design_rule"
    if "how to" in lower or "steps" in lower:
        return "procedure"
    return "semantic_note"


def infer_domains(text: str) -> list[str]:
    lower = text.lower()
    domains: list[str] = []
    known = {
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
    for needle, label in known.items():
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


def build_signal_packet(text: str, embedding: list[float]) -> SignalPacket:
    return SignalPacket(
        text=text,
        embedding=embedding,
        memory_type=classify_memory_type(text),
        domains=infer_domains(text),
        entities=extract_entities(text),
        importance=estimate_importance(text),
        confidence=0.55,
        error_signal=1.0 if CODE_RE.search(text) else 0.0,
        user_instruction=1.0 if INSTRUCTION_RE.search(text) else 0.0,
    )
