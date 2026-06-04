from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_candidate_contract import PLAN_SCHEMA, build_review_plan  # noqa: E402


DEFAULT_GUARD = REPO_ROOT / "experiments" / "ogcf_maintenance_candidate_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_plan_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_candidate_review_plan_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def write_plan(plan: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Candidate Review Plan",
        "",
        "Report-only memory-side handoff plan. This does not mutate memory rows, retrieval, selector policy, runtime config, or learned artifacts.",
        "",
        f"Candidate count: `{plan['candidate_count']}`",
        f"Blocked count: `{plan['blocked_count']}`",
        f"Next action: `{plan['next_action']}`",
        "",
        "## Review Items",
        "",
        "| candidate | kind | action | runs | support | mean priority |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    if not plan.get("items"):
        lines.append("| none | none | none | 0 | 0 | 0 |")
    for item in plan.get("items") or []:
        lines.append(
            f"| `{clean_cell(item.get('candidate_id'), 80)}` | `{clean_cell(item.get('memory_review_kind'), 80)}` | "
            f"`{clean_cell(item.get('recommended_action'), 80)}` | {item.get('run_count')} | "
            f"{item.get('support')} | {float(item.get('mean_priority') or 0.0):.3f} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a memory-side review plan from guarded OGCF maintenance candidates.")
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    guard = json.loads(Path(args.guard).read_text(encoding="utf-8"))
    plan = build_review_plan(guard)
    write_plan(plan, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": plan.get("schema") == PLAN_SCHEMA and plan.get("source_guard_ok") is True,
                "schema": plan.get("schema"),
                "candidate_count": plan.get("candidate_count"),
                "blocked_count": plan.get("blocked_count"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if plan.get("schema") == PLAN_SCHEMA and plan.get("source_guard_ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
