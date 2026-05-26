from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.outcome_logging_regression import build_test_api  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_runtime_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_runtime_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_behavior_shadow_runtime_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught = api.teach(
                {
                    "text": "Adaptive behavior shadow runtime regression: supported answers must stay grounded in selected evidence.",
                    "namespace": "agent:adaptive-behavior-shadow-runtime",
                    "agent_id": "adaptive-behavior-shadow-agent",
                    "source": "eval/adaptive_behavior_shadow_runtime.md",
                    "memory_type": "design_rule",
                }
            )
            base = api.ask(
                {
                    "query": "What must supported answers stay grounded in?",
                    "namespace": "agent:adaptive-behavior-shadow-runtime",
                    "include_global": False,
                    "agent_id": "adaptive-behavior-shadow-agent",
                    "top_k": 3,
                    "include_selector_snapshot": True,
                }
            )
            shadowed = api.ask(
                {
                    "query": "What must supported answers stay grounded in?",
                    "namespace": "agent:adaptive-behavior-shadow-runtime",
                    "include_global": False,
                    "agent_id": "adaptive-behavior-shadow-agent",
                    "top_k": 3,
                    "include_selector_snapshot": True,
                    "include_resolver_shadow": True,
                    "include_adaptive_behavior_shadow": True,
                    "log_adaptive_behavior_shadow": True,
                }
            )
            log_path = api.outcome_logger.path
            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        finally:
            api.close()

    ask_events = [row for row in rows if row.get("event_type") == "ask"]
    base_shadow = base.get("adaptive_behavior_shadow")
    shadow = shadowed.get("adaptive_behavior_shadow") or {}
    logged_shadow = ((ask_events[-1].get("payload") or {}).get("adaptive_behavior_shadow") or {}) if ask_events else {}
    shadow_features = ((shadow.get("diagnostics") or {}).get("evidence_context_features") or {})
    logged_features = ((logged_shadow.get("diagnostics") or {}).get("evidence_context_features") or {})
    checks = {
        "baseline_does_not_include_shadow": base_shadow is None,
        "requested_shadow_in_response": shadow.get("schema") == "adaptive_behavior_shadow/v1",
        "requested_shadow_logged": logged_shadow.get("schema") == "adaptive_behavior_shadow/v1",
        "report_only": shadow.get("report_only") is True
        and shadow.get("mutates_answer") is False
        and shadow.get("mutates_selector_policy") is False
        and shadow.get("mutates_memory") is False
        and shadow.get("mutates_config") is False,
        "has_supported_evidence_decision": any(
            item.get("behavior_family") == "supported_evidence"
            for item in shadow.get("decisions") or []
            if isinstance(item, dict)
        ),
        "selector_snapshot_unchanged": base.get("selector_snapshot", {}).get("decision")
        == shadowed.get("selector_snapshot", {}).get("decision"),
        "answer_unchanged": base.get("answer") == shadowed.get("answer"),
        "evidence_unchanged": [row.get("memory_id") for row in base.get("evidence") or []]
        == [row.get("memory_id") for row in shadowed.get("evidence") or []],
        "outcome_log_has_two_ask_events": len(ask_events) == 2,
        "memory_id_present": bool(taught.get("memory", {}).get("memory_id")),
        "evidence_context_features_in_response": shadow_features.get("selected_count") == 1
        and shadow_features.get("retrieval_count", 0) >= 1
        and "memory_bad_rate" in shadow_features,
        "evidence_context_features_logged": logged_features == shadow_features,
    }
    result = {
        "schema": "adaptive_behavior_shadow_runtime_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "shadow_summary": {
            "advisory_counts": shadow.get("advisory_counts"),
            "diagnostics": shadow.get("diagnostics"),
            "evidence_context_features": shadow_features,
            "decision_count": len(shadow.get("decisions") or []),
        },
        "log_path": str(log_path),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Shadow Runtime Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({k: result[k] for k in ("checks", "shadow_summary", "log_path")}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
