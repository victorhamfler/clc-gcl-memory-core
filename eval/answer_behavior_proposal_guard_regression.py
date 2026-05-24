from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.answer_behavior_proposal_eval import build_report as build_proposals  # noqa: E402
from eval.answer_behavior_proposal_guard import build_report as build_guard  # noqa: E402
from eval.answer_feedback_bank_guard import build_report as build_bank_guard  # noqa: E402
from eval.answer_feedback_memory_bank import build_report as build_bank  # noqa: E402


SIGNAL_FIXTURES = [
    ROOT / "test_corpora" / "answer_feedback_signals_a.json",
    ROOT / "test_corpora" / "answer_feedback_signals_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="answer_behavior_proposal_guard_") as raw_tmp:
        tmp = Path(raw_tmp)
        bank_path = tmp / "bank.json"
        bank_guard_path = tmp / "bank_guard.json"
        proposals_path = tmp / "proposals.json"

        bank = build_bank(SIGNAL_FIXTURES, ready_support=2, ready_logs=2, ready_queries=1)
        bank_path.write_text(json.dumps(bank, indent=2), encoding="utf-8")
        bank_guard = build_bank_guard(bank_path)
        bank_guard_path.write_text(json.dumps(bank_guard, indent=2), encoding="utf-8")
        proposals = build_proposals(bank_path, bank_guard_path)
        proposals_path.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
        guard = build_guard(proposals_path)

    statuses = {item.get("target_behavior"): item.get("status") for item in guard.get("guarded_proposals") or []}
    checks = {
        "schema_ok": guard.get("schema") == "answer_behavior_proposal_guard/v1",
        "guard_passed": guard.get("ok") is True,
        "three_proposals": guard.get("proposal_count") == 3,
        "no_errors": guard.get("error_count") == 0,
        "supported_answer_guarded": statuses.get("supported_answer_quality") == "guarded_ready",
        "bridge_warning_guarded": statuses.get("bridge_warning_disclosure") == "guarded_ready",
        "missing_support_guarded": statuses.get("missing_support_refusal") == "guarded_ready",
        "report_only": (guard.get("checks") or {}).get("all_proposals_report_only") is True,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "guard_checks": guard.get("checks"),
        "guarded_proposals": guard.get("guarded_proposals"),
        "issues": guard.get("issues"),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Answer Behavior Proposal Guard Regression\n\n"
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
