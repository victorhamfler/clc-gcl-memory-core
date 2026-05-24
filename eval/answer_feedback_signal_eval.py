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


DEFAULT_LOG = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_workflow.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "answer_feedback_signal_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_feedback_signal_eval_report.md"

POSITIVE_ANSWER_LABELS = {
    "answer_correct",
    "answer_good_citation",
    "answer_bridge_warning_useful",
}
NEGATIVE_ANSWER_LABELS = {
    "answer_stale",
    "answer_wrong_scope",
    "answer_missing_support",
    "answer_overconfident",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_noise",
}
BRIDGE_WARNING_LABELS = {
    "answer_bridge_warning_useful",
    "answer_bridge_warning_noise",
}
MISSING_SUPPORT_LABELS = {
    "answer_missing_support",
    "answer_overconfident",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append(
                {
                    "event_type": "parse_error",
                    "operation_id": f"parse_error_{line_no}",
                    "payload": {"line_no": line_no, "error": str(exc)},
                }
            )
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, dict) else {}


def nested_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def answer_feedback_scope(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    return str(request.get("feedback_scope") or feedback.get("feedback_scope") or "").strip().lower()


def answer_feedback_label(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    return str(request.get("label") or feedback.get("label") or "").strip().lower()


def answer_feedback_rating(event: dict[str, Any]) -> float:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    try:
        return float(request.get("rating", feedback.get("rating", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def linked_operation_id(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    return str(event.get("linked_operation_id") or request.get("linked_operation_id") or "").strip()


def selected_memory_ids(event: dict[str, Any]) -> list[str]:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    values = request.get("selected_memory_ids")
    if values is None:
        values = feedback.get("selected_memory_ids")
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value or "").strip()]


def ask_query(event: dict[str, Any]) -> str:
    request = nested_dict(payload(event), "request")
    return str(request.get("query") or "").strip()


def ask_response(event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(payload(event), "response")


def selector_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(payload(event), "selector_snapshot")


def selected_rows(ask_event: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(ids)
    response = ask_response(ask_event)
    rows = []
    for section in ("evidence", "raw_results", "source_context", "stale_context"):
        for row in response.get(section) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("memory_id") or "") in wanted:
                rows.append(row)
    seen = set()
    unique = []
    for row in rows:
        memory_id = str(row.get("memory_id") or "")
        if memory_id in seen:
            continue
        seen.add(memory_id)
        unique.append(row)
    return unique


def family_for_label(label: str) -> str:
    if label in BRIDGE_WARNING_LABELS:
        return "bridge_warning_quality"
    if label in MISSING_SUPPORT_LABELS:
        return "missing_support_refusal"
    if label in {"answer_stale", "answer_conflict_not_disclosed"}:
        return "stale_conflict_disclosure"
    if label in {"answer_wrong_scope"}:
        return "scope_control"
    if label in {"answer_good_citation", "answer_bad_citation"}:
        return "citation_quality"
    return "answer_quality"


def recommendation_for(label: str, rating: float, ask_event: dict[str, Any] | None) -> str:
    if ask_event is None:
        return "reject_missing_link"
    if label not in POSITIVE_ANSWER_LABELS and label not in NEGATIVE_ANSWER_LABELS:
        return "hold_unknown_label"
    if label in BRIDGE_WARNING_LABELS:
        snapshot = selector_snapshot(ask_event)
        diagnostics = nested_dict(snapshot, "diagnostics")
        if not snapshot.get("ogcf_meta_present") and not any(str(key).startswith("ogcf_") for key in diagnostics):
            return "hold_bridge_without_ogcf"
    if label in MISSING_SUPPORT_LABELS and rating < 0.0:
        return "holdout_ready"
    if rating > 0.0:
        return "holdout_ready"
    if rating < 0.0:
        return "holdout_ready"
    return "hold_neutral"


def signal_from_feedback(feedback_event: dict[str, Any], ask_event: dict[str, Any] | None) -> dict[str, Any]:
    label = answer_feedback_label(feedback_event)
    rating = answer_feedback_rating(feedback_event)
    memory_ids = selected_memory_ids(feedback_event)
    diagnostics = nested_dict(selector_snapshot(ask_event or {}), "diagnostics") if ask_event else {}
    response = ask_response(ask_event or {}) if ask_event else {}
    return {
        "id": f"answer_signal_{feedback_event.get('operation_id')}",
        "family": family_for_label(label),
        "label": label,
        "rating": rating,
        "recommendation": recommendation_for(label, rating, ask_event),
        "feedback_operation_id": feedback_event.get("operation_id"),
        "linked_operation_id": linked_operation_id(feedback_event) or None,
        "query": ask_query(ask_event or {}),
        "answer_preview": str(response.get("answer") or "")[:500],
        "selected_memory_ids": memory_ids,
        "selected_rows": selected_rows(ask_event or {}, memory_ids),
        "selector_policy": nested_dict(selector_snapshot(ask_event or {}), "decision").get("policy"),
        "selector_action": nested_dict(selector_snapshot(ask_event or {}), "decision").get("action"),
        "ogcf_meta_present": bool((selector_snapshot(ask_event or {}) or {}).get("ogcf_meta_present")),
        "ogcf_diagnostics": {
            key: value for key, value in sorted(diagnostics.items()) if str(key).startswith("ogcf_")
        },
        "diagnostic_summary": {
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
    }


def build_report(log_path: Path) -> dict[str, Any]:
    events = read_jsonl(log_path)
    by_operation = {str(event.get("operation_id")): event for event in events if event.get("operation_id")}
    feedback_events = [
        event
        for event in events
        if event.get("event_type") == "feedback"
        and (answer_feedback_scope(event) == "answer" or answer_feedback_label(event).startswith("answer_"))
    ]
    signals = [
        signal_from_feedback(event, by_operation.get(linked_operation_id(event)))
        for event in feedback_events
    ]
    label_counts = Counter(signal["label"] for signal in signals)
    family_counts = Counter(signal["family"] for signal in signals)
    recommendation_counts = Counter(signal["recommendation"] for signal in signals)
    checks = {
        "log_exists": log_path.exists(),
        "has_answer_feedback": len(feedback_events) > 0,
        "all_answer_feedback_linked": all(signal["recommendation"] != "reject_missing_link" for signal in signals),
        "has_positive_answer_signal": any(signal["rating"] > 0.0 for signal in signals),
        "has_negative_answer_signal": any(signal["rating"] < 0.0 for signal in signals),
        "bridge_signal_has_ogcf": any(
            signal["family"] == "bridge_warning_quality" and signal["ogcf_meta_present"] and signal["ogcf_diagnostics"]
            for signal in signals
        ),
        "missing_support_signal_present": any(signal["family"] == "missing_support_refusal" for signal in signals),
    }
    return {
        "schema": "answer_feedback_controller_signals/v1",
        "description": "Report-only answer-level feedback signals for neural-symbolic controller and resolver development.",
        "ok": all(checks.values()),
        "source_log": str(log_path),
        "event_count": len(events),
        "answer_feedback_count": len(feedback_events),
        "signal_count": len(signals),
        "checks": checks,
        "label_counts": dict(sorted(label_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "signals": signals,
    }


def clean_cell(value: Any, limit: int = 130) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Feedback Signal Eval",
        "",
        "This report is advisory only. It does not promote runtime config or learned policy artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Source log: `{report['source_log']}`",
        f"Answer feedback events: `{report['answer_feedback_count']}`",
        f"Signals: `{report['signal_count']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "```json",
            json.dumps(
                {
                    "labels": report["label_counts"],
                    "families": report["family_counts"],
                    "recommendations": report["recommendation_counts"],
                },
                indent=2,
            ),
            "```",
            "",
            "## Signals",
            "",
            "| recommendation | family | label | rating | ogcf | query |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for signal in report["signals"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | `{}` | {} |".format(
                signal["recommendation"],
                signal["family"],
                signal["label"],
                signal["rating"],
                signal["ogcf_meta_present"],
                clean_cell(signal["query"]),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse answer-level feedback into report-only controller signals.")
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.log))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "answer_feedback_count": report["answer_feedback_count"],
                "signal_count": report["signal_count"],
                "family_counts": report["family_counts"],
                "recommendation_counts": report["recommendation_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
