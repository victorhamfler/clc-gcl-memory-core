from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import APPLY_DECISION_SCHEMA, build_manual_apply_decisions  # noqa: E402


DEFAULT_PLAN = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_plan_results.json"
DEFAULT_OUTCOMES = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_outcomes_template.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_manual_apply_decisions_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_manual_apply_decisions_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Manual Apply Decisions",
        "",
        "Dry-run/manual decision artifact. This does not mutate the memory database.",
        "",
        f"Decision count: `{report['decision_count']}`",
        f"Ready for manual apply: `{report['ready_for_manual_apply_count']}`",
        f"Rejected: `{report['rejected_count']}`",
        f"Held: `{report['held_count']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Decisions",
        "",
        "| candidate | kind | outcome | decision | next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not report.get("decisions"):
        lines.append("| none | none | none | none | none |")
    for item in report.get("decisions") or []:
        lines.append(
            f"| `{clean_cell(item.get('candidate_id'), 80)}` | `{clean_cell(item.get('memory_review_kind'), 80)}` | "
            f"`{clean_cell(item.get('outcome'), 40)}` | `{clean_cell(item.get('decision'), 60)}` | "
            f"`{clean_cell(item.get('next_action'), 80)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dry-run manual apply/reject decisions for maintenance review outcomes.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--outcomes", default=str(DEFAULT_OUTCOMES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    plan = load_json(Path(args.plan))
    outcomes = load_json(Path(args.outcomes))
    report = build_manual_apply_decisions(plan, outcomes, dry_run=True)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report.get("schema") == APPLY_DECISION_SCHEMA,
                "schema": report.get("schema"),
                "decision_count": report.get("decision_count"),
                "ready_for_manual_apply_count": report.get("ready_for_manual_apply_count"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "dry_run": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if report.get("schema") == APPLY_DECISION_SCHEMA else 1


if __name__ == "__main__":
    raise SystemExit(main())
