from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_shadow_term_patch_proposal import build_proposal  # noqa: E402
from eval.adaptive_residual_shadow_multi_log_eval import discover_logs  # noqa: E402


DEFAULT_LOG_GLOB = "adaptive_residual_shadow_*_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_guard_report.md"


def count_grouped_terms(groups: dict[str, Any]) -> int:
    return sum(len(value) for value in groups.values() if isinstance(value, list))


def build_guard_report(proposal: dict[str, Any]) -> dict[str, Any]:
    append_terms = proposal.get("proposed_term_groups") if isinstance(proposal.get("proposed_term_groups"), dict) else {}
    review_required = proposal.get("review_required") if isinstance(proposal.get("review_required"), list) else []
    append_count = count_grouped_terms(append_terms)
    checks = {
        "proposal_ok": bool(proposal.get("ok")),
        "proposal_report_only": proposal.get("report_only") is True,
        "proposal_does_not_mutate_config": proposal.get("mutates_config") is False,
        "proposal_does_not_mutate_runtime": proposal.get("mutates_runtime") is False,
        "no_ambiguous_terms_for_auto_apply": not review_required,
        "manual_review_required_for_new_terms": append_count == 0,
    }
    no_action_needed = append_count == 0 and not review_required
    return {
        "schema": "adaptive_residual_shadow_term_patch_guard/v1",
        "description": "Guard review-only suppressor patch proposals before any manual config application.",
        "ok": all(checks.values()),
        "checks": checks,
        "append_term_count": append_count,
        "review_required_count": len(review_required),
        "no_action_needed": no_action_needed,
        "manual_review_required": append_count > 0 or bool(review_required),
        "promotion_ready": False,
        "proposal_summary": {
            "miner_recommendation": proposal.get("miner_recommendation"),
            "candidate_count": proposal.get("candidate_count"),
            "append_terms": append_terms,
            "already_configured": proposal.get("already_configured"),
            "review_required": review_required,
        },
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Residual Shadow Term Patch Guard\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Append terms: `{report['append_term_count']}`\n"
        + f"Review required terms: `{report['review_required_count']}`\n"
        + f"No action needed: `{report['no_action_needed']}`\n"
        + f"Manual review required: `{report['manual_review_required']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Proposal Summary\n\n```json\n"
        + json.dumps(report["proposal_summary"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard a review-only residual suppressor patch proposal.")
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--log-glob", default=DEFAULT_LOG_GLOB)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    logs = [Path(item) for item in args.log] if args.log else discover_logs(args.log_glob)
    logs = [log for log in logs if log.exists() and log.is_file()]
    proposal = build_proposal(logs)
    report = build_guard_report(proposal)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "append_terms": report["append_term_count"],
                "manual_review_required": report["manual_review_required"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
