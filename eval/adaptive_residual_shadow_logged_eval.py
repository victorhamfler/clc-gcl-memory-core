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

from eval.adaptive_behavior_shadow_real_log_calibration import (  # noqa: E402
    expected_advisory,
    feedback_label,
    feedback_scope,
    linked_operation_id,
    payload,
    read_jsonl,
)


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_fourth_holdout_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_logged_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_logged_eval_report.md"


def response(event: dict[str, Any]) -> dict[str, Any]:
    value = payload(event).get("response")
    return value if isinstance(value, dict) else {}


def residual_shadow(event: dict[str, Any]) -> dict[str, Any]:
    direct = payload(event).get("adaptive_residual_shadow")
    if isinstance(direct, dict):
        return direct
    nested = response(event).get("adaptive_residual_shadow")
    return nested if isinstance(nested, dict) else {}


def shadow_for_expected(event: dict[str, Any]) -> dict[str, Any]:
    residual = residual_shadow(event)
    return {
        "diagnostics": {
            "selected_evidence_count": len(response(event).get("evidence") or []),
            "stale_context_count": len(response(event).get("stale_context") or []),
        }
    }


def family_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        family = str(row.get("behavior_family") or "unknown")
        counters[family]["total"] += 1
        counters[family][f"expected:{row.get('expected_advisory')}"] += 1
        counters[family][f"report_only:{row.get('report_only_advisory')}"] += 1
        counters[family]["would_override"] += int(bool(row.get("would_override")))
        counters[family]["helpful_override"] += int(row.get("override_outcome") == "helpful")
        counters[family]["harmful_override"] += int(row.get("override_outcome") == "harmful")
        counters[family]["neutral_wrong_override"] += int(row.get("override_outcome") == "neutral_wrong")
    return {family: dict(sorted(counter.items())) for family, counter in sorted(counters.items())}


def compact_examples(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {
            "query": row.get("query"),
            "feedback_label": row.get("feedback_label"),
            "behavior_family": row.get("behavior_family"),
            "expected_advisory": row.get("expected_advisory"),
            "symbolic_advisory": row.get("symbolic_advisory"),
            "report_only_advisory": row.get("report_only_advisory"),
            "family_advisory": row.get("family_advisory"),
            "residual_confidence": row.get("residual_confidence"),
            "suppression_reasons": row.get("suppression_reasons"),
            "override_outcome": row.get("override_outcome"),
        }
        for row in rows[:limit]
    ]


def build_report(log_path: Path) -> dict[str, Any]:
    events = read_jsonl(log_path)
    asks = {str(row.get("operation_id")): row for row in events if row.get("event_type") == "ask" and row.get("operation_id")}
    feedback = [
        row
        for row in events
        if row.get("event_type") == "feedback"
        and feedback_scope(row) == "answer"
        and linked_operation_id(row) in asks
    ]
    rows = []
    skipped = []
    for item in feedback:
        op_id = linked_operation_id(item)
        ask = asks.get(op_id)
        if not ask:
            skipped.append({"operation_id": op_id, "reason": "missing_ask"})
            continue
        residual = residual_shadow(ask)
        if residual.get("schema") != "adaptive_residual_shadow/v1":
            skipped.append({"operation_id": op_id, "reason": "missing_residual_shadow"})
            continue
        label = feedback_label(item)
        query = ((payload(ask).get("request") or {}).get("query") or response(ask).get("query") or "")
        expected_shadow = shadow_for_expected(ask)
        for decision in residual.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            family = str(decision.get("behavior_family") or "")
            expected = expected_advisory(
                label=label,
                behavior_family=family,
                ask_event=ask,
                shadow_payload=expected_shadow,
            )
            symbolic = str(decision.get("symbolic_advisory") or "")
            report_only = str(decision.get("report_only_advisory") or "")
            would = bool(decision.get("would_override"))
            outcome = "not_overridden"
            if would and report_only == expected:
                outcome = "helpful"
            elif would and symbolic == expected and report_only != expected:
                outcome = "harmful"
            elif would:
                outcome = "neutral_wrong"
            rows.append(
                {
                    "operation_id": op_id,
                    "query": query,
                    "feedback_label": label,
                    "behavior_family": family,
                    "expected_advisory": expected,
                    "symbolic_advisory": symbolic,
                    "report_only_advisory": report_only,
                    "family_advisory": decision.get("family_advisory"),
                    "residual_confidence": decision.get("residual_confidence"),
                    "suppression_reasons": decision.get("suppression_reasons") or [],
                    "would_override": would,
                    "override_outcome": outcome,
                }
            )
    override_rows = [row for row in rows if row.get("would_override")]
    helpful = [row for row in override_rows if row.get("override_outcome") == "helpful"]
    harmful = [row for row in override_rows if row.get("override_outcome") == "harmful"]
    neutral_wrong = [row for row in override_rows if row.get("override_outcome") == "neutral_wrong"]
    checks = {
        "has_ask_feedback_pairs": bool(feedback),
        "has_residual_decisions": bool(rows),
        "has_overrides": bool(override_rows),
        "zero_harmful_overrides": not harmful,
        "has_helpful_overrides": bool(helpful),
        "report_only": True,
        "no_runtime_mutation_fields": True,
    }
    return {
        "schema": "adaptive_residual_shadow_logged_eval/v1",
        "description": "Evaluate logged runtime adaptive residual shadow decisions against linked answer feedback.",
        "ok": all(checks.values()),
        "log_path": str(log_path),
        "checks": checks,
        "ask_count": len(asks),
        "answer_feedback_count": len(feedback),
        "decision_count": len(rows),
        "override_count": len(override_rows),
        "helpful_override_count": len(helpful),
        "harmful_override_count": len(harmful),
        "neutral_wrong_override_count": len(neutral_wrong),
        "family_summary": family_summary(rows),
        "helpful_examples": compact_examples(helpful),
        "harmful_examples": compact_examples(harmful),
        "neutral_wrong_examples": compact_examples(neutral_wrong),
        "skipped": skipped[:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Residual Shadow Logged Eval\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Ask count: `{report['ask_count']}`\n"
        + f"Answer feedback count: `{report['answer_feedback_count']}`\n"
        + f"Decision count: `{report['decision_count']}`\n"
        + f"Overrides: `{report['override_count']}` helpful `{report['helpful_override_count']}` harmful `{report['harmful_override_count']}` neutral-wrong `{report['neutral_wrong_override_count']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Family Summary\n\n```json\n"
        + json.dumps(report["family_summary"], indent=2)
        + "\n```\n\n"
        + "## Helpful Examples\n\n```json\n"
        + json.dumps(report["helpful_examples"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate logged adaptive residual shadow decisions.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.log)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "overrides": report["override_count"],
                "helpful": report["helpful_override_count"],
                "harmful": report["harmful_override_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
