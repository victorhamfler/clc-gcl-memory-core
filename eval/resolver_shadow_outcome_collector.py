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

from core.answer_behavior_shadow import resolver_shadow_actions


DEFAULT_LOGS = [
    REPO_ROOT / "experiments" / "answer_behavior_ogcf_bridge_worklog.jsonl",
    REPO_ROOT / "agent_logs_collection" / "neural_symbolic_outcome_holdout_workflow.jsonl",
    REPO_ROOT / "agent_logs_collection" / "answer_behavior_real_log_missing_cases.jsonl",
]
OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_outcome_dataset_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_outcome_dataset_report.md"


SUPPORTED = {"answer_correct", "answer_good_citation"}
BRIDGE_USEFUL = {"answer_bridge_warning_useful"}
BRIDGE_NOISE = {"answer_bridge_warning_noise"}
MISSING_SUPPORT = {"answer_missing_support", "answer_overconfident"}
STALE = {"answer_stale", "answer_conflict_not_disclosed"}
CITATION_SCOPE = {"answer_bad_citation", "answer_wrong_scope"}
ANSWER_LABELS = SUPPORTED | BRIDGE_USEFUL | BRIDGE_NOISE | MISSING_SUPPORT | STALE | CITATION_SCOPE


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


def feedback(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "feedback")


def selector_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    adaptive = adaptive_memory_context(event)
    snapshot = adaptive.get("selector_snapshot")
    if isinstance(snapshot, dict):
        return snapshot
    return nested(payload(event), "selector_snapshot")


def adaptive_memory_context(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "adaptive_memory_context")


def diagnostics(event: dict[str, Any]) -> dict[str, Any]:
    adaptive = adaptive_memory_context(event)
    diag = adaptive.get("diagnostics")
    if isinstance(diag, dict):
        return diag
    return nested(selector_snapshot(event), "diagnostics")


def label(event: dict[str, Any]) -> str:
    return str(request(event).get("label") or feedback(event).get("label") or "").strip().lower()


def feedback_scope(event: dict[str, Any]) -> str:
    return str(request(event).get("feedback_scope") or feedback(event).get("feedback_scope") or "").strip().lower()


def linked_id(event: dict[str, Any]) -> str:
    return str(event.get("linked_operation_id") or request(event).get("linked_operation_id") or "").strip()


def context_source(event: dict[str, Any]) -> str:
    adaptive = adaptive_memory_context(event)
    if adaptive.get("schema") == "adaptive_memory_context/v1":
        return "adaptive_memory_context"
    if selector_snapshot(event):
        return "selector_snapshot"
    return "none"


def selected_memory_ids(event: dict[str, Any], ask_event: dict[str, Any]) -> list[str]:
    values = request(event).get("selected_memory_ids")
    if values is None:
        values = feedback(event).get("selected_memory_ids")
    if isinstance(values, list):
        return [str(value) for value in values if str(value or "").strip()]
    return [str(row.get("memory_id")) for row in response(ask_event).get("evidence") or [] if isinstance(row, dict) and row.get("memory_id")]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def label_family(label_value: str) -> str:
    if label_value in BRIDGE_USEFUL | BRIDGE_NOISE:
        return "bridge_warning_quality"
    if label_value in MISSING_SUPPORT:
        return "missing_support_refusal"
    if label_value in STALE:
        return "stale_conflict_disclosure"
    if label_value in {"answer_bad_citation", "answer_good_citation"}:
        return "citation_quality"
    if label_value == "answer_wrong_scope":
        return "scope_control"
    return "answer_quality"


def expected_actions(label_value: str, shadow: dict[str, Any]) -> tuple[set[str], set[str]]:
    expected: set[str] = set()
    forbidden: set[str] = set()
    if label_value in SUPPORTED | CITATION_SCOPE:
        expected.add("require_evidence_backed_answer")
    if label_value in BRIDGE_USEFUL:
        expected.add("require_evidence_backed_answer")
        expected.add("emit_ogcf_bridge_warning")
    if label_value in BRIDGE_NOISE:
        forbidden.add("emit_ogcf_bridge_warning")
    if label_value in MISSING_SUPPORT:
        expected.add("preserve_missing_support_refusal")
        forbidden.add("emit_ogcf_bridge_warning")
    if label_value in STALE or shadow.get("diagnostics", {}).get("stale_conflict"):
        expected.add("disclose_stale_conflict")
    return expected, forbidden


