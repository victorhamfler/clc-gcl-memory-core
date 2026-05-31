from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_shadow_real_log_calibration import (  # noqa: E402
    expected_advisory,
    feedback_label,
    feedback_scope,
    linked_operation_id,
    payload,
    read_jsonl,
)
from eval.adaptive_residual_shadow_logged_eval import residual_shadow, response, shadow_for_expected  # noqa: E402


LOGS = [
    REPO_ROOT / "experiments" / "adaptive_residual_shadow_seventh_agent_style_outcomes.jsonl",
    REPO_ROOT / "experiments" / "adaptive_residual_shadow_eighth_meta_recurrence_outcomes.jsonl",
]
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_risk_exception_simulation_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_risk_exception_simulation_report.md"

SAFE_LEARNED_LABELS = {"safe_supported_evidence_rescue"}
PROTECTED_TERM_LABELS = {
    "unsupported_authority_claim",
    "stale_previous_lookup",
    "sensitive_private_lookup",
    "ordinary_namespace_scope_risk",
}


def query_for_ask(event: dict[str, Any]) -> str:
    return str(((payload(event).get("request") or {}).get("query") or response(event).get("query") or ""))


def simulation_outcome(decision: dict[str, Any], expected: str) -> str:
    simulated = str(decision.get("family_advisory") or decision.get("report_only_advisory") or "")
    symbolic = str(decision.get("symbolic_advisory") or "")
    if simulated == expected and symbolic != expected:
        return "helpful"
    if symbolic == expected and simulated != expected:
        return "harmful"
    if simulated != expected:
        return "neutral_wrong"
    return "same_correct"


def build_report(logs: list[Path] | None = None) -> dict[str, Any]:
    selected_logs = logs or LOGS
    rows = []
    skipped = []
    for log in selected_logs:
        if not log.exists():
            skipped.append({"log": str(log), "reason": "missing"})
            continue
        events = read_jsonl(log)
        asks = {str(row.get("operation_id")): row for row in events if row.get("event_type") == "ask" and row.get("operation_id")}
        feedback = [
            row
            for row in events
            if row.get("event_type") == "feedback"
            and feedback_scope(row) == "answer"
            and linked_operation_id(row) in asks
        ]
        for item in feedback:
            op_id = linked_operation_id(item)
            ask = asks.get(op_id)
            if not ask:
                continue
            residual = residual_shadow(ask)
            expected_shadow = shadow_for_expected(ask)
            label = feedback_label(item)
            for decision in residual.get("decisions") or []:
                if not isinstance(decision, dict):
                    continue
                learned_label = str(decision.get("learned_risk_label") or "")
                term_label = str(decision.get("term_risk_label") or "")
                if learned_label not in SAFE_LEARNED_LABELS or term_label not in PROTECTED_TERM_LABELS:
                    continue
                if str(decision.get("residual_prediction") or "") != "symbolic_wrong":
                    continue
                if str(decision.get("behavior_family") or "") != "supported_evidence":
                    continue
                expected = expected_advisory(
                    label=label,
                    behavior_family=str(decision.get("behavior_family") or ""),
                    ask_event=ask,
                    shadow_payload=expected_shadow,
                )
                outcome = simulation_outcome(decision, expected)
                rows.append(
                    {
                        "source_log": log.name,
                        "operation_id": op_id,
                        "query": query_for_ask(ask),
                        "feedback_label": label,
                        "term_risk_label": term_label,
                        "learned_risk_label": learned_label,
                        "learned_risk_confidence": decision.get("learned_risk_confidence"),
                        "expected_advisory": expected,
                        "symbolic_advisory": decision.get("symbolic_advisory"),
                        "simulated_exception_advisory": decision.get("family_advisory"),
                        "outcome": outcome,
                    }
                )
    counters = Counter(row["outcome"] for row in rows)
    checks = {
        "logs_available": bool([log for log in selected_logs if log.exists()]),
        "has_simulated_exception_candidates": bool(rows),
        "zero_harmful": counters.get("harmful", 0) == 0,
        "zero_neutral_wrong": counters.get("neutral_wrong", 0) == 0,
        "report_only": True,
        "no_runtime_mutation": True,
        "no_config_mutation": True,
        "promotion_blocked": True,
    }
    return {
        "schema": "adaptive_residual_risk_exception_simulation/v1",
        "description": "Report-only simulation of learned contextual exceptions for term-overprotected residual decisions.",
        "ok": all(checks.values()),
        "checks": checks,
        "logs": [str(log) for log in selected_logs if log.exists()],
        "candidate_count": len(rows),
        "outcome_counts": dict(sorted(counters.items())),
        "helpful_count": counters.get("helpful", 0),
        "harmful_count": counters.get("harmful", 0),
        "neutral_wrong_count": counters.get("neutral_wrong", 0),
        "same_correct_count": counters.get("same_correct", 0),
        "rows": rows[:20],
        "skipped": skipped,
        "recommendation": "keep_report_only_collect_external_simulation" if rows else "collect_more_candidates",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Risk Exception Simulation\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Candidates: `{report['candidate_count']}`\n"
        + f"Helpful: `{report['helpful_count']}` harmful `{report['harmful_count']}` neutral-wrong `{report['neutral_wrong_count']}` same-correct `{report['same_correct_count']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Rows\n\n```json\n"
        + json.dumps(report["rows"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "candidates": report["candidate_count"],
                "helpful": report["helpful_count"],
                "harmful": report["harmful_count"],
                "neutral_wrong": report["neutral_wrong_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
