from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.canonical_ogcf_production_shadow_eval import retrieval_coverage_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_shadow_coverage_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_shadow_coverage_regression_report.md"


def mode(retrieval_count: int) -> dict[str, object]:
    return {
        "diagnostics": {"retrieval_count": retrieval_count},
        "decision": {"action": "PROTECT_PERIODIC"},
        "features": {"memory_bad_rate": 0.18, "probe_drop": 0.04, "csd_ratio": 0.75},
    }


def item(query: str, retrieval_count: int) -> dict[str, object]:
    return {
        "query": query,
        "modes": {
            "base": mode(retrieval_count),
            "canonical": mode(retrieval_count),
            "ogcf": mode(retrieval_count),
            "combined": mode(retrieval_count),
        },
    }


def main() -> int:
    clean = retrieval_coverage_report(
        [item("supported memory query", 8), item("bridge memory query", 6)],
        min_coverage=0.8,
        allow_low_coverage=False,
    )
    missing_namespace = retrieval_coverage_report(
        [item("supported memory query", 0), item("bridge memory query", 0)],
        min_coverage=0.8,
        allow_low_coverage=False,
    )
    allowed_missing = retrieval_coverage_report(
        [item("supported memory query", 0), item("bridge memory query", 0)],
        min_coverage=0.8,
        allow_low_coverage=True,
    )
    checks = {
        "clean_passes": clean["ok"] is True and clean["coverage_ok"] is True,
        "missing_namespace_fails": missing_namespace["ok"] is False
        and missing_namespace["coverage_ok"] is False
        and missing_namespace["zero_retrieval_query_count"] == 2,
        "explicit_allow_is_warning_only": allowed_missing["ok"] is True
        and allowed_missing["coverage_ok"] is False
        and allowed_missing["allowed_low_coverage"] is True,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "clean": clean,
        "missing_namespace": missing_namespace,
        "allowed_missing": allowed_missing,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical + OGCF Shadow Coverage Regression\n\n"
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
