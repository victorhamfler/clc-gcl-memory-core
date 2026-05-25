from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.outcome_logging_regression import build_test_api
from eval.resolver_shadow_outcome_collector import collect_dataset


OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_runtime_context_log_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_runtime_context_log_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="resolver_shadow_runtime_context_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            api.teach(
                {
                    "text": "Runtime context regression: Victor prefers answers that cite selected memory evidence.",
                    "namespace": "agent:runtime-context",
                    "agent_id": "runtime-context-agent",
                    "source": "eval/runtime_context.md",
                    "memory_type": "preference",
                }
            )
            asked = api.ask(
                {
                    "query": "What does Victor prefer for answers?",
                    "namespace": "agent:runtime-context",
                    "include_global": False,
                    "agent_id": "runtime-context-agent",
                    "top_k": 3,
                    "include_resolver_shadow": True,
                    "include_selector_snapshot": True,
                }
            )
            selected_ids = [
                str(row.get("memory_id"))
                for row in asked.get("evidence") or []
                if row.get("memory_id")
            ]
            feedback = api.feedback(
                {
                    "label": "answer_correct",
                    "feedback_scope": "answer",
                    "query": "What does Victor prefer for answers?",
                    "operation_id": asked["operation_id"],
                    "selected_memory_ids": selected_ids,
                    "answer": asked.get("answer"),
                    "notes": "runtime adaptive context collector regression",
                }
            )
            log_path = api.outcome_logger.path
        finally:
            api.close()

        examples, skipped, sources = collect_dataset([log_path], 0.70, 0.50)
        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    example = examples[0] if examples else {}
    ask_rows = [row for row in rows if row.get("event_type") == "ask"]
    ask_payload = ask_rows[0].get("payload", {}) if ask_rows else {}
    checks = {
        "ask_logged": bool(ask_rows),
        "ask_has_adaptive_context": (ask_payload.get("adaptive_memory_context") or {}).get("schema") == "adaptive_memory_context/v1",
        "ask_has_resolver_shadow_response": bool(asked.get("resolver_shadow")),
        "feedback_answer_logged": feedback.get("feedback", {}).get("feedback_scope") == "answer",
        "collector_collected_one": len(examples) == 1 and not skipped,
        "collector_context_source_adaptive": example.get("context_source") == "adaptive_memory_context",
        "collector_label_answer_correct": example.get("label") == "answer_correct",
        "collector_passed": example.get("passed") is True,
        "collector_evidence_backed": "require_evidence_backed_answer" in (example.get("shadow_actions") or []),
        "source_count_adaptive": (sources[0].get("context_source_counts") or {}).get("adaptive_memory_context") == 1,
    }
    report = {
        "schema": "resolver_shadow_runtime_context_log_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "example": example,
        "log_path": str(log_path),
        "operation_ids": {
            "ask": asked.get("operation_id"),
            "feedback": feedback.get("operation_id"),
        },
        "source_summary": sources,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Runtime Context Log Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
