from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.outcome_logging_regression import build_test_api  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_runtime_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_runtime_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_residual_shadow_runtime_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught = api.teach(
                {
                    "text": "Adaptive residual shadow runtime regression: supported answers must cite selected memory evidence.",
                    "namespace": "agent:adaptive-residual-shadow-runtime",
                    "agent_id": "adaptive-residual-shadow-agent",
                    "source": "eval/adaptive_residual_shadow_runtime.md",
                    "memory_type": "design_rule",
                }
            )
            base = api.ask(
                {
                    "query": "What must supported answers cite?",
                    "namespace": "agent:adaptive-residual-shadow-runtime",
                    "include_global": False,
                    "agent_id": "adaptive-residual-shadow-agent",
                    "top_k": 3,
                    "include_selector_snapshot": True,
                }
            )
            shadowed = api.ask(
                {
                    "query": "What must supported answers cite?",
                    "namespace": "agent:adaptive-residual-shadow-runtime",
                    "include_global": False,
                    "agent_id": "adaptive-residual-shadow-agent",
                    "top_k": 3,
                    "include_selector_snapshot": True,
                    "include_resolver_shadow": True,
                    "include_adaptive_residual_shadow": True,
                    "log_adaptive_residual_shadow": True,
                }
            )
            log_path = api.outcome_logger.path
            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        finally:
            api.close()

    ask_events = [row for row in rows if row.get("event_type") == "ask"]
    residual = shadowed.get("adaptive_residual_shadow") or {}
    behavior = shadowed.get("adaptive_behavior_shadow")
    logged_residual = ((ask_events[-1].get("payload") or {}).get("adaptive_residual_shadow") or {}) if ask_events else {}
    checks = {
        "baseline_does_not_include_residual_shadow": base.get("adaptive_residual_shadow") is None,
        "requested_residual_shadow_in_response": residual.get("schema") == "adaptive_residual_shadow/v1",
        "requested_residual_shadow_logged": logged_residual.get("schema") == "adaptive_residual_shadow/v1",
        "adaptive_behavior_shadow_not_forced_into_response": behavior is None,
        "report_only": residual.get("report_only") is True
        and residual.get("mutates_answer") is False
        and residual.get("mutates_selector_policy") is False
        and residual.get("mutates_memory") is False
        and residual.get("mutates_config") is False,
        "has_policy_suppressors": set((residual.get("policy") or {}).get("suppressors") or []) >= {
            "sensitive_private",
            "stale_previous",
            "ordinary_namespace_profile",
        },
        "has_supported_evidence_decision": any(
            item.get("behavior_family") == "supported_evidence"
            for item in residual.get("decisions") or []
            if isinstance(item, dict)
        ),
        "learned_risk_model_report_only": (residual.get("learned_risk_model") or {}).get("report_only") is True
        and (residual.get("learned_risk_model") or {}).get("mutates_runtime") is False
        and (residual.get("learned_risk_model") or {}).get("mutates_config") is False,
        "decisions_include_learned_risk_labels": all(
            "learned_risk_label" in item and "term_risk_label" in item
            for item in residual.get("decisions") or []
            if isinstance(item, dict)
        ),
        "selector_snapshot_unchanged": base.get("selector_snapshot", {}).get("decision")
        == shadowed.get("selector_snapshot", {}).get("decision"),
        "answer_unchanged": base.get("answer") == shadowed.get("answer"),
        "evidence_unchanged": [row.get("memory_id") for row in base.get("evidence") or []]
        == [row.get("memory_id") for row in shadowed.get("evidence") or []],
        "outcome_log_has_two_ask_events": len(ask_events) == 2,
        "memory_id_present": bool(taught.get("memory", {}).get("memory_id")),
    }
    result = {
        "schema": "adaptive_residual_shadow_runtime_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "residual_summary": {
            "ok": residual.get("ok"),
            "decision_counts": residual.get("decision_counts"),
            "policy": residual.get("policy"),
            "learned_risk_model": residual.get("learned_risk_model"),
            "decision_count": len(residual.get("decisions") or []),
        },
        "log_path": str(log_path),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Runtime Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({k: result[k] for k in ("checks", "residual_summary", "log_path")}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
