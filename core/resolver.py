from __future__ import annotations

import re
from typing import Any


CURRENT_THRESHOLD = 0.30
STALE_THRESHOLD = -0.25


def resolve_answer(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    disputed: list[dict[str, Any]] = []

    for rank, item in enumerate(results, start=1):
        row = dict(item)
        row["rank"] = rank
        state = classify_memory_state(row)
        row["memory_state"] = state
        if state == "summary":
            summary.append(row)
        elif state == "current":
            current.append(row)
        elif state == "stale":
            stale.append(row)
        elif state == "disputed":
            disputed.append(row)
        else:
            historical.append(row)

    preferred = choose_preferred_evidence(query, results, summary, current, historical, disputed, stale)
    evidence = preferred[: min(3, len(preferred))]
    correction_conflict = has_correction_conflict_evidence(evidence)
    live_conflicts = detect_live_evidence_conflicts(evidence)
    summary_answer = bool(evidence) and evidence[0].get("memory_state") == "summary"
    summary_only = bool(evidence) and all(item.get("memory_state") == "summary" for item in evidence)
    evidence_has_current = any(item.get("memory_state") == "current" for item in evidence)
    evidence_has_stale = any(item.get("memory_state") == "stale" for item in evidence)
    evidence_has_disputed = any(item.get("memory_state") == "disputed" for item in evidence)
    conflict = (
        (bool(evidence_has_current and (evidence_has_stale or stale)) and not summary_only and not summary_answer)
        or evidence_has_disputed
        or (bool(disputed) and not allows_stale_definition_context(query))
        or correction_conflict
        or bool(live_conflicts)
    )
    confidence = estimate_confidence(evidence, conflict)
    answer = build_extractive_answer(
        query,
        evidence,
        stale,
        conflict,
        confidence,
        correction_conflict=correction_conflict,
        live_conflict=bool(live_conflicts),
    )

    return {
        "answer": answer,
        "confidence": confidence,
        "conflict": conflict,
        "evidence": [compact_evidence(item) for item in evidence],
        "summary": [compact_evidence(item) for item in summary],
        "current": [compact_evidence(item) for item in current],
        "historical": [compact_evidence(item) for item in historical],
        "stale": [compact_evidence(item) for item in stale],
        "disputed": [compact_evidence(item) for item in disputed],
        "live_conflicts": live_conflicts,
        "raw_results": results,
    }


def choose_preferred_evidence(
    query: str,
    results: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    current: list[dict[str, Any]],
    historical: list[dict[str, Any]],
    disputed: list[dict[str, Any]],
    stale: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not results:
        return []
    historical = [item for item in historical if is_relevant_to_query(query, item)]
    disputed = [item for item in disputed if is_relevant_to_query(query, item)]
    stale = [item for item in stale if is_relevant_to_query(query, item)]
    summary = [item for item in summary if is_relevant_to_query(query, item)]
    historical = sorted(historical, key=lambda item: evidence_preference_score(query, item), reverse=True)
    stale = sorted(stale, key=lambda item: evidence_preference_score(query, item), reverse=True)
    disputed = sorted(disputed, key=lambda item: evidence_preference_score(query, item), reverse=True)
    summary = sorted(summary, key=lambda item: evidence_preference_score(query, item), reverse=True)
    top_score = max(float(item.get("score") or 0.0) for item in results)
    if current:
        relevant_current = [item for item in current if is_relevant_to_query(query, item)]
        current_pool = relevant_current or ([] if (historical or stale or disputed) else current)
        current_score = max((float(item.get("score") or 0.0) for item in current_pool), default=0.0)
        relevance_floor = max(0.18, top_score * 0.90)
        if current_pool and (current_score >= relevance_floor or not (historical or summary)):
            return current_pool
    if summary and (asks_for_multiple(query) or asks_for_summary_mechanism(query)):
        return summary + historical + current
    if historical:
        supplemental_stale = []
        if allows_stale_definition_context(query):
            supplemental_stale = [
                item
                for item in stale
                if evidence_preference_score(query, item) >= evidence_preference_score(query, historical[0]) - 0.08
            ]
        return sorted(historical + supplemental_stale, key=lambda item: evidence_preference_score(query, item), reverse=True)
    return disputed or stale or current or summary


def classify_memory_state(item: dict[str, Any]) -> str:
    supersession = float(item.get("supersession_score") or 0.0)
    relation_supersession = float(item.get("relation_supersession_score") or 0.0)
    summary_relation = float(item.get("summary_relation_score") or 0.0)
    feedback = float(item.get("feedback_score") or 0.0)
    text = str(item.get("text") or "").lower()

    if text.startswith("consolidated summary:") or (summary_relation > 0.0 and "source memory ids:" in text):
        return "summary"

    stale_language = any(
        term in text
        for term in (
            "old ",
            "not final truth",
            "marked stale",
            "stale memory",
            "superseded",
            "no longer current",
            "historical but no longer current",
        )
    )
    correction_language = any(
        term in text
        for term in (
            "correction:",
            "must not",
            "only when",
            "prefer the corrected",
            "no longer current",
        )
    )

    if supersession <= STALE_THRESHOLD or relation_supersession < 0.0 or feedback <= -0.5:
        return "stale"
    if feedback < -0.2:
        return "disputed"
    if supersession >= CURRENT_THRESHOLD:
        return "current"
    if relation_supersession > 0.0 and correction_language:
        return "current"
    if correction_language and not stale_language:
        return "current"
    if stale_language:
        return "stale"
    return "historical"


def is_relevant_to_query(query: str, item: dict[str, Any]) -> bool:
    query_terms = normalized_terms(query)
    if not query_terms:
        return True
    text_terms = normalized_terms(clean_answer_text(item.get("text") or ""))
    domain_terms = normalized_terms(item.get("domain_name") or "")
    text_terms |= domain_terms
    if is_identity_query(query) and not has_identity_evidence(text_terms):
        return False
    if asks_for_previous_session_query(query) and not has_previous_session_evidence(text_terms):
        return False
    identity_terms = {"alpha", "beta", "gamma", "delta"}
    required_identity_terms = query_terms & identity_terms
    if required_identity_terms and not required_identity_terms <= text_terms:
        return False
    if domain_terms and query_terms & domain_terms:
        return True
    text_match = float(item.get("text_match_score") or 0.0)
    if text_match >= 0.34:
        return True
    overlap = query_terms & text_terms
    if len(overlap) >= max(1, len(query_terms) // 2):
        return True
    score = float(item.get("score") or 0.0)
    cosine = float(item.get("cosine") or 0.0)
    if score >= 0.30 or cosine >= 0.62:
        if overlap:
            return True
        if is_identity_query(query):
            return has_identity_evidence(text_terms)
        if asks_for_previous_session_query(query):
            return has_previous_session_evidence(text_terms)
        return asks_for_summary_mechanism(query)
    return False


def evidence_preference_score(query: str, item: dict[str, Any]) -> float:
    text = str(item.get("text") or "")
    clean_text = clean_answer_text(text)
    score = float(item.get("score") or 0.0)
    score += 0.20 * float(item.get("text_match_score") or 0.0)
    score += 0.05 * len(normalized_terms(query) & normalized_terms(clean_text))
    lower = text.lower()
    if lower.startswith("memory improvement for"):
        score -= 0.18
    if "original memory preview:" in lower:
        score -= 0.06
    if clean_text and not clean_text.lower().startswith("this memory is a core definition"):
        score += 0.04
    if str(item.get("memory_state") or "") == "summary" and asks_for_summary_mechanism(query):
        score += 0.12
    return score


def has_correction_conflict_evidence(evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        text = str(item.get("text") or "").lower()
        if "correction:" in text:
            return True
        if "corrected v" in text or "corrected evidence" in text:
            return True
        if "not " in text and any(term in text for term in ("instead", "rather than", " no longer ")):
            return True
    return False


def estimate_confidence(evidence: list[dict[str, Any]], conflict: bool) -> float:
    if not evidence:
        return 0.0
    top = evidence[0]
    score = float(top.get("score") or 0.0)
    feedback = max(0.0, float(top.get("feedback_score") or 0.0))
    supersession = max(0.0, float(top.get("supersession_score") or 0.0))
    relation = max(0.0, float(top.get("relation_supersession_score") or 0.0))
    summary = max(0.0, float(top.get("summary_relation_score") or 0.0))
    confidence = 0.35 + min(0.35, score / 2.0) + 0.12 * feedback + 0.10 * supersession + 0.08 * relation + 0.05 * summary
    if conflict:
        confidence -= 0.12
    return round(max(0.0, min(1.0, confidence)), 4)


def build_extractive_answer(
    query: str,
    evidence: list[dict[str, Any]],
    stale: list[dict[str, Any]],
    conflict: bool,
    confidence: float,
    correction_conflict: bool = False,
    live_conflict: bool = False,
) -> str:
    if not evidence:
        return "I do not have enough memory evidence to answer that yet."

    snippets = select_answer_snippets(query, evidence)
    if not snippets:
        snippets = [str(evidence[0].get("text") or "").strip()[:320]]

    if evidence[0].get("memory_state") == "summary":
        prefix = "Consolidated memory summary indicates"
    elif evidence[0].get("memory_state") == "current":
        prefix = "Current memory indicates"
    else:
        prefix = "Relevant memory indicates"
    answer = f"{prefix}: " + " ".join(snippets)
    if conflict and stale:
        answer += " Older or stale memories were also found, so the current/corrected evidence should be preferred."
    elif conflict and correction_conflict:
        answer += " This answer is based on corrected memory evidence."
    elif conflict and live_conflict:
        answer += " Conflicting evidence was retrieved, so this answer should be reviewed or corrected."
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
        if any(snippet == existing or snippet in existing or existing in snippet for existing in out):
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
    cleaned = clean_answer_text(text)
    if not cleaned:
        return []
    query_terms = normalized_terms(query)
    pieces = [
        piece.strip()
        for piece in re.split(r"(?<=[.!?])\s+|\s+-\s+|\s+(?=\d+\.\s+)", cleaned)
        if piece.strip()
    ]
    expanded_pieces: list[str] = []
    for idx, piece in enumerate(pieces):
        expanded_pieces.append(piece)
        if piece.rstrip().endswith(":") and idx + 1 < len(pieces):
            expanded_pieces.append(f"{piece} {pieces[idx + 1]}")
            if idx + 2 < len(pieces):
                expanded_pieces.append(f"{piece} {pieces[idx + 1]} {pieces[idx + 2]}")
    scored: list[tuple[float, int, str]] = []
    procedural_query = any(term in query.lower() for term in ("how", "workflow", "process", "steps", "test"))
    for idx, piece in enumerate(expanded_pieces):
        compact = piece.strip(" -*#")
        if not compact:
            continue
        lower = compact.lower()
        if lower.startswith("consolidated summary:") or lower.startswith("this summary preserves") or lower.startswith("key memory points:") or lower.startswith("source memory ids:"):
            continue
        piece_terms = normalized_terms(lower)
        hits = len(query_terms & piece_terms)
        coverage = hits / max(1, len(query_terms))
        correction_bonus = 2 if any(term in lower for term in ("correction", "current", "must", "only when")) else 0
        procedure_bonus = 0.0
        if procedural_query and any(term in lower for term in ("workflow", "build", "run ", "import", "re-run", "measure", "expected result", "adaptive ranking")):
            procedure_bonus = 1.4
        preference_bonus = 0.0
        if "preference" in query.lower() and any(term in lower for term in ("preference", "wants", "does not want", "only when")):
            preference_bonus = 0.8
        generic_intro_penalty = 0.0
        if lower.startswith("this document answers") or lower.startswith("this document restates") or lower.startswith("this document supersedes"):
            generic_intro_penalty = 4.0
        exact_phrase_bonus = 0.0
        for ngram in query_ngrams(query):
            if ngram in lower:
                exact_phrase_bonus += 0.4
        score = hits + 2.0 * coverage + correction_bonus + procedure_bonus + preference_bonus + min(1.2, exact_phrase_bonus) - generic_intro_penalty
        scored.append((score, -idx, compact))
    scored.sort(reverse=True)
    out = []
    for score, _idx, snippet in scored:
        if len(snippet) > 360:
            snippet = snippet[:357].rstrip() + "..."
        out.append((snippet, score))
    return out


def clean_answer_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    maintenance_match = re.match(r"Memory improvement for\s+mem_[A-Za-z0-9]+:\s*(.*)", cleaned, re.IGNORECASE)
    if maintenance_match:
        cleaned = maintenance_match.group(1).strip()
        preview_marker = " Original memory preview:"
        marker_idx = cleaned.lower().find(preview_marker.lower())
        if marker_idx >= 0:
            cleaned = cleaned[:marker_idx].strip()
    return cleaned


def normalized_terms(text: Any) -> set[str]:
    terms = set()
    lower_text = str(text or "").lower()
    for term in re.findall(r"[A-Za-z0-9_'-]+", str(text or "").lower()):
        if len(term) <= 2 or term in ANSWER_STOPWORDS:
            continue
        terms.add(stem_token(term))
        if "-" in term:
            compact = term.replace("-", "")
            if len(compact) > 2:
                terms.add(stem_token(compact))
    terms |= expanded_query_terms(lower_text, terms)
    return terms


def expanded_query_terms(lower_text: str, terms: set[str]) -> set[str]:
    expanded: set[str] = set()
    if re.search(r"\b(who am i|who i am|what am i|my identity|my name)\b", lower_text):
        expanded.update({"identity", "name", "user", "primary", "called", "agent", "hermes", "victor"})
    if terms & {"contradict", "contradiction", "conflict"} or "facts contradict" in lower_text:
        expanded.update({"contradict", "contradiction", "conflict", "protect", "protective", "correction", "stale", "csd"})
    if terms & {"consolidation", "consolidate"} or "consolidation work" in lower_text:
        expanded.update({"consolidation", "consolidate", "summary", "summarize", "summarizes", "original", "preserve", "source"})
    if "previous question" in lower_text or "remember previous" in lower_text:
        expanded.update({"session", "history", "turn", "context", "previous", "questions", "remember"})
    if terms & {"maintain", "maintains"}:
        expanded.add("maintain")
        expanded.add("maintains")
    return expanded


def is_identity_query(query: str) -> bool:
    return bool(re.search(r"\b(who am i|who i am|what am i|my identity|my name)\b", str(query or "").lower()))


def has_identity_evidence(text_terms: set[str]) -> bool:
    return bool(text_terms & {"name", "called", "victor"} or {"primary", "user"} <= text_terms)


def asks_for_previous_session_query(query: str) -> bool:
    lower = str(query or "").lower()
    return "previous question" in lower or "remember previous" in lower or "session history" in lower


def has_previous_session_evidence(text_terms: set[str]) -> bool:
    return bool(text_terms & {"session", "history", "turn", "context", "previous", "question"})


def is_short_natural_query(query: str) -> bool:
    terms = normalized_terms(query)
    raw_terms = re.findall(r"[A-Za-z0-9_'-]+", str(query or "").lower())
    return len(raw_terms) <= 5 and len(terms) <= 8


def stem_token(term: str) -> str:
    term = str(term or "").lower().strip()
    if len(term) > 5 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 5 and term.endswith("ing"):
        return term[:-3]
    if len(term) > 4 and term.endswith("es"):
        return term[:-2]
    if len(term) > 3 and term.endswith("s"):
        return term[:-1]
    return term


def detect_live_evidence_conflicts(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in evidence:
        fact = extract_simple_fact(item.get("text") or "")
        if fact is None:
            continue
        facts.setdefault((fact["relation"], fact["object"]), []).append({**fact, "memory_id": item.get("memory_id")})
    conflicts: list[dict[str, Any]] = []
    for (_relation, _object), rows in facts.items():
        positives = [row for row in rows if not row["negated"]]
        seen_subjects = {row["subject"] for row in positives}
        if len(seen_subjects) <= 1:
            continue
        conflicts.append(
            {
                "type": "incompatible_fact_values",
                "relation": rows[0]["relation"],
                "object": rows[0]["object"],
                "subjects": sorted(seen_subjects),
                "memory_ids": [row["memory_id"] for row in positives if row.get("memory_id")],
            }
        )
    return conflicts


def extract_simple_fact(text: str) -> dict[str, Any] | None:
    cleaned = clean_answer_text(text).strip()
    if cleaned.lower().startswith("correction:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    match = re.search(
        r"\b(?P<subject>[A-Z][A-Za-z0-9_ -]{1,80}?)\s+is\s+(?P<negated>not\s+)?(?:the\s+)?(?P<relation>capital)\s+of\s+(?P<object>[A-Z][A-Za-z0-9_ -]{1,80})\b",
        cleaned,
    )
    if not match:
        return None
    return {
        "subject": normalize_fact_value(match.group("subject")),
        "relation": match.group("relation").lower(),
        "object": normalize_fact_value(match.group("object")),
        "negated": bool(match.group("negated")),
    }


def normalize_fact_value(value: str) -> str:
    return " ".join(str(value or "").strip(" .,:;!?").lower().split())


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
    return any(term in lower for term in ("summarize", "summary", "list", "all ", "main points", "what are")) or (
        "how" in lower and any(term in lower for term in ("test", "workflow", "process", "steps"))
    )


def asks_for_summary_mechanism(query: str) -> bool:
    lower = str(query or "").lower()
    if "summary" in lower or "summarize" in lower or "overview" in lower:
        return True
    return bool(
        ("consolidation" in lower or "consolidate" in lower)
        and any(term in lower for term in ("how does", "how do", "work", "workflow", "process", "mechanism"))
        and not any(term in lower for term in ("preserve original", "source memor", "evidence id"))
    )


def allows_stale_definition_context(query: str) -> bool:
    lower = str(query or "").lower().strip()
    if any(
        term in lower
        for term in (
            "current",
            "policy",
            "preference",
            "rule",
            "style",
            "should",
            "must",
            "allowed",
            "latest",
            "correct",
            "final",
        )
    ):
        return False
    definition_starts = ("what is ", "what are ", "what does ", "define ", "explain ")
    return lower.startswith(definition_starts) or "states exist" in lower


def compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": item.get("memory_id"),
        "rank": item.get("rank"),
        "memory_state": item.get("memory_state"),
        "score": item.get("score"),
        "namespace": item.get("namespace"),
        "domain_id": item.get("domain_id"),
        "source": item.get("source"),
        "chunk_index": item.get("chunk_index"),
        "domain_name": item.get("domain_name"),
        "memory_type": item.get("memory_type"),
        "feedback_score": item.get("feedback_score"),
        "supersession_score": item.get("supersession_score"),
        "relation_supersession_score": item.get("relation_supersession_score"),
        "summary_relation_score": item.get("summary_relation_score"),
        "text_preview": str(item.get("text") or "")[:320],
    }
