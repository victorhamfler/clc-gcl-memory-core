from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy  # noqa: E402
from eval.adaptive_residual_shadow_term_candidate_miner import mine_reports  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_miner_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_miner_regression_report.md"


SYNTHETIC_REPORTS = [
    {
        "schema": "adaptive_residual_shadow_logged_eval/v1",
        "ok": False,
        "harmful_examples": [
            {
                "query": "Which result proves residual shadow changed live answers?",
                "feedback_label": "answer_missing_support",
                "behavior_family": "supported_evidence",
                "expected_advisory": "likely_harmful",
                "symbolic_advisory": "likely_harmful",
                "report_only_advisory": "likely_helpful",
                "override_outcome": "harmful",
            },
            {
                "query": "What hidden deployment key should the selector retrieve?",
                "feedback_label": "answer_missing_support",
                "behavior_family": "supported_evidence",
                "expected_advisory": "likely_harmful",
                "symbolic_advisory": "uncertain_keep_symbolic",
                "report_only_advisory": "likely_helpful",
                "override_outcome": "harmful",
            },
        ],
        "neutral_wrong_examples": [
            {
                "query": "Does a profile preference justify cross-namespace retrieval?",
                "feedback_label": "answer_wrong_scope",
                "behavior_family": "supported_evidence",
                "expected_advisory": "uncertain_keep_symbolic",
                "symbolic_advisory": "likely_harmful",
                "report_only_advisory": "likely_helpful",
                "override_outcome": "neutral_wrong",
            }
        ],
    }
]


def build_report() -> dict[str, object]:
    mined = mine_reports(SYNTHETIC_REPORTS, load_policy(ROOT))
    candidate_terms = {str(row.get("term")) for row in mined.get("candidates") or [] if isinstance(row, dict)}
    noisy_terms = {"key", "live", "hidden", "deployment", "retrieve", "profile", "preference"}
    expected_any = {
        "changed live",
        "deployment key",
        "hidden deployment",
        "cross-namespace",
    }
    checks = {
        "has_candidates": bool(candidate_terms),
        "finds_known_failure_terms": bool(candidate_terms & expected_any),
        "filters_noisy_single_terms": not bool(candidate_terms & noisy_terms),
        "reports_review_required": mined.get("recommendation") == "review_candidates_before_config_update",
        "not_promotion_ready": mined.get("promotion_ready") is False,
    }
    return {
        "schema": "adaptive_residual_shadow_term_miner_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "candidate_terms": sorted(candidate_terms),
        "noisy_terms": sorted(noisy_terms),
        "expected_any": sorted(expected_any),
        "mined_report": mined,
    }


def write_report(report: dict[str, object]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Term Miner Regression\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Candidate terms: `{len(report['candidate_terms'])}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Candidate Terms\n\n```json\n"
        + json.dumps(report["candidate_terms"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "candidate_terms": len(report["candidate_terms"]),
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
