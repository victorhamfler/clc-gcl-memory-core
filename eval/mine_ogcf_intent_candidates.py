from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402
from core.ogcf_intent import normalize_ogcf_intent_config, parse_term_sequence  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_intent_candidates_mined.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_intent_candidates_mined_report.md"

BRIDGE_LABELS = {
    "bridge",
    "bridge_relevant",
    "cross_domain_bridge",
    "cross_domain_synthesis",
    "ogcf_bridge",
    "selector_bridge",
}
GEOMETRY_LABELS = {
    "geometry_relevant",
    "ogcf",
    "ogcf_geometry",
    "bridge_geometry",
    "embedding_geometry",
    "loop_overload",
}
MAINTENANCE_LABELS = {
    "memory_maintenance",
    "maintenance",
    "dedup",
    "duplicate",
    "stale_cluster",
    "bridge_maintenance",
}
ORDINARY_SUPPRESSION_LABELS = {
    "ogcf_false_positive",
    "bridge_irrelevant",
    "ordinary_fact",
    "ordinary_lookup",
    "unrelated_bridge",
    "no_ogcf_pressure",
}
STOP_TERMS = {
    "about",
    "after",
    "also",
    "across",
    "audit",
    "before",
    "between",
    "bridge",
    "canonical",
    "check",
    "checks",
    "connect",
    "connects",
    "could",
    "defect",
    "defects",
    "deployment",
    "does",
    "domain",
    "domains",
    "evidence",
    "from",
    "have",
    "heavy",
    "hermes",
    "important",
    "joins",
    "local",
    "memo",
    "memories",
    "meeting",
    "memory",
    "note",
    "notes",
    "policy",
    "pressure",
    "project",
    "radar",
    "reveal",
    "reveals",
    "refresh",
    "review",
    "reviewed",
    "risk",
    "selector",
    "should",
    "story",
    "stress",
    "support",
    "that",
    "the",
    "this",
    "vector",
    "victor",
    "weather",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "uncertainty",
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


def feedback_request(event: dict[str, Any]) -> dict[str, Any]:
    request = payload(event).get("request")
    return request if isinstance(request, dict) else {}


def event_query(event: dict[str, Any]) -> str:
    request = payload(event).get("request")
    if isinstance(request, dict) and request.get("query"):
        return str(request.get("query"))
    return ""


def response_rows(event: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload(event).get("response")
    if not isinstance(response, dict):
        return []
    rows = response.get("raw_results") or response.get("results") or response.get("evidence") or []
    return [row for row in rows if isinstance(row, dict)]


def candidate_terms(text: str, *, max_terms: int = 8) -> list[str]:
    out = []
    seen = set()
    for token in lexical_tokens(text):
        if token not in seen:
            seen.add(token)
            out.append(token)
    lowered = " ".join(str(text or "").lower().split())
    for phrase in (
        "cross domain",
        "cross-domain",
        "selector refresh",
        "refresh policy",
        "bridge overload",
        "embedding geometry",
        "memory routing",
    ):
        if phrase in lowered and phrase not in seen:
            seen.add(phrase)
            out.append(phrase)
    return out[:max_terms]


def lexical_tokens(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return [token for token in cleaned.split() if usable_term(token)]


def usable_term(term: str) -> bool:
    term = str(term or "").strip().lower()
    return len(term) >= 4 and term not in STOP_TERMS and not any(ch.isdigit() for ch in term)


def existing_terms(config: dict[str, Any]) -> dict[str, set[str]]:
    normalized = normalize_ogcf_intent_config(config.get("ogcf_intent") or {})
    return {
        "bridge_terms": set(parse_term_sequence(normalized.get("bridge_terms"))),
        "geometry_terms": set(parse_term_sequence(normalized.get("geometry_terms"))),
        "maintenance_terms": set(parse_term_sequence(normalized.get("maintenance_terms"))),
        "ordinary_fact_terms": set(parse_term_sequence(normalized.get("ordinary_fact_terms"))),
    }


def example_row(query: str, row: dict[str, Any] | None, feedback: dict[str, Any]) -> dict[str, Any]:
    request = feedback_request(feedback)
    return {
        "query": query,
        "memory_id": (row or {}).get("memory_id"),
        "source": (row or {}).get("source"),
        "text": (row or {}).get("text"),
        "label": request.get("label"),
        "rating": request.get("rating"),
        "linked_operation_id": feedback.get("linked_operation_id") or request.get("linked_operation_id"),
    }


def add_counter(
    counter: Counter[str],
    examples: dict[str, list[dict[str, Any]]],
    family: str,
    terms: list[str],
    existing: set[str],
    example: dict[str, Any],
) -> None:
    for term in terms:
        if term in existing:
            continue
        counter[term] += 1
        key = f"{family}:{term}"
        if len(examples[key]) < 5:
            examples[key].append(example)


def build_report(log_path: Path, *, min_support: int = 1) -> dict[str, Any]:
    config = load_config(ROOT)
    known = existing_terms(config)

    asks: dict[str, dict[str, Any]] = {}
    feedback_events = []
    for event in read_jsonl(log_path):
        event_type = str(event.get("event_type") or "").lower()
        if event_type == "ask":
            asks[str(event.get("operation_id") or "")] = event
        elif event_type == "feedback":
            feedback_events.append(event)

    bridge_terms: Counter[str] = Counter()
    geometry_terms: Counter[str] = Counter()
    maintenance_terms: Counter[str] = Counter()
    ordinary_fact_terms: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for feedback in feedback_events:
        request = feedback_request(feedback)
        label = str(request.get("label") or "").strip().lower()
        try:
            rating = float(request.get("rating") or 0.0)
        except (TypeError, ValueError):
            rating = 0.0
        linked = str(feedback.get("linked_operation_id") or request.get("linked_operation_id") or "")
        ask = asks.get(linked)
        if not ask:
            continue
        memory_id = str(request.get("memory_id") or "")
        row = next((item for item in response_rows(ask) if str(item.get("memory_id") or "") == memory_id), None)
        query = str(request.get("query") or event_query(ask))
        row_text = str((row or {}).get("text") or "")
        example = example_row(query, row, feedback)

        query_terms = candidate_terms(query)
        evidence_terms = candidate_terms(f"{query} {row_text}", max_terms=12)
        if rating > 0.0 and label in BRIDGE_LABELS:
            add_counter(bridge_terms, examples, "bridge_terms", evidence_terms, known["bridge_terms"], example)
        if rating > 0.0 and label in GEOMETRY_LABELS:
            add_counter(geometry_terms, examples, "geometry_terms", evidence_terms, known["geometry_terms"], example)
        if rating > 0.0 and label in MAINTENANCE_LABELS:
            add_counter(
                maintenance_terms,
                examples,
                "maintenance_terms",
                evidence_terms,
                known["maintenance_terms"],
                example,
            )
        if label in ORDINARY_SUPPRESSION_LABELS or (rating < 0.0 and "ogcf" in label):
            add_counter(
                ordinary_fact_terms,
                examples,
                "ordinary_fact_terms",
                query_terms,
                known["ordinary_fact_terms"],
                example,
            )

    candidates = []
    for family, counter, notes in (
        ("bridge_terms", bridge_terms, "Mined from positive bridge/cross-domain OGCF feedback."),
        ("geometry_terms", geometry_terms, "Mined from positive OGCF geometry feedback."),
        ("maintenance_terms", maintenance_terms, "Mined from positive memory-maintenance feedback."),
        ("ordinary_fact_terms", ordinary_fact_terms, "Mined from OGCF false-positive or ordinary-lookup feedback."),
    ):
        terms = sorted(term for term, count in counter.items() if count >= min_support)
        if terms:
            candidates.append(
                {
                    "id": f"mined_ogcf_intent_{family}",
                    "section": family,
                    "terms": terms,
                    "support": sum(counter.values()),
                    "notes": notes,
                }
            )

    return {
        "schema": "ogcf_intent_candidates/v1",
        "description": "Mined OGCF intent-controller candidates from linked memory outcome feedback.",
        "source_log": str(log_path),
        "min_support": min_support,
        "ask_event_count": len(asks),
        "feedback_event_count": len(feedback_events),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "support": {
            "bridge_terms": dict(sorted(bridge_terms.items())),
            "geometry_terms": dict(sorted(geometry_terms.items())),
            "maintenance_terms": dict(sorted(maintenance_terms.items())),
            "ordinary_fact_terms": dict(sorted(ordinary_fact_terms.items())),
        },
        "examples": {key: value[:5] for key, value in sorted(examples.items())},
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Mined OGCF Intent Candidates",
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
        lines.append("No OGCF intent candidates mined.")
    for candidate in report["candidates"]:
        lines.extend(
            [
                f"### {candidate['id']}",
                "",
                f"- Section: `{candidate['section']}`",
                f"- Support: `{candidate.get('support')}`",
                f"- Terms: `{', '.join(candidate.get('terms') or [])}`",
                f"- Notes: {candidate.get('notes')}",
                "",
            ]
        )
    lines.extend(["## Support", "", "```json", json.dumps(report["support"], indent=2), "```", ""])
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine OGCF intent candidate artifacts from outcome logs.")
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
