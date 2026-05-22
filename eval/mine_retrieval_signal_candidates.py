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
from core.retrieval_signals import normalize_retrieval_signal_config, parse_term_sequence, tokens  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "retrieval_signal_candidates_mined.json"
OUT_MD = REPO_ROOT / "experiments" / "retrieval_signal_candidates_mined_report.md"
NEGATIVE_LABELS = {"wrong_domain", "stale", "irrelevant", "bad_source", "incorrect", "not_useful"}
STOP_TERMS = {
    "about",
    "after",
    "before",
    "can",
    "could",
    "does",
    "follow",
    "for",
    "from",
    "happen",
    "hermes",
    "how",
    "is",
    "me",
    "need",
    "repository",
    "rule",
    "should",
    "the",
    "this",
    "victor",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
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


def source_stem(source: str) -> str:
    return Path(str(source or "").replace("\\", "/")).stem.lower()


def starts_broad_note(text: str) -> str | None:
    lowered = str(text or "").strip().lower()
    match = re.match(r"^([a-z][a-z0-9 _-]{2,40} note):", lowered)
    return match.group(1).strip() if match else None


def negative_marker(text: str) -> str | None:
    lowered = str(text or "").strip().lower()
    patterns = [
        r"\bnot [a-z0-9_-]+ approval\b",
        r"\bnot [a-z0-9_-]+ permission\b",
        r"\bnot authorized\b",
        r"\bnot permission\b",
        r"\bdo not authorize\b",
        r"\bdoes not authorize\b",
        r"\bseparate [a-z0-9_-]+ policy\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0).strip()
    return None


def query_candidate_terms(query: str) -> list[str]:
    out = []
    for term in tokens(query):
        if len(term) < 4 or term in STOP_TERMS:
            continue
        if any(ch.isdigit() for ch in term):
            continue
        out.append(term)
    return out[:6]


def covered_by_existing_source_marker(stem: str, existing_source_markers: set[str]) -> bool:
    stem_l = str(stem or "").lower()
    return any(marker and marker in stem_l for marker in existing_source_markers)


def covered_by_existing_prefix(prefix: str, existing_prefixes: set[str]) -> bool:
    prefix_l = str(prefix or "").lower()
    return any(marker and prefix_l.startswith(marker) for marker in existing_prefixes)


def build_report(log_path: Path, *, min_support: int = 1) -> dict[str, Any]:
    config = load_config(ROOT)
    current = normalize_retrieval_signal_config(config.get("retrieval_signals") or {})
    existing_source_markers = set(current["broad_generic"]["source_contains"])
    existing_prefixes = set(current["broad_generic"]["text_prefixes"])
    existing_query_terms = set(current["scope_deflection"]["query_terms"])
    existing_text_markers = set(current["scope_deflection"]["text_markers"])

    asks: dict[str, dict[str, Any]] = {}
    feedback_events = []
    for event in read_jsonl(log_path):
        event_type = str(event.get("event_type") or "").lower()
        if event_type == "ask":
            asks[str(event.get("operation_id") or "")] = event
        elif event_type == "feedback":
            feedback_events.append(event)

    broad_sources: Counter[str] = Counter()
    broad_prefixes: Counter[str] = Counter()
    scope_query_terms: Counter[str] = Counter()
    scope_markers: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for feedback in feedback_events:
        request = feedback_request(feedback)
        label = str(request.get("label") or "").lower()
        rating = float(request.get("rating") or 0.0)
        if label not in NEGATIVE_LABELS and rating >= 0.0:
            continue
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
        source = str(row.get("source") or "")
        stem = source_stem(source)
        prefix = starts_broad_note(text)
        marker = negative_marker(text)

        if prefix and not covered_by_existing_prefix(prefix, existing_prefixes):
            broad_prefixes[prefix] += 1
            examples[f"broad_prefix:{prefix}"].append(example_row(query, row, feedback))
        if (
            ("note" in stem or "ops" in stem or "control" in stem)
            and stem
            and not covered_by_existing_source_marker(stem, existing_source_markers)
        ):
            broad_sources[stem] += 1
            examples[f"broad_source:{stem}"].append(example_row(query, row, feedback))
        if marker and marker not in existing_text_markers:
            scope_markers[marker] += 1
            examples[f"scope_marker:{marker}"].append(example_row(query, row, feedback))
            for term in query_candidate_terms(query):
                if term not in existing_query_terms:
                    scope_query_terms[term] += 1
                    examples[f"scope_query:{term}"].append(example_row(query, row, feedback))

    candidates = []
    broad_source_terms = sorted(term for term, count in broad_sources.items() if count >= min_support)
    broad_prefix_terms = sorted(term for term, count in broad_prefixes.items() if count >= min_support)
    if broad_source_terms or broad_prefix_terms:
        candidates.append(
            {
                "id": "mined_broad_generic_markers",
                "section": "broad_generic",
                "source_contains": broad_source_terms,
                "text_prefixes": broad_prefix_terms,
                "support": sum(broad_sources.values()) + sum(broad_prefixes.values()),
                "notes": "Mined from negatively labeled broad/generic note retrieval rows.",
            }
        )
    scope_query_terms_out = sorted(term for term, count in scope_query_terms.items() if count >= min_support)
    scope_markers_out = sorted(term for term, count in scope_markers.items() if count >= min_support)
    if scope_query_terms_out or scope_markers_out:
        candidates.append(
            {
                "id": "mined_scope_deflection_markers",
                "section": "scope_deflection",
                "query_terms": scope_query_terms_out,
                "text_markers": scope_markers_out,
                "support": sum(scope_query_terms.values()) + sum(scope_markers.values()),
                "notes": "Mined from negative correction rows that explicitly deflect permission/approval scope.",
            }
        )

    return {
        "schema": "retrieval_signal_candidates/v1",
        "description": "Mined retrieval-signal candidates from memory outcome feedback.",
        "source_log": str(log_path),
        "min_support": min_support,
        "ask_event_count": len(asks),
        "feedback_event_count": len(feedback_events),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "support": {
            "broad_sources": dict(sorted(broad_sources.items())),
            "broad_prefixes": dict(sorted(broad_prefixes.items())),
            "scope_query_terms": dict(sorted(scope_query_terms.items())),
            "scope_markers": dict(sorted(scope_markers.items())),
        },
        "examples": {key: value[:5] for key, value in sorted(examples.items())},
    }


def example_row(query: str, row: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    request = feedback_request(feedback)
    return {
        "query": query,
        "memory_id": row.get("memory_id"),
        "source": row.get("source"),
        "text": row.get("text"),
        "label": request.get("label"),
        "rating": request.get("rating"),
        "linked_operation_id": feedback.get("linked_operation_id"),
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Mined Retrieval Signal Candidates",
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
        for key in ("source_contains", "text_prefixes", "query_terms", "text_markers"):
            if candidate.get(key):
                lines.append(f"- {key}: `{', '.join(candidate[key])}`")
        lines.append("")
    lines.extend(["## Support", "", "```json", json.dumps(report["support"], indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine retrieval-signal candidate artifacts from outcome logs.")
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
