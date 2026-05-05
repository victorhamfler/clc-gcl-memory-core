from __future__ import annotations

import re
from typing import Any


CURRENT_THRESHOLD = 0.30
STALE_THRESHOLD = -0.25


def resolve_answer(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    current: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    disputed: list[dict[str, Any]] = []

    for rank, item in enumerate(results, start=1):
        row = dict(item)
        row["rank"] = rank
        state = classify_memory_state(row)
        row["memory_state"] = state
        if state == "current":
            current.append(row)
        elif state == "stale":
            stale.append(row)
        elif state == "disputed":
            disputed.append(row)
        else:
            historical.append(row)

    preferred = choose_preferred_evidence(results, current, historical, disputed, stale)
    evidence = preferred[: min(3, len(preferred))]
    conflict = bool((current or historical) and stale) or bool(disputed)
    confidence = estimate_confidence(evidence, conflict)
    answer = build_extractive_answer(query, evidence, stale, conflict, confidence)

    return {
        "answer": answer,
        "confidence": confidence,
        "conflict": conflict,
        "evidence": [compact_evidence(item) for item in evidence],
        "current": [compact_evidence(item) for item in current],
        "historical": [compact_evidence(item) for item in historical],
        "stale": [compact_evidence(item) for item in stale],
        "disputed": [compact_evidence(item) for item in disputed],
        "raw_results": results,
    }


def choose_preferred_evidence(
    results: list[dict[str, Any]],
    current: list[dict[str, Any]],
    historical: list[dict[str, Any]],
    disputed: list[dict[str, Any]],
    stale: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not results:
        return []
    top_score = max(float(item.get("score") or 0.0) for item in results)
    if current:
        current_score = max(float(item.get("score") or 0.0) for item in current)
        relevance_floor = max(0.18, top_score * 0.90)
        if current_score >= relevance_floor or not historical:
            return current
    return historical or current or disputed or stale


def classify_memory_state(item: dict[str, Any]) -> str:
    supersession = float(item.get("supersession_score") or 0.0)
    relation_supersession = float(item.get("relation_supersession_score") or 0.0)
    feedback = float(item.get("feedback_score") or 0.0)
    text = str(item.get("text") or "").lower()

    stale_language = any(
        term in text
        for term in (
            "old ",
            "not final truth",
            "stale",
            "superseded",
            "no longer current",
            "historical but no longer current",
        )
    )
    correction_language = any(
        term in text
        for term in (
            "correction:",
            "current",
            "must not",
            "only when",
            "supersedes",
            "prefer the corrected",
        )
    )

    if supersession <= STALE_THRESHOLD or relation_supersession < 0.0 or feedback <= -0.5:
        return "stale"
    if feedback < -0.2:
        return "disputed"
    if supersession >= CURRENT_THRESHOLD or relation_supersession > 0.0:
        return "current"
    if correction_language and not stale_language:
        return "current"
    if stale_language:
        return "stale"
    return "historical"


def estimate_confidence(evidence: list[dict[str, Any]], conflict: bool) -> float:
    if not evidence:
        return 0.0
    top = evidence[0]
    score = float(top.get("score") or 0.0)
    feedback = max(0.0, float(top.get("feedback_score") or 0.0))
    supersession = max(0.0, float(top.get("supersession_score") or 0.0))
    relation = max(0.0, float(top.get("relation_supersession_score") or 0.0))
    confidence = 0.35 + min(0.35, score / 2.0) + 0.12 * feedback + 0.10 * supersession + 0.08 * relation
    if conflict:
        confidence -= 0.12
    return round(max(0.0, min(1.0, confidence)), 4)


def build_extractive_answer(
    query: str,
    evidence: list[dict[str, Any]],
    stale: list[dict[str, Any]],
    conflict: bool,
    confidence: float,
) -> str:
    if not evidence:
        return "I do not have enough memory evidence to answer that yet."

    snippets = select_answer_snippets(query, evidence)
    if not snippets:
        snippets = [str(evidence[0].get("text") or "").strip()[:320]]

    prefix = "Current memory indicates" if evidence[0].get("memory_state") == "current" else "Relevant memory indicates"
    answer = f"{prefix}: " + " ".join(snippets)
    if conflict and stale:
        answer += " Older or stale memories were also found, so the current/corrected evidence should be preferred."
    if confidence < 0.45:
        answer += " Confidence is low because the retrieved evidence is weak."
    return answer.strip()


def select_answer_snippets(query: str, evidence: list[dict[str, Any]]) -> list[str]:
    scored: list[tuple[float, int, str]] = []
    for evidence_idx, item in enumerate(evidence[:3]):
        for snippet, score in candidate_snippets(query, item.get("text") or ""):
            if snippet:
                scored.append((score, -evidence_idx, snippet))
    if not scored:
        return []
    scored.sort(reverse=True)
    out = [scored[0][2]]
    multi = asks_for_multiple(query)
    for score, _idx, snippet in scored[1:]:
        if snippet in out:
            continue
        if multi or (score >= max(1.0, scored[0][0] * 0.82) and len(out) < 2):
            out.append(snippet)
        if len(out) >= (3 if multi else 2):
            break
    return out


def best_snippet(query: str, text: str) -> str:
    snippets = candidate_snippets(query, text)
    return snippets[0][0] if snippets else ""


def candidate_snippets(query: str, text: str) -> list[tuple[str, float]]:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return []
    query_terms = {
        term
        for term in re.findall(r"[A-Za-z0-9_'-]+", query.lower())
        if len(term) > 2 and term not in ANSWER_STOPWORDS
    }
    pieces = re.split(r"(?<=[.!?])\s+|\s+-\s+", cleaned)
    scored: list[tuple[float, int, str]] = []
    for idx, piece in enumerate(pieces):
        compact = piece.strip(" -*")
        if not compact:
            continue
        lower = compact.lower()
        piece_terms = {
            term
            for term in re.findall(r"[A-Za-z0-9_'-]+", lower)
            if len(term) > 2 and term not in ANSWER_STOPWORDS
        }
        hits = len(query_terms & piece_terms)
        coverage = hits / max(1, len(query_terms))
        correction_bonus = 2 if any(term in lower for term in ("correction", "current", "must", "only when")) else 0
        exact_phrase_bonus = 0.0
        for ngram in query_ngrams(query):
            if ngram in lower:
                exact_phrase_bonus += 0.4
        score = hits + 2.0 * coverage + correction_bonus + min(1.2, exact_phrase_bonus)
        scored.append((score, -idx, compact))
    scored.sort(reverse=True)
    out = []
    for score, _idx, snippet in scored:
        if len(snippet) > 360:
            snippet = snippet[:357].rstrip() + "..."
        out.append((snippet, score))
    return out


ANSWER_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "decide",
    "does",
    "for",
    "from",
    "handle",
    "how",
    "should",
    "that",
    "the",
    "this",
    "use",
    "what",
    "when",
    "where",
    "whether",
    "which",
    "with",
}


def query_ngrams(query: str) -> list[str]:
    terms = [
        term
        for term in re.findall(r"[A-Za-z0-9_'-]+", query.lower())
        if len(term) > 2 and term not in ANSWER_STOPWORDS
    ]
    grams = []
    for size in (3, 2):
        for idx in range(0, max(0, len(terms) - size + 1)):
            grams.append(" ".join(terms[idx : idx + size]))
    return grams


def asks_for_multiple(query: str) -> bool:
    lower = str(query or "").lower()
    return any(term in lower for term in ("summarize", "summary", "list", "all ", "main points", "what are"))


def compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": item.get("memory_id"),
        "rank": item.get("rank"),
        "memory_state": item.get("memory_state"),
        "score": item.get("score"),
        "source": item.get("source"),
        "chunk_index": item.get("chunk_index"),
        "domain_name": item.get("domain_name"),
        "memory_type": item.get("memory_type"),
        "feedback_score": item.get("feedback_score"),
        "supersession_score": item.get("supersession_score"),
        "relation_supersession_score": item.get("relation_supersession_score"),
        "text_preview": str(item.get("text") or "")[:320],
    }
