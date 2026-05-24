from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.answer_feedback_bank_guard import build_report as build_guard_report  # noqa: E402
from eval.answer_feedback_memory_bank import build_report as build_bank_report  # noqa: E402


SIGNAL_FIXTURES = [
    ROOT / "test_corpora" / "answer_feedback_signals_a.json",
    ROOT / "test_corpora" / "answer_feedback_signals_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "answer_feedback_bank_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_feedback_bank_guard_regression_report.md"


def main() -> int:
    bank = build_bank_report(SIGNAL_FIXTURES, ready_support=2, ready_logs=2, ready_queries=1)
    with tempfile.TemporaryDirectory(prefix="answer_feedback_bank_guard_") as raw_tmp:
        bank_path = Path(raw_tmp) / "answer_feedback_memory_bank.json"
        bank_path.write_text(json.dumps(bank, indent=2), encoding="utf-8")
        guard = build_guard_report(bank_path)

    checks = {
        "schema_ok": guard.get("schema") == "answer_feedback_bank_guard/v1",
        "guard_passed": guard.get("ok") is True,
        "three_ready_clusters": guard.get("ready_cluster_count") == 3,
        "no_errors": guard.get("error_count") == 0,
        "bridge_guard_passed": (guard.get("checks") or {}).get("bridge_ready_requires_ogcf") is True,
        "supported_answer_guard_passed": (guard.get("checks") or {}).get("supported_answer_ready_requires_evidence") is True,
        "missing_support_guard_passed": (guard.get("checks") or {}).get("missing_support_refusal_guarded") is True,
        "report_only_guard_passed": (guard.get("checks") or {}).get("report_only_no_runtime_mutation") is True,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "guard_checks": guard.get("checks"),
        "ready_clusters": guard.get("ready_clusters"),
        "issues": guard.get("issues"),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Answer Feedback Bank Guard Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({"checks": checks, "guard_checks": guard.get("checks")}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
