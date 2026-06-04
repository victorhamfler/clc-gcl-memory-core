from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import (  # noqa: E402
    OUTCOME_SUMMARY_SCHEMA,
    build_outcome_template,
    summarize_review_outcomes,
)


DEFAULT_PLAN = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_plan_results.json"
DEFAULT_OUTCOMES = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_outcomes_template.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_review_outcome_summary_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_review_outcome_summary_report.md"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_summary(summary: dict[str, Any], template: dict[str, Any], out_json: Path, out_md: Path, template_out: Path | None) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if template_out is not None:
        template_out.write_text(json.dumps(template, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Review Outcome Summary",
        "",
        "Report-only outcome summary. This records manual review decisions but does not apply them.",
        "",
        f"Outcome count: `{summary['outcome_count']}`",
        f"Accepted: `{summary['accepted_count']}`",
        f"Blocked/rejected: `{summary['blocked_or_rejected_count']}`",
        f"Readiness: `{summary['readiness']}`",
        f"Next action: `{summary['next_action']}`",
        "",
        "## Outcome Counts",
        "",
        "```json",
        json.dumps(summary.get("outcome_counts"), indent=2),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize report-only manual outcomes for memory maintenance review-plan items.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--outcomes", default=str(DEFAULT_OUTCOMES))
    parser.add_argument("--write-template", action="store_true")
    parser.add_argument("--template-out", default=str(DEFAULT_OUTCOMES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    plan = load_json(Path(args.plan))
    template = build_outcome_template(plan)
    outcomes_path = Path(args.outcomes)
    outcomes = load_json(outcomes_path) if outcomes_path.exists() and not args.write_template else template
    summary = summarize_review_outcomes(plan, outcomes)
    write_summary(
        summary,
        template,
        Path(args.out_json),
        Path(args.out_md),
        Path(args.template_out) if args.write_template else None,
    )
    print(
        json.dumps(
            {
                "ok": summary.get("schema") == OUTCOME_SUMMARY_SCHEMA,
                "schema": summary.get("schema"),
                "outcome_count": summary.get("outcome_count"),
                "readiness": summary.get("readiness"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "template": str(Path(args.template_out)) if args.write_template else None,
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if summary.get("schema") == OUTCOME_SUMMARY_SCHEMA else 1


if __name__ == "__main__":
    raise SystemExit(main())
