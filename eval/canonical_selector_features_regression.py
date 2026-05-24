from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "canonical_selector_features_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_selector_features_regression_report.md"


def row(
    memory_id: str,
    score: float,
    *,
    support_count: int = 1,
    is_keeper: bool = True,
    stale: bool = False,
) -> dict:
    return {
        "memory_id": memory_id,
        "score": score,
        "cosine": score,
        "text_match_score": 0.9,
        "claim_scope_score": 0.9,
        "stored_contradiction_score": 0.0,
        "supersession_score": -0.4 if stale else 0.0,
        "relation_supersession_score": -0.4 if stale else 0.0,
        "source_reliability": 0.0,
        "domain_reliability": 0.0,
        "authority_state": "superseded" if stale else "standalone",
        "canonical_support_count": support_count,
        "canonical_duplicate_count": max(0, support_count - 1),
        "canonical_is_keeper": is_keeper,
        "canonical_keeper_memory_id": memory_id if is_keeper else "keeper",
    }


def main() -> int:
    unsupported_rows = [
        row("u1", 0.72),
        row("u2", 0.68),
        row("u3", 0.64),
    ]
    supported_rows = [
        row("s1", 0.72, support_count=8, is_keeper=True),
        row("s2", 0.68),
        row("s3", 0.64),
    ]
    duplicate_clutter_rows = [
        row("k1", 0.72, support_count=8, is_keeper=True),
        row("d1", 0.68, support_count=8, is_keeper=False),
        row("d2", 0.64, support_count=8, is_keeper=False),
        row("d3", 0.62, support_count=8, is_keeper=False),
    ]
    stale_supported_rows = [
        row("stale", 0.74, support_count=8, is_keeper=True, stale=True),
        row("current_anchor", 0.70, support_count=8, is_keeper=True),
    ]

    unsupported_features, unsupported_diag = selector_features_from_retrieval_context(unsupported_rows)
    supported_features, supported_diag = selector_features_from_retrieval_context(supported_rows)
    clutter_features, clutter_diag = selector_features_from_retrieval_context(duplicate_clutter_rows)
    stale_features, stale_diag = selector_features_from_retrieval_context(stale_supported_rows)

    checks = {
        "support_signal_exposed": supported_diag["canonical_confidence_signal"] > 0.0
        and supported_diag["canonical_supported_keeper_rows"] == 1,
        "clean_support_reduces_memory_pressure": supported_features.memory_bad_rate < unsupported_features.memory_bad_rate,
        "duplicate_clutter_pressure_exposed": clutter_diag["canonical_duplicate_pressure"] >= 0.7
        and clutter_diag["canonical_nonkeeper_rows"] == 3,
        "duplicate_clutter_increases_memory_pressure": clutter_features.memory_bad_rate > supported_features.memory_bad_rate,
        "stale_context_not_overtrusted": stale_features.memory_bad_rate > supported_features.memory_bad_rate
        and stale_diag["canonical_confidence_credit"] == 0.0,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "cases": {
            "unsupported": {
                "features": unsupported_features.__dict__,
                "diagnostics": unsupported_diag,
            },
            "supported": {
                "features": supported_features.__dict__,
                "diagnostics": supported_diag,
            },
            "duplicate_clutter": {
                "features": clutter_features.__dict__,
                "diagnostics": clutter_diag,
            },
            "stale_supported": {
                "features": stale_features.__dict__,
                "diagnostics": stale_diag,
            },
        },
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical Selector Features Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