def outcome_bucket(label_value: str, actual_actions: set[str], expected: set[str], forbidden: set[str]) -> str:
    missing = expected - actual_actions
    forbidden_hits = forbidden & actual_actions
    if forbidden_hits:
        if "emit_ogcf_bridge_warning" in forbidden_hits:
            return "bridge_warning_false_positive"
        return "forbidden_action_hit"
    if missing:
        if "emit_ogcf_bridge_warning" in missing:
            return "bridge_warning_false_negative"
        if "preserve_missing_support_refusal" in missing:
            return "missing_support_false_negative"
        if "disclose_stale_conflict" in missing:
            return "stale_disclosure_false_negative"
        return "expected_action_missing"
    if label_value in BRIDGE_USEFUL:
        return "bridge_warning_true_positive"
    if label_value in BRIDGE_NOISE:
        return "bridge_warning_true_negative"
    if label_value in MISSING_SUPPORT:
        return "missing_support_correct"
    if label_value in STALE:
        return "stale_disclosure_correct"
    return "supported_answer_correct"


def build_example(
    *,
    log_path: Path,
    feedback_event: dict[str, Any],
    ask_event: dict[str, Any],
    score_threshold: float,
    effective_threshold: float,
) -> dict[str, Any]:
    label_value = label(feedback_event)
    ask_response = response(ask_event)
    shadow = resolver_shadow_actions(
        query=str(request(ask_event).get("query") or ""),
        answer=str(ask_response.get("answer") or ""),
        evidence=ask_response.get("evidence") or [],
        stale_context=ask_response.get("stale_context") or [],
        selector_snapshot=selector_snapshot(ask_event),
        conflict=bool(ask_response.get("conflict")),
        config={
            "enabled": True,
            "bridge_warning_score_threshold": score_threshold,
            "bridge_warning_effective_ratio_threshold": effective_threshold,
        },
    )
    expected, forbidden = expected_actions(label_value, shadow)
    actual = set(shadow.get("actions") or [])
    diag = diagnostics(ask_event)
    shadow_diag = shadow.get("diagnostics") if isinstance(shadow.get("diagnostics"), dict) else {}
    selected_ids = selected_memory_ids(feedback_event, ask_event)
    return {
        "id": f"resolver_shadow_outcome_{feedback_event.get('operation_id')}",
        "source_log": str(log_path),
        "feedback_operation_id": feedback_event.get("operation_id"),
        "linked_operation_id": linked_id(feedback_event),
        "context_source": context_source(ask_event),
        "query": request(ask_event).get("query"),
        "answer_preview": str(ask_response.get("answer") or "")[:300],
        "label": label_value,
        "family": label_family(label_value),
        "rating": _float(request(feedback_event).get("rating", feedback(feedback_event).get("rating")), 0.0),
        "selected_memory_ids": selected_ids,
        "selected_evidence_count": int(shadow_diag.get("selected_evidence_count") or len(selected_ids)),
        "stale_context_count": int(shadow_diag.get("stale_context_count") or len(ask_response.get("stale_context") or [])),
        "ogcf_meta_present": bool(selector_snapshot(ask_event).get("ogcf_meta_present")),
        "ogcf_bridge_overload_score": _float(diag.get("ogcf_bridge_overload_score"), 0.0),
        "ogcf_effective_affected_memory_ratio": _float(diag.get("ogcf_effective_affected_memory_ratio"), 0.0),
        "ogcf_intent": diag.get("ogcf_intent"),
        "ordinary_fact_lookup": bool(shadow_diag.get("ordinary_fact_lookup")),
        "stale_conflict": bool(shadow_diag.get("stale_conflict")),
        "shadow_actions": sorted(actual),
        "expected_actions": sorted(expected),
        "forbidden_actions": sorted(forbidden),
        "missing_expected": sorted(expected - actual),
        "forbidden_hits": sorted(forbidden & actual),
        "outcome_bucket": outcome_bucket(label_value, actual, expected, forbidden),
        "passed": not (expected - actual) and not (forbidden & actual) and shadow.get("mutates_answer") is False,
        "shadow_mutates_answer": shadow.get("mutates_answer"),
        "shadow_mutates_config": shadow.get("mutates_config"),
    }


