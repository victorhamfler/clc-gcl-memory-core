from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import APPLY_PLAN_SCHEMA, build_manual_apply_plan  # noqa: E402


DEFAULT_DECISIONS = REPO_ROOT / "experiments" / "memory_maintenance_manual_apply_decisions_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_apply_plan_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_apply_plan_report.md"


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
        "# Memory Maintenance Apply Plan",
        "",
        "Report-only apply plan. This artifact does not mutate the memory database.",
        "",
        f"Planned operations: `{report['planned_operation_count']}`",
        f"Blocked operations: `{report['blocked_operation_count']}`",
        f"Ready to execute: `{report['ready_to_execute_count']}`",
        f"Applied count: `{report['applied_count']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Planned Operations",
        "",
        "| candidate | operation | blocked reasons |",
        "| --- | --- | --- |",
    ]
    if not report.get("planned_operations"):
        lines.append("| none | none | none |")
    for item in report.get("planned_operations") or []:
        lines.append(
            f"| `{clean_cell(item.get('candidate_id'), 80)}` | `{clean_cell(item.get('operation_kind'), 80)}` | "
            f"`{clean_cell(', '.join(item.get('blocked_reasons') or []), 120)}` |"
        )
    lines.extend(["", "## Blocked Operations", "", "| candidate | kind | reasons |", "| --- | --- | --- |"])
    if not report.get("blocked_operations"):
        lines.append("| none | none | none |")
    for item in report.get("blocked_operations") or []:
        lines.append(
            f"| `{clean_cell(item.get('candidate_id'), 80)}` | `{clean_cell(item.get('memory_review_kind'), 80)}` | "
            f"`{clean_cell(', '.join(item.get('blocked_reasons') or []), 120)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a guarded, report-only memory maintenance apply plan.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--operator-id", default="")
    args = parser.parse_args()

    decisions = load_json(Path(args.decisions))
    report = build_manual_apply_plan(decisions, dry_run=True, operator_id=args.operator_id)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report.get("schema") == APPLY_PLAN_SCHEMA,
                "schema": report.get("schema"),
                "planned_operation_count": report.get("planned_operation_count"),
                "blocked_operation_count": report.get("blocked_operation_count"),
                "ready_to_execute_count": report.get("ready_to_execute_count"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "dry_run": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if report.get("schema") == APPLY_PLAN_SCHEMA else 1


if __name__ == "__main__":
    raise SystemExit(main())
