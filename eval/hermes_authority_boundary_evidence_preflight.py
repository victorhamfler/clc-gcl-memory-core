from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from serve import MemoryApi  # noqa: E402


SOURCE_DB = ROOT / "memory_experiment_180_best.db"
RUN_DB = REPO_ROOT / "experiments" / "hermes_authority_boundary_preflight_test.db"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_authority_boundary_evidence_preflight_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_authority_boundary_evidence_preflight_report.md"

QUERIES = [
    "What does the current gate report about learned-risk checks?",
    "How is report-only behavior confirmed in current evaluations?",
    "What is the correct interpretation of learned-risk veto outcomes?",
    "Why is policy mutation still report-only?",
    "What evidence says self-modification is blocked?",
]


def prepare_db() -> tuple[bool, str | None]:
    if not SOURCE_DB.exists():
        return False, f"Missing source DB: {SOURCE_DB}"
    RUN_DB.parent.mkdir(parents=True, exist_ok=True)
    if RUN_DB.exists():
        RUN_DB.unlink()
    shutil.copy2(SOURCE_DB, RUN_DB)
    return True, None


def ask_rows() -> list[dict[str, Any]]:
    rows = []
    ok, error = prepare_db()
    if not ok:
        return [{"query": "", "error": error, "evidence_count": 0}]
    api = MemoryApi(ROOT, db_path=RUN_DB)
    try:
        for query in QUERIES:
            answer = api.ask(
                {
                    "query": query,
                    "top_k": 8,
                    "namespace": "global",
                    "include_global": True,
                    "agent_id": "hermes-authority-boundary-preflight",
                    "include_selector_snapshot": True,
                    "include_resolver_shadow": True,
                    "include_adaptive_residual_shadow": True,
                }
            )
            evidence = answer.get("evidence") if isinstance(answer.get("evidence"), list) else []
            rows.append(
                {
                    "query": query,
                    "operation_id": answer.get("operation_id"),
                    "evidence_count": len(evidence),
                    "answer_len": len(str(answer.get("answer") or "")),
                    "selector_decision": (answer.get("selector_snapshot") or {}).get("decision")
                    if isinstance(answer.get("selector_snapshot"), dict)
                    else None,
                }
            )
    finally:
        api.close()
    return rows


def build_report() -> dict[str, Any]:
    rows = ask_rows()
    evidence_positive = [row for row in rows if int(row.get("evidence_count") or 0) > 0]
    missing_db = any(row.get("error") for row in rows)
    checks = {
        "source_db_available": not missing_db,
        "has_queries": bool(rows),
        "has_any_evidence": bool(evidence_positive),
        "has_at_least_three_evidence_positive_queries": len(evidence_positive) >= 3,
        "report_only": True,
        "no_config_mutation": True,
    }
    return {
        "schema": "hermes_authority_boundary_evidence_preflight/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "source_db": str(SOURCE_DB),
        "run_db": str(RUN_DB),
        "query_count": len(rows),
        "evidence_positive_query_count": len(evidence_positive),
        "rows": rows,
        "recommendation": "continue_full_hermes_rerun" if all(checks.values()) else "fix_db_or_retrieval_before_full_rerun",
        "report_only": True,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Hermes Authority Boundary Evidence Preflight\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Evidence-positive queries: `{report['evidence_positive_query_count']}` / `{report['query_count']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Rows\n\n```json\n"
        + json.dumps(report["rows"], indent=2)
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
                "evidence_positive": report["evidence_positive_query_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
