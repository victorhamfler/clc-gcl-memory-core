from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_shadow_coverage_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_shadow_coverage_regression_report.md"


def retrieval_coverage_report(
    results: list[dict[str, object]],
    *,
    min_coverage: float,
    allow_low_coverage: bool,
) -> dict[str, object]:
    modes = ("base", "canonical", "ogcf", "combined")
    total = max(1, len(results))
    mode_coverage: dict[str, object] = {}
    zero_retrieval_queries: list[dict[str, object]] = []
    for mode_name in modes:
        query_counts = [
            int(((item["modes"][mode_name].get("diagnostics") or {})).get("retrieval_count") or 0)  # type: ignore[index, union-attr]
            for item in results
        ]
        covered = sum(1 for count in query_counts if count > 0)
        mode_coverage[mode_name] = {
            "covered_queries": covered,
            "query_count": len(results),
            "coverage": round(covered / total, 6),
            "min_retrieval_count": min(query_counts, default=0),
            "avg_retrieval_count": round(sum(query_counts) / total, 6),
        }
    for item_row in results:
        missing_modes = [
            mode_name
            for mode_name in modes
            if int(((item_row["modes"][mode_name].get("diagnostics") or {})).get("retrieval_count") or 0) <= 0  # type: ignore[index, union-attr]
        ]
        if missing_modes:
            zero_retrieval_queries.append(
                {
                    "query": item_row.get("query"),
                    "missing_modes": missing_modes,
                }
            )
    min_observed = min((row["coverage"] for row in mode_coverage.values()), default=0.0)  # type: ignore[index]
    ok = min_observed >= float(min_coverage)
    return {
        "ok": ok or bool(allow_low_coverage),
        "coverage_ok": ok,
        "allowed_low_coverage": bool(allow_low_coverage),
        "min_required_coverage": float(min_coverage),
        "min_observed_coverage": round(min_observed, 6),
        "mode_coverage": mode_coverage,
        "zero_retrieval_query_count": len(zero_retrieval_queries),
        "zero_retrieval_queries": zero_retrieval_queries[:20],
    }


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
