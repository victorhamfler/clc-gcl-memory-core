from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.answer_behavior_shadow import resolver_shadow_actions


DEFAULT_LOG = REPO_ROOT / "experiments" / "answer_behavior_ogcf_bridge_worklog.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_ogcf_bridge_worklog_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_ogcf_bridge_worklog_regression_report.md"


BRIDGE_USEFUL = {"answer_bridge_warning_useful"}
BRIDGE_NOISE = {"answer_bridge_warning_noise"}
MISSING_SUPPORT = {"answer_missing_support", "answer_overconfident"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def nested(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return nested(event, "payload")


def label(event: dict[str, Any]) -> str:
    req = nested(payload(event), "request")
    fb = nested(payload(event), "feedback")
    return str(req.get("label") or fb.get("label") or "").strip().lower()


def linked_id(event: dict[str, Any]) -> str:
    req = nested(payload(event), "request")
    return str(event.get("linked_operation_id") or req.get("linked_operation_id") or "").strip()


def ask_response(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "response")


def ask_request(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "request")


def selector_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "selector_snapshot")


def expected_for(label_value: str, shadow: dict[str, Any]) -> tuple[set[str], set[str]]:
    expected: set[str] = set()
    forbidden: set[str] = set()
    if label_value in BRIDGE_USEFUL:
        expected.add("emit_ogcf_bridge_warning")
        expected.add("require_evidence_backed_answer")
    if label_value in BRIDGE_NOISE:
        forbidden.add("emit_ogcf_bridge_warning")
    if label_value in MISSING_SUPPORT:
        expected.add("preserve_missing_support_refusal")
        forbidden.add("emit_ogcf_bridge_warning")
    if shadow.get("diagnostics", {}).get("stale_conflict"):
        expected.add("disclose_stale_conflict")
    return expected, forbidden


def build_report(log_path: Path = DEFAULT_LOG) -> dict[str, Any]:
    rows = read_jsonl(log_path)
    asks = {
        str(row.get("operation_id")): row
        for row in rows
        if str(row.get("event_type") or "").lower() == "ask" and row.get("operation_id")
    }
    cases: list[dict[str, Any]] = []
    for event in rows:
        if str(event.get("event_type") or "").lower() != "feedback":
            continue
        label_value = label(event)
        ask = asks.get(linked_id(event))
        if not ask:
            cases.append(
                {
                    "id": event.get("operation_id"),
                    "label": label_value,
                    "passed": False,
                    "missing_expected": ["linked_ask"],
                    "forbidden_hits": [],
                    "actions": [],
                    "query": "",
                }
            )
            continue
        response = ask_response(ask)
        shadow = resolver_shadow_actions(
            query=str(ask_request(ask).get("query") or ""),
            answer=str(response.get("answer") or ""),
            evidence=response.get("evidence") or [],
            stale_context=response.get("stale_context") or [],
            selector_snapshot=selector_snapshot(ask),
            conflict=bool(response.get("conflict")),
            config={"enabled": True},
        )
        expected, forbidden = expected_for(label_value, shadow)
        actual = set(shadow.get("actions") or [])
        missing = sorted(expected - actual)
        forbidden_hits = sorted(forbidden & actual)
        cases.append(
            {
                "id": event.get("operation_id"),
                "linked_operation_id": linked_id(event),
                "label": label_value,
                "query": ask_request(ask).get("query"),
                "actions": shadow.get("actions") or [],
                "expected_actions": sorted(expected),
                "forbidden_actions": sorted(forbidden),
                "missing_expected": missing,
                "forbidden_hits": forbidden_hits,
                "mutates_answer": shadow.get("mutates_answer"),
                "passed": not missing and not forbidden_hits and shadow.get("mutates_answer") is False,
                "diagnostics": shadow.get("diagnostics"),
            }
        )
    return {
        "schema": "resolver_shadow_ogcf_bridge_worklog_regression/v1",
        "ok": bool(cases) and all(case["passed"] for case in cases),
        "log_path": str(log_path),
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case["passed"]),
        "cases": cases,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow OGCF Bridge Worklog Regression",
        "",
        "This regression calls the actual resolver-shadow module on live-log-shaped OGCF bridge cases.",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        f"Passed cases: `{report['passed_count']}`",
        "",
        "| case | label | pass | actions | missing | forbidden | query |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        query = str(case.get("query") or "").replace("|", "\\|")
        lines.append(
            f"| `{case['id']}` | `{case['label']}` | `{case['passed']}` | "
            f"`{', '.join(case.get('actions') or [])}` | `{', '.join(case.get('missing_expected') or [])}` | "
            f"`{', '.join(case.get('forbidden_hits') or [])}` | {query[:120]} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "case_count": report["case_count"], "passed_count": report["passed_count"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
