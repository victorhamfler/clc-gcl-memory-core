from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "evidence_context_selector_runtime_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_context_selector_runtime_regression_report.md"


def build_report() -> dict:
    rows = [
        {
            "memory_id": "mem_current",
            "score": 0.82,
            "claim_scope_score": 0.80,
            "text_match_score": 0.78,
            "authority_state": "current",
            "supersession_score": 0.50,
            "relation_supersession_score": 0.35,
            "canonical_support_count": 4,
            "canonical_is_keeper": True,
        },
        "not-a-dict-row",
        {
            "memory_id": "mem_duplicate",
            "score": 0.71,
            "claim_scope_score": 0.70,
            "text_match_score": 0.68,
            "authority_state": "standalone",
            "canonical_support_count": 1,
            "canonical_is_keeper": False,
        },
        {
            "memory_id": "mem_stale",
            "score": 0.62,
            "claim_scope_score": 0.64,
            "text_match_score": 0.62,
            "authority_state": "stale",
            "supersession_score": -0.60,
            "relation_supersession_score": -0.40,
            "superseded_by_memory_ids": ["mem_current"],
            "stored_contradiction_score": 0.10,
        },
    ]
    features, diagnostics = selector_features_from_retrieval_context(
        rows,
        condition_name="standard_budget144",
    )
    checks = {
        "malformed_row_ignored": diagnostics.get("retrieval_count") == 3,
        "current_row_detected": diagnostics.get("current_rows") == 1,
        "stale_row_detected": diagnostics.get("stale_rows") == 1,
        "canonical_support_preserved": diagnostics.get("canonical_max_support_count") == 4,
        "canonical_duplicate_pressure_visible": diagnostics.get("canonical_duplicate_pressure") == 0.333333,
        "features_nonzero": features.memory_bad_rate > 0.0 and features.probe_drop > 0.0,
        "condition_preserved": features.long_stream is False,
    }
    return {
        "schema": "evidence_context_selector_runtime_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "features": features.__dict__,
        "diagnostics": diagnostics,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Evidence Context Selector Runtime Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
