from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_alias_candidates.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_alias_candidates_report.md"
POSITIVE_LABELS = {"accepted", "correct", "excellent", "good", "helpful", "useful"}
NEGATIVE_LABELS = {"bad", "incomplete", "incorrect", "missing_source", "stale", "wrong", "wrong_domain"}
OWNER_RELATION_ALIAS_TERMS = {
    "accountable",
    "assignee",
    "assigned",
    "assignment",
    "ownership",
    "responsible",
    "responsibility",
}
SLOT_HINTS = {
    "backend_port": {"backend", "port"},
    "codename": {"codename"},
    "decision": {"decision", "decide", "decided"},
    "deadline": {"deadline", "due", "when"},
    "drink": {"drink", "water", "espresso", "sparkling"},
    "filename": {"file", "filename"},
    "github_upload": {"github", "upload", "uploads", "uploading"},
    "calendar_change": {"calendar", "schedule", "meeting", "meetings", "event", "events", "change", "changing"},
    "mechanism": {"maintain", "maintains", "detect", "detects"},
    "method": {"method", "tool"},
    "owner": {"accountable", "assignee", "assigned", "owner", "owns", "responsible", "responsibility", "belong", "belongs", "who"},
    "pizza": {"pizza", "cheese", "mushroom"},
    "policy": {"policy", "rule"},
    "preference": {"prefer", "prefers", "preference"},
    "status": {"status", "ready", "blocked"},
}
GENERIC_TERMS = {
    "about",
    "agent",
    "and",
    "answer",
    "answers",
    "api",
    "ask",
    "before",
    "checks",
    "current",
    "currently",
    "correction",
    "corrected",
    "does",
    "evidence",
    "feedback",
    "for",
    "global",
    "hermes",
    "indicates",
    "linked",
    "memory",
    "memories",
    "not",
    "older",
    "only",
    "prefer",
    "prefers",
    "preference",
    "project",
    "query",
    "ready",
    "relevant",
    "retrieval",
    "sample",
    "session",
    "should",
    "stale",
    "test",
    "tests",
    "that",
    "the",
    "this",
    "use",
    "user_rules",
    "user",
    "victor",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "were",
    "also",
    "found",
    "preferred",
    "draft",
}


def default_log_path() -> Path:
    config = load_config(ROOT)
    cfg = config.get("outcome_log") if isinstance(config.get("outcome_log"), dict) else {}
    return resolve_project_path(ROOT, cfg.get("path"), "logs/memory_outcomes.jsonl")


def tokens(text: str) -> list[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9_+-]*|\d+", str(text or ""))]


def phrase_terms(text: str) -> list[str]:
    raw = tokens(text)
    negated = set()
    for index, token in enumerate(raw):
        if token in {"not", "no"}:
            negated.update(raw[index + 1 : index + 4])
    out = []
    for token in raw:
        if len(token) <= 2 or token in GENERIC_TERMS:
            continue
        if token in negated:
            continue
        if re.search(r"_v\d+$", token) or re.fullmatch(r"v\d+", token):
            continue
        if token.endswith(".md") or token in {"md", "sample"}:
            continue
        out.append(token)
    return out


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            events.append(
                {
                    "operation_id": f"parse_error_{line_no}",
                    "event_type": "parse_error",
                    "payload": {"error": str(exc), "line_no": line_no},
                }
            )
    return events


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def feedback_signal(event: dict[str, Any]) -> tuple[str, str, float, str | None]:
    payload = event_payload(event)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    feedback = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else {}
    label = str(request.get("label") or feedback.get("label") or "").strip().lower()
    memory_id = str(request.get("memory_id") or feedback.get("memory_id") or "").strip() or None
    try:
        rating = float(request.get("rating", feedback.get("rating", 0.0)) or 0.0)
    except (TypeError, ValueError):
        rating = 0.0
    if label in POSITIVE_LABELS or rating >= 0.5:
        return "positive", label, rating, memory_id
    if label in NEGATIVE_LABELS or rating <= -0.5:
        return "negative", label, rating, memory_id
    return "unclear", label, rating, memory_id


