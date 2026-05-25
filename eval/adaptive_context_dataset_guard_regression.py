from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_dataset_guard import build_report as build_guard_report
from eval.adaptive_context_outcome_dataset import build_report as build_dataset_report
from eval.outcome_logging_regression import build_test_api


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_dataset_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_dataset_guard_regression_report.md"


def write_dataset(path: Path, dataset: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_context_guard_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        try:
            taught = api.teach(
                {
                    "text": "Adaptive context guard regression: Victor prefers grounded evidence answers.",
                    "namespace": "agent:adaptive-context-guard",
                    "agent_id": "adaptive-context-guard-agent",
                    "source": "eval/adaptive_context_guard.md",
                    "memory_type": "preference",
                }
            )
            asked = api.ask(
                {
                    "query": "What does Victor prefer for evidence answers?",
                    "namespace": "agent:adaptive-context-guard",
                    "include_global": False,
                    "agent_id": "adaptive-context-guard-agent",
                    "top_k": 3,
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
                    "query": "What does Victor prefer for evidence answers?",
                    "operation_id": asked["operation_id"],
                    "selected_memory_ids": selected_ids,
                    "answer": asked.get("answer"),
                }
            )
            api.feedback(
                {
                    "memory_id": taught["memory"]["memory_id"],
                    "label": "useful",
                    "query": "What does Victor prefer for evidence answers?",
                    "operation_id": asked["operation_id"],
                    "rank": 1,
                    "retrieval_score": asked["evidence"][0]["score"] if asked["evidence"] else None,
                }
            )
            log_path = api.outcome_logger.path
        finally:
            api.close()

        dataset = build_dataset_report([log_path])
        dataset_path = tmp / "adaptive_context_dataset.json"
        write_dataset(dataset_path, dataset)
        guard = build_guard_report(dataset_path)

    checks = {
        "dataset_ok": dataset.get("ok") is True,
        "guard_schema_ok": guard.get("schema") == "adaptive_context_dataset_guard/v1",
        "guard_ok": guard.get("ok") is True,
        "readiness_runtime_collection": guard.get("readiness") == "ready_for_runtime_collection",
        "has_answer_feedback": guard.get("checks", {}).get("has_answer_feedback") is True,
        "has_memory_feedback": guard.get("checks", {}).get("has_memory_feedback") is True,
        "has_adaptive_context": guard.get("checks", {}).get("has_adaptive_context_example") is True,
        "no_errors": guard.get("error_count") == 0,
    }
    report = {
        "schema": "adaptive_context_dataset_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "guard_summary": {
            "readiness": guard.get("readiness"),
            "example_count": guard.get("example_count"),
            "error_count": guard.get("error_count"),
            "warning_count": guard.get("warning_count"),
            "surface_readiness": guard.get("surface_readiness"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Dataset Guard Regression",
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
