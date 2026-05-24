from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.answer_behavior_proposal_eval import build_report as build_proposals  # noqa: E402
from eval.answer_behavior_proposal_guard import build_report as build_proposal_guard  # noqa: E402
from eval.answer_behavior_shadow_eval import build_report as build_shadow  # noqa: E402
from eval.answer_feedback_bank_guard import build_report as build_bank_guard  # noqa: E402
from eval.answer_feedback_memory_bank import build_report as build_bank  # noqa: E402


SIGNAL_FIXTURES = [
    ROOT / "test_corpora" / "answer_feedback_signals_a.json",
    ROOT / "test_corpora" / "answer_feedback_signals_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_shadow_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_shadow_regression_report.md"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="answer_behavior_shadow_") as raw_tmp:
        tmp = Path(raw_tmp)
        bank_path = tmp / "bank.json"
        bank_guard_path = tmp / "bank_guard.json"
        proposals_path = tmp / "proposals.json"
        proposal_guard_path = tmp / "proposal_guard.json"

        bank = build_bank(SIGNAL_FIXTURES, ready_support=2, ready_logs=2, ready_queries=1)
        bank_path.write_text(json.dumps(bank, indent=2), encoding="utf-8")
        bank_guard = build_bank_guard(bank_path)
        bank_guard_path.write_text(json.dumps(bank_guard, indent=2), encoding="utf-8")
        proposals = build_proposals(bank_path, bank_guard_path)
        proposals_path.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
        proposal_guard = build_proposal_guard(proposals_path)
        proposal_guard_path.write_text(json.dumps(proposal_guard, indent=2), encoding="utf-8")
        shadow = build_shadow(proposals_path, proposal_guard_path)

    checks = {
        "schema_ok": shadow.get("schema") == "answer_behavior_shadow_eval/v1",
        "shadow_passed": shadow.get("ok") is True,
        "five_cases": shadow.get("case_count") == 5,
        "all_cases_pass": (shadow.get("checks") or {}).get("all_cases_pass") is True,
        "ordinary_bridge_word_suppressed": (shadow.get("checks") or {}).get("ordinary_bridge_word_suppressed") is True,
        "missing_support_refusal_preserved": (shadow.get("checks") or {}).get("missing_support_refusal_preserved")
        is True,
        "stale_conflict_disclosed": (shadow.get("checks") or {}).get("stale_conflict_disclosed") is True,
        "report_only": shadow.get("mutates_config") is False and shadow.get("mutates_runtime") is False,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "shadow_checks": shadow.get("checks"),
        "case_results": shadow.get("case_results"),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Answer Behavior Shadow Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({"checks": checks, "shadow_checks": shadow.get("checks")}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
