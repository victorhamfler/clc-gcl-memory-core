from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy, suppression_reasons  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_suppressor_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_suppressor_regression_report.md"


CASES = [
    {
        "query": "Which result proves residual shadow changed live answers?",
        "expected": ["unsupported_proof_lookup_pressure"],
    },
    {
        "query": "What unsupported claim says the fifth holdout was already natural multi-day data?",
        "expected": ["unsupported_proof_lookup_pressure"],
    },
    {
        "query": "Which proof says the residual controller can now mutate live answers?",
        "expected": ["unsupported_proof_lookup_pressure"],
    },
    {
        "query": "What hidden deployment key should the selector retrieve?",
        "expected": ["sensitive_private_lookup_pressure"],
    },
    {
        "query": "Which secret credential authorizes the memory program?",
        "expected": ["sensitive_private_lookup_pressure"],
    },
    {
        "query": "Which previous roadmap said learned controllers should be promoted immediately?",
        "expected": ["stale_previous_lookup_pressure"],
    },
    {
        "query": "Which stale config value was replaced by the current one?",
        "expected": ["stale_previous_lookup_pressure"],
    },
    {
        "query": "Does a profile preference justify cross-namespace retrieval?",
        "expected": ["ordinary_namespace_profile_lookup_pressure"],
    },
    {
        "query": "Can ordinary namespace lookup bypass the residual suppressors?",
        "expected": ["ordinary_namespace_profile_lookup_pressure"],
    },
    {
        "query": "What evidence supports the current neural-symbolic selector roadmap?",
        "expected": [],
    },
    {
        "query": "How should linked feedback guide residual controller promotion?",
        "expected": [],
    },
]


def build_report() -> dict[str, object]:
    policy = load_policy(ROOT)
    rows = []
    for case in CASES:
        actual = suppression_reasons(case["query"], policy)
        expected = list(case["expected"])
        rows.append(
            {
                "query": case["query"],
                "expected": expected,
                "actual": actual,
                "ok": set(expected).issubset(set(actual)) and (bool(expected) or not actual),
            }
        )
    return {
        "schema": "adaptive_residual_shadow_suppressor_regression/v1",
        "ok": all(bool(row["ok"]) for row in rows),
        "policy_suppressors": policy.get("suppressors"),
        "policy_terms": policy.get("terms"),
        "case_count": len(rows),
        "rows": rows,
    }


def write_report(report: dict[str, object]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Residual Shadow Suppressor Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| query | expected | actual | pass |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["rows"]:  # type: ignore[index]
        query = str(row["query"]).replace("|", "\\|")
        expected = ", ".join(row["expected"])  # type: ignore[index]
        actual = ", ".join(row["actual"])  # type: ignore[index]
        lines.append(f"| {query} | `{expected}` | `{actual}` | `{row['ok']}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "cases": report["case_count"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
