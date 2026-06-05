from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.maintenance_apply_backend import apply_memory_maintenance_plan_to_sqlite  # noqa: E402


DEFAULT_PLAN = REPO_ROOT / "experiments" / "memory_maintenance_apply_plan_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_apply_operator_command_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_apply_operator_command_report.md"


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
        "# Memory Maintenance Apply Operator Command",
        "",
        "Operator-facing maintenance apply result. Defaults are dry-run and mutation-disabled.",
        "",
        f"Operation count: `{report['operation_count']}`",
        f"Applied count: `{report['applied_count']}`",
        f"Blocked count: `{report['blocked_count']}`",
        f"Dry run: `{report['dry_run']}`",
        f"Mutation enabled: `{report['mutation_enabled']}`",
        f"Operator confirmed: `{report['operator_confirmed']}`",
        "",
        "## Results",
        "",
        "| candidate | operation | applied | blocked reasons |",
        "| --- | --- | --- | --- |",
    ]
    if not report.get("results"):
        lines.append("| none | none | false | none |")
    for item in report.get("results") or []:
        lines.append(
            f"| `{clean_cell(item.get('candidate_id'), 80)}` | `{clean_cell(item.get('operation_kind'), 80)}` | "
            f"`{item.get('applied')}` | `{clean_cell(', '.join(item.get('blocked_reasons') or []), 140)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a guarded memory maintenance apply plan against a SQLite DB.")
    parser.add_argument("--db", required=True, help="SQLite memory DB path.")
    parser.add_argument("--apply-plan", default=str(DEFAULT_PLAN), help="memory_maintenance_apply_plan/v1 artifact.")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    parser.add_argument("--operator-id", default="", help="Required for audit clarity.")
    parser.add_argument("--confirm-operator", action="store_true", help="Record explicit operator confirmation.")
    parser.add_argument("--enable-mutation", action="store_true", help="Allow database mutation. Unsafe for real DBs without review.")
    parser.add_argument("--no-dry-run", action="store_true", help="Disable dry-run mode. Requires --enable-mutation to mutate.")
    parser.add_argument("--write-audit", action="store_true", help="Write audit rows to memory_maintenance_apply_audit.")
    args = parser.parse_args()

    apply_plan = load_json(Path(args.apply_plan))
    dry_run = not bool(args.no_dry_run)
    report = apply_memory_maintenance_plan_to_sqlite(
        Path(args.db),
        apply_plan,
        operator_id=args.operator_id,
        operator_confirmed=bool(args.confirm_operator),
        mutation_enabled=bool(args.enable_mutation),
        dry_run=dry_run,
        write_audit=bool(args.write_audit),
    )
    report["schema"] = "memory_maintenance_apply_operator_command_result/v1"
    report["source_apply_plan_path"] = str(Path(args.apply_plan))
    report["db_path"] = str(Path(args.db))
    report["safety_mode"] = (
        "mutation_enabled"
        if bool(args.enable_mutation) and bool(args.confirm_operator) and not dry_run
        else "report_only_or_blocked"
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report.get("schema"),
                "operation_count": report.get("operation_count"),
                "applied_count": report.get("applied_count"),
                "blocked_count": report.get("blocked_count"),
                "dry_run": report.get("dry_run"),
                "mutation_enabled": report.get("mutation_enabled"),
                "operator_confirmed": report.get("operator_confirmed"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
