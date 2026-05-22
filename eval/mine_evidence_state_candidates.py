from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402
from core.evidence_states import classify_memory_state, normalize_evidence_state_config, parse_term_sequence  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "evidence_state_candidates_mined.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_state_candidates_mined_report.md"
STALE_LABELS = {"stale", "old", "obsolete", "superseded", "incorrect_stale"}
CURRENT_LABELS = {"current", "should_be_current", "fresh", "corrected_current"}
SENSITIVE_LABELS = {"sensitive", "sensitive_lookup", "needs_exact_evidence", "private_lookup"}
STOP_TERMS = {
    "about",
    "channel",
    "could",
    "current",
    "deployment",
    "does",
    "evidence",
    "general",
    "have",
    "has",
    "had",
    "hermes",
    "must",
    "memory",
    "need",
    "needs",
    "private",
    "rule",
    "should",
    "the",
    "this",
    "value",
    "victor",
    "what",
    "will",
    "where",
    "which",
    "would",
}


def default_log_path() -> Path:
    config = load_config(ROOT)
    cfg = config.get("outcome_log") if isinstance(config.get("outcome_log"), dict) else {}
    return resolve_project_path(ROOT, cfg.get("path"), "logs/memory_outcomes.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, dict) else {}


def response_rows(event: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload(event).get("response")
    if not isinstance(response, dict):
        return []
    rows = response.get("raw_results") or response.get("results") or response.get("evidence") or []
    return [row for row in rows if isinstance(row, dict)]


def feedback_request(event: dict[str, Any]) -> dict[str, Any]:
    request = payload(event).get("request")
    return request if isinstance(request, dict) else {}


def event_query(event: dict[str, Any]) -> str:
    request = payload(event).get("request")
    if isinstance(request, dict) and request.get("query"):
        return str(request.get("query"))
    return ""


def stale_phrase(text: str) -> str | None:
    lowered = str(text or "").strip().lower()
    patterns = [
        r"\bretired truth\b",
        r"\bobsolete (?:truth|memory|policy|rule)\b",
        r"\bdeprecated (?:truth|memory|policy|rule)\b",
        r"\barchived (?:truth|memory|policy|rule)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0).strip()
    return None


def correction_prefix(text: str) -> str | None:
    lowered = str(text or "").strip().lower()
    match = re.match(r"^([a-z][a-z0-9 _-]{2,30}:)", lowered)
    if not match:
        return None
    prefix = match.group(1).strip()
    if prefix in {"note:", "memo:", "summary:"}:
        return None
    return prefix


def query_terms(query: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(query or ""))
    out = []
    for term in cleaned.split():
        if len(term) < 4 or term in STOP_TERMS:
            continue
        if any(ch.isdigit() for ch in term):
            continue
        out.append(term)
    return out[:6]


def example_row(query: str, row: dict[str, Any], feedback: dict[str, Any], observed_state: str) -> dict[str, Any]:
    request = feedback_request(feedback)
    return {
        "query": query,
        "memory_id": row.get("memory_id"),
        "source": row.get("source"),
        "text": row.get("text"),
        "observed_state": observed_state,
        "label": request.get("label"),
        "rating": request.get("rating"),
        "linked_operation_id": feedback.get("linked_operation_id"),
    }


def build_report(log_path: Path, *, min_support: int = 1) -> dict[str, Any]:
    config = load_config(ROOT)
    current = normalize_evidence_state_config(config.get("evidence_states") or {})
    existing_stale_terms = set(parse_term_sequence(current.get("stale_language_terms")))
    existing_correction_terms = set(parse_term_sequence(current.get("correction_language_terms")))
    existing_sensitive_terms = set(parse_term_sequence(current.get("sensitive_lookup_terms")))

    asks: dict[str, dict[str, Any]] = {}
    feedback_events = []
    for event in read_jsonl(log_path):
        event_type = str(event.get("event_type") or "").lower()
        if event_type == "ask":
            asks[str(event.get("operation_id") or "")] = event
        elif event_type == "feedback":
            feedback_events.append(event)

    stale_terms: Counter[str] = Counter()
    correction_terms: Counter[str] = Counter()
    sensitive_terms: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for feedback in feedback_events:
        request = feedback_request(feedback)
        label = str(request.get("label") or "").lower()
        linked = str(feedback.get("linked_operation_id") or request.get("linked_operation_id") or "")
        ask = asks.get(linked)
        if not ask:
            continue
        memory_id = str(request.get("memory_id") or "")
        row = next((item for item in response_rows(ask) if str(item.get("memory_id") or "") == memory_id), None)
        if not row:
            continue
        query = str(request.get("query") or event_query(ask))
        text = str(row.get("text") or "")
        observed_state = classify_memory_state(row, current)

        if label in STALE_LABELS and observed_state != "stale":
            phrase = stale_phrase(text)
            if phrase and phrase not in existing_stale_terms:
                stale_terms[phrase] += 1
                examples[f"stale_language:{phrase}"].append(example_row(query, row, feedback, observed_state))

        if label in CURRENT_LABELS and observed_state != "current":
            prefix = correction_prefix(text)
            if prefix and prefix not in existing_correction_terms:
                correction_terms[prefix] += 1
                examples[f"correction_language:{prefix}"].append(example_row(query, row, feedback, observed_state))

        if label in SENSITIVE_LABELS:
            for term in query_terms(query):
                if term not in existing_sensitive_terms:
                    sensitive_terms[term] += 1
                    examples[f"sensitive_lookup:{term}"].append(example_row(query, row, feedback, observed_state))

    candidates = []
    stale_out = sorted(term for term, count in stale_terms.items() if count >= min_support)
    if stale_out:
        candidates.append(
            {
                "id": "mined_stale_language_terms",
                "section": "stale_language",
                "terms": stale_out,
                "support": sum(stale_terms.values()),
                "notes": "Mined from rows labeled stale but classified as non-stale.",
            }
        )
    correction_out = sorted(term for term, count in correction_terms.items() if count >= min_support)
    if correction_out:
        candidates.append(
            {
                "id": "mined_correction_language_terms",
                "section": "correction_language",
                "terms": correction_out,
                "support": sum(correction_terms.values()),
                "notes": "Mined from rows labeled current/corrected but classified as non-current.",
            }
        )
    sensitive_out = sorted(term for term, count in sensitive_terms.items() if count >= min_support)
    if sensitive_out:
        candidates.append(
            {
                "id": "mined_sensitive_lookup_terms",
                "section": "sensitive_lookup",
                "terms": sensitive_out,
                "support": sum(sensitive_terms.values()),
                "notes": "Mined from sensitive lookup feedback labels.",
            }
        )

    return {
        "schema": "evidence_state_candidates/v1",
        "description": "Mined evidence-state candidates from memory outcome feedback.",
        "source_log": str(log_path),
        "min_support": min_support,
        "ask_event_count": len(asks),
        "feedback_event_count": len(feedback_events),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "support": {
            "stale_language": dict(sorted(stale_terms.items())),
            "correction_language": dict(sorted(correction_terms.items())),
            "sensitive_lookup": dict(sorted(sensitive_terms.items())),
        },
        "examples": {key: value[:5] for key, value in sorted(examples.items())},
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Mined Evidence State Candidates",
        "",
        f"Source log: `{report['source_log']}`",
        f"Candidate count: **{report['candidate_count']}**",
        f"Ask events: `{report['ask_event_count']}`",
        f"Feedback events: `{report['feedback_event_count']}`",
        f"Minimum support: `{report['min_support']}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("No candidates mined.")
    for candidate in report["candidates"]:
        lines.extend(
            [
                f"### {candidate['id']}",
                "",
                f"- Section: `{candidate['section']}`",
                f"- Support: `{candidate.get('support')}`",
                f"- Notes: {candidate.get('notes')}",
            ]
        )
        if candidate.get("terms"):
            lines.append(f"- terms: `{', '.join(candidate['terms'])}`")
        lines.append("")
    lines.extend(["## Support", "", "```json", json.dumps(report["support"], indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine evidence-state candidate artifacts from outcome logs.")
    parser.add_argument("--log", default=str(default_log_path()))
    parser.add_argument("--min-support", type=int, default=1)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.log), min_support=max(1, int(args.min_support)))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "candidate_count": report["candidate_count"],
                "ask_event_count": report["ask_event_count"],
                "feedback_event_count": report["feedback_event_count"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
