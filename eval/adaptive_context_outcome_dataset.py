from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_LOGS = [
    ROOT / "logs" / "memory_outcomes.jsonl",
    REPO_ROOT / "agent_logs_collection" / "neural_symbolic_outcome_holdout_workflow.jsonl",
    REPO_ROOT / "agent_logs_collection" / "answer_behavior_real_log_missing_cases.jsonl",
]
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_outcome_dataset_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_outcome_dataset_report.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append(
                {
                    "event_type": "parse_error",
                    "operation_id": f"parse_error_{line_no}",
                    "payload": {"line_no": line_no, "error": str(exc)},
                }
            )
            continue
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def nested(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return nested(event, "payload")


def request(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "request")


def response(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "response")


def feedback_payload(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "feedback")


def adaptive_context(event: dict[str, Any]) -> dict[str, Any]:
    value = payload(event).get("adaptive_memory_context")
    if isinstance(value, dict) and value.get("schema") == "adaptive_memory_context/v1":
        return value
    snapshot = payload(event).get("selector_snapshot")
    if isinstance(snapshot, dict):
        return {
            "schema": "adaptive_memory_context_legacy_selector_snapshot/v1",
            "ok": bool(snapshot.get("ok", True)),
            "selector_snapshot": snapshot,
            "features": {},
            "diagnostics": nested(snapshot, "diagnostics"),
            "retrieval_context": response(event).get("raw_results") or [],
            "ogcf_meta_present": bool(snapshot.get("ogcf_meta_present")),
        }
    return {}


def linked_operation_id(event: dict[str, Any]) -> str:
    return str(event.get("linked_operation_id") or request(event).get("linked_operation_id") or "").strip()


def feedback_label(event: dict[str, Any]) -> str:
    return str(request(event).get("label") or feedback_payload(event).get("label") or "").strip().lower()


def feedback_scope(event: dict[str, Any]) -> str:
    scope = str(
        request(event).get("feedback_scope")
        or feedback_payload(event).get("feedback_scope")
        or request(event).get("target_type")
        or request(event).get("scope")
        or ""
    ).strip().lower()
    if scope:
        return "answer" if scope in {"answer", "response"} else scope
    return "answer" if feedback_label(event).startswith("answer_") else "memory"


def feedback_rating(event: dict[str, Any]) -> float:
    try:
        return float(request(event).get("rating", feedback_payload(event).get("rating", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def selected_memory_ids(event: dict[str, Any], ask_event: dict[str, Any]) -> list[str]:
    values = request(event).get("selected_memory_ids")
    if values is None:
        values = feedback_payload(event).get("selected_memory_ids")
    if isinstance(values, list):
        return [str(value) for value in values if str(value or "").strip()]
    memory_id = str(request(event).get("memory_id") or feedback_payload(event).get("memory_id") or "").strip()
    if memory_id:
        return [memory_id]
    return [
        str(row.get("memory_id"))
        for row in response(ask_event).get("evidence") or []
        if isinstance(row, dict) and row.get("memory_id")
    ]


def compact_retrieval(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    out = []
    for row in list(rows or [])[:limit]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "memory_id": row.get("memory_id"),
                "rank": row.get("rank"),
                "score": row.get("score"),
                "cosine": row.get("cosine"),
                "text_match_score": row.get("text_match_score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "authority_state": row.get("authority_state") or row.get("memory_state"),
                "canonical_support_count": row.get("canonical_support_count"),
                "canonical_duplicate_count": row.get("canonical_duplicate_count"),
                "canonical_is_keeper": row.get("canonical_is_keeper"),
                "text": row.get("text") or row.get("text_preview"),
            }
        )
    return out


def outcome_family(label: str, scope: str) -> str:
    if scope == "answer":
        if "bridge_warning" in label:
            return "answer_bridge_warning"
        if label in {"answer_missing_support", "answer_overconfident"}:
            return "answer_missing_support"
        if label in {"answer_stale", "answer_conflict_not_disclosed"}:
            return "answer_stale_conflict"
        if label in {"answer_bad_citation", "answer_good_citation"}:
            return "answer_citation"
        return "answer_quality"
    if label in {"stale", "wrong_domain", "missing_source"}:
        return "retrieval_negative"
    if label in {"useful", "good", "excellent"}:
        return "retrieval_positive"
    if label in {"bridge_relevant", "cross_domain_bridge", "ogcf_bridge", "ogcf_geometry", "bridge_geometry"}:
        return "ogcf_positive"
    if label in {"ogcf_false_positive", "bridge_irrelevant", "ordinary_lookup", "no_ogcf_pressure"}:
        return "ogcf_negative"
    return f"{scope or 'unknown'}_feedback"


def build_example(log_path: Path, feedback_event: dict[str, Any], ask_event: dict[str, Any]) -> dict[str, Any]:
    context = adaptive_context(ask_event)
    snapshot = nested(context, "selector_snapshot")
    diagnostics = nested(context, "diagnostics")
    decision = nested(snapshot, "decision")
    scope = feedback_scope(feedback_event)
    label = feedback_label(feedback_event)
    return {
        "id": f"adaptive_context_outcome_{feedback_event.get('operation_id')}",
        "source_log": str(log_path),
        "feedback_operation_id": feedback_event.get("operation_id"),
        "linked_operation_id": linked_operation_id(feedback_event),
        "context_schema": context.get("schema") or "missing",
        "context_source": "adaptive_memory_context" if context.get("schema") == "adaptive_memory_context/v1" else "legacy_selector_snapshot",
        "feedback_scope": scope,
        "label": label,
        "rating": feedback_rating(feedback_event),
        "outcome_family": outcome_family(label, scope),
        "query": request(ask_event).get("query"),
        "answer_preview": str(response(ask_event).get("answer") or "")[:300],
        "selected_memory_ids": selected_memory_ids(feedback_event, ask_event),
        "selector_policy": decision.get("policy"),
        "selector_action": decision.get("action"),
        "selector_reason": decision.get("reason"),
        "features": context.get("features") if isinstance(context.get("features"), dict) else {},
        "diagnostics": {
            key: diagnostics.get(key)
            for key in (
                "memory_bad_rate",
                "probe_drop",
                "csd_ratio",
                "stale_current_conflict",
                "contradiction_peak",
                "canonical_confidence_signal",
                "canonical_duplicate_pressure",
                "ogcf_bridge_overload_score",
                "ogcf_effective_affected_memory_ratio",
                "ogcf_intent",
                "ogcf_intent_score",
            )
            if key in diagnostics
        },
        "ogcf_meta_present": bool(context.get("ogcf_meta_present") or snapshot.get("ogcf_meta_present")),
        "retrieval_context": compact_retrieval(context.get("retrieval_context") or response(ask_event).get("raw_results") or []),
        "resolver_shadow_actions": (payload(ask_event).get("resolver_shadow") or {}).get("actions", []),
    }


def collect_dataset(log_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    examples: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for log_path in log_paths:
        rows = read_jsonl(log_path)
        asks = {
            str(row.get("operation_id")): row
            for row in rows
            if str(row.get("event_type") or "").lower() == "ask" and row.get("operation_id")
        }
        source_counts = Counter(str(row.get("event_type")) for row in rows)
        context_counts: Counter[str] = Counter()
        added = 0
        for event in rows:
            if str(event.get("event_type") or "").lower() != "feedback":
                continue
            linked = linked_operation_id(event)
            if not linked:
                skipped.append({"source_log": str(log_path), "operation_id": event.get("operation_id"), "reason": "feedback_without_link"})
                continue
            ask_event = asks.get(linked)
            if not ask_event:
                skipped.append({"source_log": str(log_path), "operation_id": event.get("operation_id"), "reason": "missing_linked_ask"})
                continue
            context = adaptive_context(ask_event)
            if not context:
                skipped.append({"source_log": str(log_path), "operation_id": event.get("operation_id"), "reason": "missing_context"})
                continue
            example = build_example(log_path, event, ask_event)
            examples.append(example)
            context_counts[example["context_source"]] += 1
            added += 1
        sources.append(
            {
                "path": str(log_path),
                "exists": log_path.exists(),
                "event_count": len(rows),
                "event_type_counts": dict(sorted(source_counts.items())),
                "context_source_counts": dict(sorted(context_counts.items())),
                "examples_added": added,
            }
        )
    return examples, skipped, sources


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def build_report(log_paths: list[Path]) -> dict[str, Any]:
    examples, skipped, sources = collect_dataset(log_paths)
    label_counts = Counter(item["label"] for item in examples)
    family_counts = Counter(item["outcome_family"] for item in examples)
    scope_counts = Counter(item["feedback_scope"] for item in examples)
    context_counts = Counter(item["context_source"] for item in examples)
    checks = {
        "has_examples": bool(examples),
        "has_context_examples": any(item["context_source"] in {"adaptive_memory_context", "legacy_selector_snapshot"} for item in examples),
        "all_examples_linked": all(bool(item.get("linked_operation_id")) for item in examples),
        "all_examples_have_context": all(item.get("context_schema") not in {"", "missing"} for item in examples),
    }
    return {
        "schema": "adaptive_context_outcome_dataset/v1",
        "description": "Joined ask/feedback outcomes using adaptive memory context for selector, resolver, OGCF, and answer-behavior learning.",
        "ok": all(checks.values()),
        "source_logs": sources,
        "example_count": len(examples),
        "skipped_count": len(skipped),
        "checks": checks,
        "label_counts": dict(sorted(label_counts.items())),
        "outcome_family_counts": dict(sorted(family_counts.items())),
        "feedback_scope_counts": dict(sorted(scope_counts.items())),
        "context_source_counts": dict(sorted(context_counts.items())),
        "examples": examples,
        "skipped": skipped[:100],
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Outcome Dataset",
        "",
        "This collector is report-only. It joins linked ask/feedback rows through the adaptive memory context.",
        "",
        f"Passed: **{report['ok']}**",
        f"Examples: `{report['example_count']}`",
        f"Skipped: `{report['skipped_count']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "```json",
            json.dumps(
                {
                    "labels": report.get("label_counts"),
                    "families": report.get("outcome_family_counts"),
                    "scopes": report.get("feedback_scope_counts"),
                    "contexts": report.get("context_source_counts"),
                },
                indent=2,
            ),
            "```",
            "",
            "## Examples",
            "",
            "| scope | label | context | selector action | query |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("examples") or []:
        query = str(item.get("query") or "").replace("|", "\\|")
        lines.append(
            f"| `{item['feedback_scope']}` | `{item['label']}` | `{item['context_source']}` | "
            f"`{item.get('selector_action')}` | {query[:140]} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect linked adaptive-memory-context outcomes from outcome logs.")
    parser.add_argument("--log", action="append", default=None)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    log_paths = parse_paths(args.log) or [path for path in DEFAULT_LOGS if path.exists()]
    report = build_report(log_paths)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "example_count": report["example_count"],
                "skipped_count": report["skipped_count"],
                "context_source_counts": report["context_source_counts"],
                "feedback_scope_counts": report["feedback_scope_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
