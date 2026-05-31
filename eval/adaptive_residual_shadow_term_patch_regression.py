from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_shadow_term_patch_proposal import classify_term  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_regression_report.md"


CASES = {
    "deployment key": "sensitive_private",
    "hidden deployment key": "sensitive_private",
    "changed live answers": "unsupported_proof",
    "result proves": "unsupported_proof",
    "profile preference justify": "ordinary_namespace_profile",
    "justify cross-namespace": "ordinary_namespace_profile",
    "previous roadmap": "stale_previous",
    "ambiguous fragment": "review_required",
}


def build_report() -> dict[str, object]:
    before = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    rows = []
    for term, expected in CASES.items():
        actual = classify_term(term)
        rows.append({"term": term, "expected": expected, "actual": actual, "ok": actual == expected})
    after = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    checks = {
        "all_terms_classified": all(bool(row["ok"]) for row in rows),
        "config_unchanged": before == after,
        "has_review_required_bucket": any(row["actual"] == "review_required" for row in rows),
    }
    return {
        "schema": "adaptive_residual_shadow_term_patch_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "rows": rows,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, object]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Term Patch Regression\n\n"
        + f"Passed: **{report['ok']}**\n\n"
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
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