def rows_by_memory(source_event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = event_payload(source_event)
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    out = {}
    for section in ("evidence", "raw_results", "source_context", "stale_context"):
        for row in response.get(section) or []:
            memory_id = str(row.get("memory_id") or "").strip()
            if memory_id and memory_id not in out:
                out[memory_id] = row
    return out


def source_text_for_feedback(source_event: dict[str, Any], memory_id: str | None) -> tuple[str, list[str]]:
    payload = event_payload(source_event)
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    sections = []
    if memory_id:
        row = rows_by_memory(source_event).get(memory_id)
        if row:
            sections.append(str(row.get("text") or ""))
    if not sections:
        sections.append(str(response.get("answer") or ""))
    return "\n".join(section for section in sections if section), sections


def owner_alias_terms(text: str, query: str) -> list[str]:
    query_terms = set(tokens(query))
    terms = []
    patterns = [
        r"\b([A-Z][A-Za-z0-9_+-]*(?:\s+(?:agent|team|group|diagnostics|[A-Z][A-Za-z0-9_+-]*)){0,2})\s+owns\b",
        r"\bowner\s+(?:should\s+be|is|:)\s+([A-Z][A-Za-z0-9_+-]*(?:\s+(?:agent|team|group|diagnostics|[A-Z][A-Za-z0-9_+-]*)){0,2})\b",
        r"\bowned\s+by\s+([A-Z][A-Za-z0-9_+-]*(?:\s+(?:agent|team|group|diagnostics|[A-Z][A-Za-z0-9_+-]*)){0,2})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or "")):
            candidate = "_".join(tokens(match.group(1)))
            if not candidate or candidate in query_terms or candidate in GENERIC_TERMS:
                continue
            if any(part in query_terms for part in candidate.split("_")):
                continue
            terms.append(candidate)
    return terms


def infer_slots(query: str) -> list[str]:
    query_terms = set(tokens(query))
    if "codename" in query_terms:
        return ["codename"]
    if "filename" in query_terms or "file" in query_terms:
        return ["filename"]
    if query_terms & {"who", "owner", "owns", "accountable", "assignee", "assigned", "responsible", "responsibility"}:
        return ["owner"]
    if query_terms & {"when", "deadline", "due"}:
        return ["deadline"]
    slots = []
    for slot, hints in SLOT_HINTS.items():
        if query_terms & hints:
            slots.append(slot)
    if not slots and "prefer" in query_terms:
        slots.append("preference")
    if not slots and {"what", "is"} <= query_terms:
        slots.append("definition")
    specific = [slot for slot in slots if slot not in {"method", "policy", "preference"}]
    if specific:
        slots = specific
    if any(slot in slots for slot in {"drink", "pizza"}):
        slots = [slot for slot in slots if slot != "preference"]
    if any(slot in slots for slot in {"backend_port", "filename"}):
        slots = [slot for slot in slots if slot != "method"]
    if "codename" in slots:
        slots = [slot for slot in slots if slot != "owner"]
    if any(
        slot in slots
        for slot in {
            "backend_port",
            "calendar_change",
            "codename",
            "drink",
            "filename",
            "github_upload",
            "mechanism",
            "method",
            "pizza",
            "status",
        }
    ):
        slots = [slot for slot in slots if slot != "policy"]
    return slots or ["general_claim"]


def candidate_terms(text: str, query: str, slot: str) -> list[str]:
    query_terms = set(tokens(query))
    slot_terms = set(tokens(slot.replace("_", " ")))
    hint_terms = SLOT_HINTS.get(slot, set())
    out = []
    if slot == "owner":
        return [term for term in phrase_terms(text) if term in OWNER_RELATION_ALIAS_TERMS and term not in query_terms]
    for term in phrase_terms(text):
        if term in query_terms or term in slot_terms or term in hint_terms:
            continue
        if term.isdigit() and slot not in {"backend_port", "deadline"}:
            continue
        out.append(term)
    return out


def confidence(positive_count: int, negative_count: int, alias_count: int) -> float:
    if positive_count <= 0 or alias_count <= 0:
        return 0.0
    support = min(1.0, positive_count / 5.0)
    balance = positive_count / max(1, positive_count + negative_count)
    compactness = 1.0 if alias_count <= 6 else max(0.5, 6 / alias_count)
    return round(max(0.0, min(1.0, 0.50 * support + 0.35 * balance + 0.15 * compactness)), 4)


def build_candidates(events: list[dict[str, Any]], source_logs: list[Path]) -> dict[str, Any]:
    by_operation = {str(event.get("operation_id")): event for event in events if event.get("operation_id")}
    slot_alias_counts: dict[str, Counter[str]] = defaultdict(Counter)
    slot_excluded_counts: dict[str, Counter[str]] = defaultdict(Counter)
    slot_positive: Counter[str] = Counter()
    slot_negative: Counter[str] = Counter()
    slot_positive_queries: dict[str, list[str]] = defaultdict(list)
    slot_negative_queries: dict[str, list[str]] = defaultdict(list)
    slot_memory_ids: dict[str, set[str]] = defaultdict(set)
    rejected_feedback = []

    for event in events:
        if event.get("event_type") != "feedback":
            continue
        linked_id = str(event.get("linked_operation_id") or "").strip()
        source_event = by_operation.get(linked_id)
        kind, label, rating, memory_id = feedback_signal(event)
        if source_event is None:
            rejected_feedback.append(
                {
                    "feedback_operation_id": event.get("operation_id"),
                    "linked_operation_id": linked_id or None,
                    "reason": "missing_linked_operation",
                    "label": label,
                    "rating": rating,
                }
            )
            continue
        payload = event_payload(source_event)
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        query = str(request.get("query") or "").strip()
        if not query or kind == "unclear":
            continue
        slots = infer_slots(query)
        evidence_text, _sections = source_text_for_feedback(source_event, memory_id)
        terms = candidate_terms(evidence_text, query, slots[0])
        if kind == "negative" and label == "stale":
            source_payload = event_payload(source_event)
            response = source_payload.get("response") if isinstance(source_payload.get("response"), dict) else {}
            desired_text = "\n".join(
                [str(response.get("answer") or "")]
                + [str(row.get("text") or "") for row in response.get("evidence") or []]
            )
            desired_terms = set(candidate_terms(desired_text, query, slots[0]))
            terms = [term for term in terms if term not in desired_terms]
        for slot in slots:
            if kind == "positive" and query not in slot_positive_queries[slot]:
                slot_positive_queries[slot].append(query)
            if kind == "negative" and query not in slot_negative_queries[slot]:
                slot_negative_queries[slot].append(query)
            if memory_id:
                slot_memory_ids[slot].add(memory_id)
            if kind == "positive":
                slot_positive[slot] += 1
                slot_alias_counts[slot].update(terms)
            else:
                slot_negative[slot] += 1
                slot_excluded_counts[slot].update(terms)

    candidates = []
    for slot in sorted(set(slot_positive) | set(slot_negative)):
        aliases = [
            term
            for term, count in slot_alias_counts[slot].most_common(10)
            if count > slot_excluded_counts[slot][term]
        ][:8]
        excluded_terms = [
            term
            for term, count in slot_excluded_counts[slot].most_common(8)
            if count >= slot_alias_counts[slot][term]
        ][:5]
        positive_count = int(slot_positive[slot])
        negative_count = int(slot_negative[slot])
        if not aliases and positive_count <= 0:
            continue
        candidates.append(
            {
                "slot": slot,
                "aliases": aliases,
                "excluded_terms": excluded_terms,
                "supporting_queries": slot_positive_queries[slot][:8],
                "negative_queries": slot_negative_queries[slot][:8],
                "supporting_memory_ids": sorted(slot_memory_ids[slot])[:12],
                "positive_count": positive_count,
                "negative_count": negative_count,
                "confidence": confidence(positive_count, negative_count, len(aliases)),
                "notes": (
                    "Candidate mined from linked feedback. Review manually before adding to claim_scope.slot_aliases."
                    if positive_count
                    else "Only negative support found; use excluded terms cautiously."
                ),
            }
        )
    candidates.sort(key=lambda row: (row["confidence"], row["positive_count"], -row["negative_count"]), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_logs": [str(path) for path in source_logs],
        "event_count": len(events),
        "ask_count": sum(1 for event in events if event.get("event_type") == "ask"),
        "feedback_count": sum(1 for event in events if event.get("event_type") == "feedback"),
        "linked_feedback_count": sum(
            1 for event in events if event.get("event_type") == "feedback" and event.get("linked_operation_id")
        ),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejected_feedback": rejected_feedback[:20],
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Claim Scope Alias Candidate Report",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Source logs: `{', '.join(report['source_logs'])}`",
        f"Events: `{report['event_count']}`",
        f"Asks: `{report['ask_count']}`",
        f"Feedback: `{report['feedback_count']}`",
        f"Linked feedback: `{report['linked_feedback_count']}`",
        f"Candidates: `{report['candidate_count']}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("- No reliable candidates yet.")
    for candidate in report["candidates"]:
        lines.append(
            f"- `{candidate['slot']}` confidence `{candidate['confidence']}` "
            f"positive `{candidate['positive_count']}` negative `{candidate['negative_count']}`"
        )
        lines.append(f"  aliases: `{', '.join(candidate['aliases']) or 'none'}`")
        lines.append(f"  excluded: `{', '.join(candidate['excluded_terms']) or 'none'}`")
        for query in candidate["supporting_queries"][:3]:
            lines.append(f"  query: {query}")
        for query in candidate.get("negative_queries", [])[:2]:
            lines.append(f"  negative query: {query}")
    lines.extend(["", "## Rejected Feedback", ""])
    if not report["rejected_feedback"]:
        lines.append("- None")
    for item in report["rejected_feedback"]:
        lines.append(f"- `{item.get('feedback_operation_id')}`: {item.get('reason')}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine claim-scope alias candidates from linked memory outcome logs.")
    parser.add_argument("--log", action="append", dest="logs", help="Outcome JSONL path. Can be passed more than once.")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    log_paths = [Path(path) for path in args.logs] if args.logs else [default_log_path()]
    events: list[dict[str, Any]] = []
    for path in log_paths:
        events.extend(load_events(path))
    report = build_candidates(events, log_paths)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": True,
                "candidate_count": report["candidate_count"],
                "ask_count": report["ask_count"],
                "feedback_count": report["feedback_count"],
                "linked_feedback_count": report["linked_feedback_count"],
                "json": str(out_json),
                "markdown": str(out_md),
                "top_candidates": [
                    {
                        "slot": item["slot"],
                        "aliases": item["aliases"][:5],
                        "excluded_terms": item["excluded_terms"][:5],
                        "confidence": item["confidence"],
                    }
                    for item in report["candidates"][:5]
                ],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
