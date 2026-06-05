from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_copied_db_rehearsal import build_review_summary  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
OUT_JSON = OUT_DIR / "memory_maintenance_rehearsal_review_summary_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rehearsal_review_summary_regression_report.md"


def main() -> int:
    quality = {
        "operations": [
            {
                "candidate_id": "safe",
                "operation_kind": "duplicate_deprecation",
                "target_ids": ["keep", "dup"],
                "missing_ids": [],
                "exact_duplicate_target": True,
                "risk_flags": [],
            },
            {
                "candidate_id": "missing",
                "operation_kind": "duplicate_deprecation",
                "target_ids": ["keep", "missing_dup"],
                "missing_ids": ["missing_dup"],
                "exact_duplicate_target": False,
                "risk_flags": [],
            },
            {
                "candidate_id": "stale",
                "operation_kind": "duplicate_deprecation",
                "target_ids": ["current", "old"],
                "missing_ids": [],
                "exact_duplicate_target": False,
                "risk_flags": ["stale_marker", "duplicate_text_mismatch"],
            },
            {
                "candidate_id": "semantic",
                "operation_kind": "duplicate_deprecation",
                "target_ids": ["keep", "semantic"],
                "missing_ids": [],
                "exact_duplicate_target": False,
                "risk_flags": ["semantic_marker"],
            },
            {
                "candidate_id": "unsupported",
                "operation_kind": "semantic_merge",
                "target_ids": ["a", "b"],
                "missing_ids": [],
                "exact_duplicate_target": False,
                "risk_flags": [],
            },
        ]
    }
    summary = build_review_summary(quality)
    decisions = {item.get("candidate_id"): item.get("decision") for item in summary.get("reviews") or []}
    checks = {
        "schema_ok": summary.get("schema") == "memory_maintenance_rehearsal_review_summary/v1",
        "safe_label": decisions.get("safe") == "safe_to_review",
        "missing_label": decisions.get("missing") == "blocked_missing_targets",
        "stale_label": decisions.get("stale") == "blocked_stale_risk",
        "semantic_label": decisions.get("semantic") == "blocked_semantic_risk",
        "unsupported_label": decisions.get("unsupported") == "blocked_unsupported_operation",
        "overall_blocked": summary.get("overall_decision") == "blocked_or_needs_review",
        "mutation_never_allowed": summary.get("mutation_allowed") is False
        and all(item.get("mutation_allowed") is False for item in summary.get("reviews") or []),
        "counts_ok": (summary.get("decision_counts") or {}).get("safe_to_review") == 1
        and summary.get("blocked_count") == 4,
    }
    result = {
        "schema": "memory_maintenance_rehearsal_review_summary_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "summary": summary,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rehearsal Review Summary Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
