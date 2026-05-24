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
DEFAULT_PROPOSALS = REPO_ROOT / "experiments" / "answer_behavior_proposals_results.json"
DEFAULT_GUARD = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_real_log_shadow_replay_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_real_log_shadow_replay_report.md"


POSITIVE_SUPPORTED_LABELS = {"answer_correct", "answer_good_citation"}
BRIDGE_USEFUL_LABELS = {"answer_bridge_warning_useful"}
BRIDGE_NOISE_LABELS = {"answer_bridge_warning_noise"}
MISSING_SUPPORT_LABELS = {"answer_missing_support", "answer_overconfident"}
STALE_DISCLOSURE_LABELS = {"answer_stale", "answer_conflict_not_disclosed"}
ANSWER_LABELS = (
    POSITIVE_SUPPORTED_LABELS
    | BRIDGE_USEFUL_LABELS
    | BRIDGE_NOISE_LABELS
    | MISSING_SUPPORT_LABELS
    | STALE_DISCLOSURE_LABELS
    | {"answer_wrong_scope", "answer_bad_citation"}
)
REFUSAL_MARKERS = (
    "do not have enough",
    "not enough memory evidence",
    "insufficient",
    "cannot answer",
    "no memory evidence",
    "not have memory evidence",
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return loaded


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


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def nested_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(event, "payload")


def guarded_targets(guard: dict[str, Any]) -> set[str]:
    return {
        normalize_text(item.get("target_behavior"))
        for item in guard.get("guarded_proposals") or []
        if isinstance(item, dict) and normalize_text(item.get("status")) == "guarded_ready"
    }


def proposal_targets(proposals: dict[str, Any]) -> set[str]:
    return {
        normalize_text(item.get("target_behavior"))
        for item in proposals.get("proposals") or []
        if isinstance(item, dict)
    }


def feedback_scope(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    return normalize_text(request.get("feedback_scope") or feedback.get("feedback_scope"))


def feedback_label(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    return normalize_text(request.get("label") or feedback.get("label"))


def linked_operation_id(event: dict[str, Any]) -> str:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    return str(event.get("linked_operation_id") or request.get("linked_operation_id") or "").strip()


def request_selected_ids(event: dict[str, Any]) -> list[str]:
    event_payload = payload(event)
    request = nested_dict(event_payload, "request")
    feedback = nested_dict(event_payload, "feedback")
    values = request.get("selected_memory_ids")
    if values is None:
        values = feedback.get("selected_memory_ids")
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value or "").strip()]


def ask_response(ask_event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(payload(ask_event), "response")


def ask_request(ask_event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(payload(ask_event), "request")


def selector_snapshot(ask_event: dict[str, Any]) -> dict[str, Any]:
    return nested_dict(payload(ask_event), "selector_snapshot")


def evidence_rows(ask_event: dict[str, Any]) -> list[dict[str, Any]]:
    response = ask_response(ask_event)
    rows: list[dict[str, Any]] = []
    for section in ("evidence", "source_context", "stale_context", "raw_results"):
        for row in response.get(section) or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def selected_rows(ask_event: dict[str, Any], selected_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(selected_ids)
    rows = []
    for row in evidence_rows(ask_event):
        if str(row.get("memory_id") or "") in wanted:
            rows.append(row)
    if rows:
        return rows
    response_evidence = ask_response(ask_event).get("evidence")
    if isinstance(response_evidence, list) and response_evidence:
        return [row for row in response_evidence if isinstance(row, dict)]
    return []


def has_refusal_language(answer: str) -> bool:
    lowered = normalize_text(answer)
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def row_authority_values(rows: list[dict[str, Any]]) -> set[str]:
    return {normalize_text(row.get("authority_state")) for row in rows if normalize_text(row.get("authority_state"))}


def stale_conflict_present(ask_event: dict[str, Any]) -> bool:
    snapshot = selector_snapshot(ask_event)
    diagnostics = nested_dict(snapshot, "diagnostics")
    try:
        if float(diagnostics.get("stale_current_conflict") or 0.0) > 0.0:
            return True
    except (TypeError, ValueError):
        pass
    response = ask_response(ask_event)
    if response.get("conflict") is True and response.get("stale_context"):
        return True
    rows = evidence_rows(ask_event)
    authorities = row_authority_values(rows)
    return "stale" in authorities and "current" in authorities


def ordinary_fact_lookup(ask_event: dict[str, Any]) -> bool:
    diagnostics = nested_dict(selector_snapshot(ask_event), "diagnostics")
    if normalize_text(diagnostics.get("ogcf_intent")) == "ordinary_fact_lookup":
        return True
    request = ask_request(ask_event)
    query = normalize_text(request.get("query"))
    ordinary_terms = ("when is", "what is the calendar", "meeting", "scheduled", "calendar", "location")
    return any(term in query for term in ordinary_terms)


def simulate_actions(ask_event: dict[str, Any], selected_ids: list[str], targets: set[str]) -> list[str]:
    actions: list[str] = []
    rows = selected_rows(ask_event, selected_ids)
    response = ask_response(ask_event)
    diagnostics = nested_dict(selector_snapshot(ask_event), "diagnostics")
    selected_count = len(selected_ids) if selected_ids else len(response.get("evidence") or [])
    if "supported_answer_quality" in targets and selected_count > 0:
        actions.append("require_evidence_backed_answer")
    if stale_conflict_present(ask_event):
        actions.append("disclose_stale_conflict")
    if "bridge_warning_disclosure" in targets:
        try:
            ogcf_score = float(diagnostics.get("ogcf_bridge_overload_score") or 0.0)
            ogcf_effective = float(diagnostics.get("ogcf_effective_affected_memory_ratio") or 0.0)
        except (TypeError, ValueError):
            ogcf_score = 0.0
            ogcf_effective = 0.0
        if (
            rows
            and selector_snapshot(ask_event).get("ogcf_meta_present")
            and not ordinary_fact_lookup(ask_event)
            and (ogcf_score >= 0.7 or ogcf_effective >= 0.5)
        ):
            actions.append("emit_ogcf_bridge_warning")
    if "missing_support_refusal" in targets and selected_count == 0:
        actions.append("preserve_missing_support_refusal")
    return actions


def expectations(label: str, ask_event: dict[str, Any], selected_ids: list[str]) -> tuple[set[str], set[str], list[str]]:
    expected: set[str] = set()
    forbidden: set[str] = set()
    notes: list[str] = []
    selected_count = len(selected_ids) if selected_ids else len(ask_response(ask_event).get("evidence") or [])
    if label in POSITIVE_SUPPORTED_LABELS and selected_count > 0:
        expected.add("require_evidence_backed_answer")
    if label in BRIDGE_USEFUL_LABELS:
        expected.add("emit_ogcf_bridge_warning")
        if selected_count > 0:
            expected.add("require_evidence_backed_answer")
    if label in BRIDGE_NOISE_LABELS:
        forbidden.add("emit_ogcf_bridge_warning")
    if label in MISSING_SUPPORT_LABELS:
        if selected_count == 0:
            expected.add("preserve_missing_support_refusal")
        else:
            notes.append("missing_support_label_with_selected_evidence")
        forbidden.add("emit_ogcf_bridge_warning")
    if label in STALE_DISCLOSURE_LABELS:
        expected.add("disclose_stale_conflict")
    if label == "answer_bad_citation" and selected_count > 0:
        expected.add("require_evidence_backed_answer")
    if label == "answer_wrong_scope" and selected_count > 0:
        expected.add("require_evidence_backed_answer")
    if ordinary_fact_lookup(ask_event):
        forbidden.add("emit_ogcf_bridge_warning")
    return expected, forbidden, notes


def build_cases(log_paths: list[Path], targets: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for log_path in log_paths:
        rows = read_jsonl(log_path)
        asks = {
            str(row.get("operation_id")): row
            for row in rows
            if normalize_text(row.get("event_type")) == "ask" and str(row.get("operation_id") or "")
        }
        for row in rows:
            if normalize_text(row.get("event_type")) != "feedback":
                continue
            if feedback_scope(row) != "answer":
                continue
            label = feedback_label(row)
            if label not in ANSWER_LABELS:
                skipped.append(
                    {
                        "reason": "unsupported_answer_label",
                        "label": label,
                        "operation_id": row.get("operation_id"),
                        "source_log": str(log_path),
                    }
                )
                continue
            linked_id = linked_operation_id(row)
            ask_event = asks.get(linked_id)
            if not ask_event:
                skipped.append(
                    {
                        "reason": "missing_linked_ask",
                        "label": label,
                        "operation_id": row.get("operation_id"),
                        "linked_operation_id": linked_id,
                        "source_log": str(log_path),
                    }
                )
                continue
            selected_ids = request_selected_ids(row)
            actions = simulate_actions(ask_event, selected_ids, targets)
            expected, forbidden, notes = expectations(label, ask_event, selected_ids)
            actual = set(actions)
            answer = str(ask_response(ask_event).get("answer") or "")
            if "preserve_missing_support_refusal" in expected and not has_refusal_language(answer):
                notes.append("answer_lacks_refusal_language")
            case = {
                "id": row.get("operation_id"),
                "source_log": str(log_path),
                "linked_operation_id": linked_id,
                "query": ask_request(ask_event).get("query"),
                "label": label,
                "rating": nested_dict(payload(row), "request").get("rating"),
                "selected_memory_ids": selected_ids,
                "selected_evidence_count": len(selected_rows(ask_event, selected_ids)),
                "answer_preview": answer[:280],
                "actions": actions,
                "expected_actions": sorted(expected),
                "forbidden_actions": sorted(forbidden),
                "missing_expected": sorted(expected - actual),
                "forbidden_hits": sorted(forbidden & actual),
                "notes": notes,
                "ogcf_meta_present": bool(selector_snapshot(ask_event).get("ogcf_meta_present")),
                "ordinary_fact_lookup": ordinary_fact_lookup(ask_event),
                "stale_conflict": stale_conflict_present(ask_event),
            }
            case["passed"] = not case["missing_expected"] and not case["forbidden_hits"]
            cases.append(case)
    return cases, skipped


def build_report(log_paths: list[Path], proposals_path: Path, guard_path: Path) -> dict[str, Any]:
    proposals = read_json(proposals_path)
    guard = read_json(guard_path)
    if proposals.get("schema") != "answer_behavior_proposals/v1":
        return {"schema": "answer_behavior_real_log_shadow_replay/v1", "ok": False, "error": "unsupported_proposals_schema"}
    if guard.get("schema") != "answer_behavior_proposal_guard/v1":
        return {"schema": "answer_behavior_real_log_shadow_replay/v1", "ok": False, "error": "unsupported_guard_schema"}
    targets = proposal_targets(proposals) & guarded_targets(guard)
    cases, skipped = build_cases(log_paths, targets)
    label_counts = Counter(case["label"] for case in cases)
    action_counts = Counter(action for case in cases for action in case["actions"])
    checks = {
        "proposals_passed": proposals.get("ok") is True,
        "guard_passed": guard.get("ok") is True,
        "has_real_answer_cases": bool(cases),
        "all_replayed_cases_pass": bool(cases) and all(case["passed"] for case in cases),
        "report_only": True,
    }
    return {
        "schema": "answer_behavior_real_log_shadow_replay/v1",
        "description": "Report-only replay of guarded answer behavior proposals over linked ask/answer-feedback logs.",
        "ok": all(checks.values()),
        "log_paths": [str(path) for path in log_paths],
        "proposals_path": str(proposals_path),
        "guard_path": str(guard_path),
        "available_targets": sorted(targets),
        "checks": checks,
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case["passed"]),
        "skipped_count": len(skipped),
        "label_counts": dict(sorted(label_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "mutates_config": False,
        "mutates_runtime": False,
        "cases": cases,
        "skipped": skipped[:50],
    }


def clean_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Behavior Real-Log Shadow Replay",
        "",
        "This replay is advisory only. It does not modify resolver code, selector policy, runtime config, memory rows, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report.get('case_count', 0)}`",
        f"Passed cases: `{report.get('passed_count', 0)}`",
        f"Skipped events: `{report.get('skipped_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Label Counts", "", "| label | count |", "| --- | ---: |"])
    for label, count in (report.get("label_counts") or {}).items():
        lines.append(f"| `{label}` | {count} |")
    lines.extend(["", "## Action Counts", "", "| action | count |", "| --- | ---: |"])
    for action, count in (report.get("action_counts") or {}).items():
        lines.append(f"| `{action}` | {count} |")
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| case | label | pass | actions | missing | forbidden hits | query |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report.get("cases") or []:
        lines.append(
            f"| `{case.get('id')}` | `{case.get('label')}` | `{case.get('passed')}` | "
            f"`{', '.join(case.get('actions') or [])}` | `{', '.join(case.get('missing_expected') or [])}` | "
            f"`{', '.join(case.get('forbidden_hits') or [])}` | {clean_cell(case.get('query'))} |"
        )
    if report.get("skipped"):
        lines.extend(["", "## Skipped Sample", "", "| reason | label | operation |", "| --- | --- | --- |"])
        for item in report.get("skipped") or []:
            lines.append(f"| `{item.get('reason')}` | `{item.get('label')}` | `{item.get('operation_id')}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_log_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay guarded answer behavior proposals over real linked answer logs.")
    parser.add_argument("--log", action="append", default=None, help="JSONL outcome log. Can be passed multiple times.")
    parser.add_argument("--proposals", default=str(DEFAULT_PROPOSALS))
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    log_paths = parse_log_paths(args.log) or [DEFAULT_LOG]
    report = build_report(log_paths, Path(args.proposals), Path(args.guard))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "case_count": report.get("case_count"),
                "passed_count": report.get("passed_count"),
                "skipped_count": report.get("skipped_count"),
                "label_counts": report.get("label_counts"),
                "action_counts": report.get("action_counts"),
                "checks": report.get("checks"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