def collect_dataset(log_paths: list[Path], score_threshold: float, effective_threshold: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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
            label_value = label(event)
            if feedback_scope(event) != "answer" and not label_value.startswith("answer_"):
                continue
            if label_value not in ANSWER_LABELS:
                skipped.append({"source_log": str(log_path), "operation_id": event.get("operation_id"), "label": label_value, "reason": "unsupported_answer_label"})
                continue
            ask = asks.get(linked_id(event))
            if not ask:
                skipped.append({"source_log": str(log_path), "operation_id": event.get("operation_id"), "label": label_value, "reason": "missing_linked_ask"})
                continue
            example = build_example(
                log_path=log_path,
                feedback_event=event,
                ask_event=ask,
                score_threshold=score_threshold,
                effective_threshold=effective_threshold,
            )
            examples.append(example)
            context_counts[str(example.get("context_source") or "none")] += 1
            added += 1
        sources.append(
            {
                "path": str(log_path),
                "exists": log_path.exists(),
                "event_count": len(rows),
                "event_type_counts": dict(sorted(source_counts.items())),
                "context_source_counts": dict(sorted(context_counts.items())),
                "answer_examples_added": added,
            }
        )
    return examples, skipped, sources


def build_report(
    log_paths: list[Path],
    *,
    score_threshold: float,
    effective_threshold: float,
) -> dict[str, Any]:
    examples, skipped, sources = collect_dataset(log_paths, score_threshold, effective_threshold)
    label_counts = Counter(item["label"] for item in examples)
    family_counts = Counter(item["family"] for item in examples)
    outcome_counts = Counter(item["outcome_bucket"] for item in examples)
    action_counts = Counter(action for item in examples for action in item["shadow_actions"])
    checks = {
        "has_examples": bool(examples),
        "all_examples_pass": bool(examples) and all(item["passed"] for item in examples),
        "all_report_only": all(item["shadow_mutates_answer"] is False and item["shadow_mutates_config"] is False for item in examples),
        "has_bridge_positive": any(item["label"] in BRIDGE_USEFUL for item in examples),
        "has_bridge_negative": any(item["label"] in BRIDGE_NOISE for item in examples),
        "has_missing_support": any(item["label"] in MISSING_SUPPORT for item in examples),
        "has_supported_answer": any(item["label"] in SUPPORTED for item in examples),
    }
    return {
        "schema": "resolver_shadow_outcome_dataset/v1",
        "description": "Report-only collected resolver-shadow answer outcomes for calibration and future controller learning.",
        "ok": all(checks.values()),
        "thresholds": {
            "bridge_warning_score_threshold": score_threshold,
            "bridge_warning_effective_ratio_threshold": effective_threshold,
        },
        "source_logs": sources,
        "example_count": len(examples),
        "skipped_count": len(skipped),
        "checks": checks,
        "label_counts": dict(sorted(label_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "examples": examples,
        "skipped": skipped[:100],
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Outcome Dataset",
        "",
        "This collector is advisory only. It does not modify resolver behavior, runtime config, or memory rows.",
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
    lines.extend(["", "## Counts", "", "```json", json.dumps({
        "labels": report.get("label_counts"),
        "families": report.get("family_counts"),
        "outcomes": report.get("outcome_counts"),
        "actions": report.get("action_counts"),
    }, indent=2), "```"])
    lines.extend(["", "## Examples", "", "| label | outcome | pass | actions | query |", "| --- | --- | --- | --- | --- |"])
    for item in report.get("examples") or []:
        query = str(item.get("query") or "").replace("|", "\\|")
        lines.append(
            f"| `{item['label']}` | `{item['outcome_bucket']}` | `{item['passed']}` | "
            f"`{', '.join(item.get('shadow_actions') or [])}` | {query[:140]} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect resolver-shadow answer outcomes from linked ask/feedback logs.")
    parser.add_argument("--log", action="append", default=None)
    parser.add_argument("--bridge-score-threshold", type=float, default=0.70)
    parser.add_argument("--bridge-effective-threshold", type=float, default=0.50)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    log_paths = parse_paths(args.log) or [path for path in DEFAULT_LOGS if path.exists()]
    report = build_report(
        log_paths,
        score_threshold=float(args.bridge_score_threshold),
        effective_threshold=float(args.bridge_effective_threshold),
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "example_count": report["example_count"],
                "skipped_count": report["skipped_count"],
                "label_counts": report["label_counts"],
                "outcome_counts": report["outcome_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
