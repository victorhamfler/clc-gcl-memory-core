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

from eval.adaptive_behavior_shadow_real_log_calibration import (  # noqa: E402
    feedback_scope,
    linked_operation_id,
    payload,
    read_jsonl,
)
from eval.adaptive_residual_shadow_logged_eval import residual_shadow, response  # noqa: E402


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_seventh_agent_style_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_risk_logged_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_risk_logged_eval_report.md"

PROTECTED_RISK_LABELS = {
    "unsupported_authority_claim",
    "stale_previous_lookup",
    "sensitive_private_lookup",
    "ordinary_namespace_scope_risk",
}
SAFE_LABELS = {"safe_supported_evidence_rescue", "other_symbolic_fallback", "no_term_suppression"}


def query_for_ask(event: dict[str, Any]) -> str:
    return str(((payload(event).get("request") or {}).get("query") or response(event).get("query") or ""))


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
    missing_diagnostics = []
    model_summaries = []
    for item in feedback:
        op_id = linked_operation_id(item)
        ask = asks.get(op_id)
        if not ask:
            continue
        residual = residual_shadow(ask)
        model = residual.get("learned_risk_model") if isinstance(residual.get("learned_risk_model"), dict) else {}
        if model:
            model_summaries.append(model)
        for decision in residual.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            learned = decision.get("learned_risk_label")
            term = decision.get("term_risk_label")
            if learned is None or term is None:
                missing_diagnostics.append({"operation_id": op_id, "query": query_for_ask(ask)})
                continue
            learned_protected = str(learned) in PROTECTED_RISK_LABELS
            term_protected = str(term) in PROTECTED_RISK_LABELS
            rows.append(
                {
                    "operation_id": op_id,
                    "query": query_for_ask(ask),
                    "behavior_family": decision.get("behavior_family"),
                    "would_override": bool(decision.get("would_override")),
                    "suppression_reasons": decision.get("suppression_reasons") or [],
                    "term_risk_label": term,
                    "learned_risk_label": learned,
                    "learned_risk_confidence": decision.get("learned_risk_confidence"),
                    "learned_risk_disagrees_with_terms": bool(decision.get("learned_risk_disagrees_with_terms")),
                    "learned_protected": learned_protected,
                    "term_protected": term_protected,
                    "learned_catches_beyond_terms": learned_protected and not term_protected,
                    "learned_safe_where_terms_protect": str(learned) in SAFE_LABELS and term_protected,
                }
            )
    counters = Counter()
    for row in rows:
        counters[f"learned:{row['learned_risk_label']}"] += 1
        counters[f"term:{row['term_risk_label']}"] += 1
        counters["disagreements"] += int(row["learned_risk_disagrees_with_terms"])
        counters["learned_beyond_terms"] += int(row["learned_catches_beyond_terms"])
        counters["learned_safe_where_terms_protect"] += int(row["learned_safe_where_terms_protect"])
    learned_beyond_terms = [row for row in rows if row["learned_catches_beyond_terms"]]
    learned_safe_where_terms_protect = [row for row in rows if row["learned_safe_where_terms_protect"]]
    checks = {
        "has_ask_feedback_pairs": bool(feedback),
        "has_risk_diagnostic_rows": bool(rows),
        "no_missing_learned_risk_fields": not missing_diagnostics,
        "risk_model_report_only": bool(model_summaries)
        and all(model.get("report_only") is True and model.get("mutates_runtime") is False and model.get("mutates_config") is False for model in model_summaries),
        "term_overprotection_reported_not_failed": True,
        "report_only": True,
        "no_runtime_mutation": True,
        "no_config_mutation": True,
    }
    return {
        "schema": "adaptive_residual_risk_logged_eval/v1",
        "description": "Evaluate learned residual-risk diagnostics exported in runtime residual-shadow logs.",
        "ok": all(checks.values()),
        "log_path": str(log_path),
        "checks": checks,
        "ask_count": len(asks),
        "answer_feedback_count": len(feedback),
        "risk_diagnostic_row_count": len(rows),
        "summary": dict(sorted(counters.items())),
        "learned_beyond_terms_count": len(learned_beyond_terms),
        "term_overprotection_count": len(learned_safe_where_terms_protect),
        "learned_beyond_terms_examples": learned_beyond_terms[:12],
        "term_overprotection_examples": learned_safe_where_terms_protect[:12],
        "missing_diagnostics": missing_diagnostics[:12],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Residual Risk Logged Eval\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Risk diagnostic rows: `{report['risk_diagnostic_row_count']}`\n"
        + f"Learned beyond terms: `{report['learned_beyond_terms_count']}`\n"
        + f"Term overprotection signals: `{report['term_overprotection_count']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Summary\n\n```json\n"
        + json.dumps(report["summary"], indent=2)
        + "\n```\n\n"
        + "## Learned Beyond Terms\n\n```json\n"
        + json.dumps(report["learned_beyond_terms_examples"], indent=2)
        + "\n```\n\n"
        + "## Term Overprotection Signals\n\n```json\n"
        + json.dumps(report["term_overprotection_examples"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate logged learned residual-risk diagnostics.")
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
                "risk_rows": report["risk_diagnostic_row_count"],
                "learned_beyond_terms": report["learned_beyond_terms_count"],
                "term_overprotection": report["term_overprotection_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
