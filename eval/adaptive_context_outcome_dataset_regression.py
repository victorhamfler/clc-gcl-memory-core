from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_outcome_dataset import build_report
from eval.outcome_logging_regression import build_test_api


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_outcome_dataset_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_outcome_dataset_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_context_dataset_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught = api.teach(
                {
                    "text": "Adaptive context dataset regression: Victor prefers grounded answers with selected memory evidence.",
                    "namespace": "agent:adaptive-context-dataset",
                    "agent_id": "adaptive-context-agent",
                    "source": "eval/adaptive_context_dataset.md",
                    "memory_type": "preference",
                }
            )
            asked = api.ask(
                {
                    "query": "What does Victor prefer for grounded answers?",
                    "namespace": "agent:adaptive-context-dataset",
                    "include_global": False,
                    "agent_id": "adaptive-context-agent",
                    "top_k": 3,
                    "include_resolver_shadow": True,
                }
            )
            selected_ids = [
                str(row.get("memory_id"))
                for row in asked.get("evidence") or []
                if row.get("memory_id")
            ]
            api.feedback(
                {
                    "label": "answer_correct",
                    "feedback_scope": "answer",
                    "query": "What does Victor prefer for grounded answers?",
                    "operation_id": asked["operation_id"],
                    "selected_memory_ids": selected_ids,
                    "answer": asked.get("answer"),
                }
            )
            api.feedback(
                {
                    "memory_id": taught["memory"]["memory_id"],
                    "label": "useful",
                    "query": "What does Victor prefer for grounded answers?",
                    "operation_id": asked["operation_id"],
                    "rank": 1,
                    "retrieval_score": asked["evidence"][0]["score"] if asked["evidence"] else None,
                }
            )
            log_path = api.outcome_logger.path
        finally:
            api.close()

        dataset = build_report([log_path])

    examples = dataset.get("examples") or []
    scopes = {item.get("feedback_scope") for item in examples}
    checks = {
        "schema_ok": dataset.get("schema") == "adaptive_context_outcome_dataset/v1",
        "dataset_ok": dataset.get("ok") is True,
        "two_examples": dataset.get("example_count") == 2,
        "has_answer_feedback": "answer" in scopes,
        "has_memory_feedback": "memory" in scopes,
        "all_adaptive_context": all(item.get("context_source") == "adaptive_memory_context" for item in examples),
        "all_have_features": all(bool(item.get("features")) for item in examples),
        "all_have_retrieval_context": all(bool(item.get("retrieval_context")) for item in examples),
        "answer_example_positive": any(
            item.get("feedback_scope") == "answer"
            and item.get("label") == "answer_correct"
            and item.get("outcome_family") == "answer_quality"
            for item in examples
        ),
        "memory_example_positive": any(
            item.get("feedback_scope") == "memory"
            and item.get("label") == "useful"
            and item.get("outcome_family") == "retrieval_positive"
            for item in examples
        ),
    }
    report = {
        "schema": "adaptive_context_outcome_dataset_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "dataset_summary": {
            "example_count": dataset.get("example_count"),
            "skipped_count": dataset.get("skipped_count"),
            "label_counts": dataset.get("label_counts"),
            "outcome_family_counts": dataset.get("outcome_family_counts"),
            "feedback_scope_counts": dataset.get("feedback_scope_counts"),
            "context_source_counts": dataset.get("context_source_counts"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Outcome Dataset Regression",
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
