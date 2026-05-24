from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.candidate_promotion_readiness import build_report  # noqa: E402


FIXTURES = [
    ROOT / "test_corpora" / "candidate_readiness_retrieval_a.json",
    ROOT / "test_corpora" / "candidate_readiness_evidence_a.json",
    ROOT / "test_corpora" / "candidate_readiness_evidence_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "candidate_promotion_readiness_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "candidate_promotion_readiness_regression_report.md"


def by_key(report: dict) -> dict[str, dict]:
    return {item["key"]: item for item in report.get("candidates") or []}


def main() -> int:
    report = build_report(FIXTURES)
    candidates = by_key(report)
    checks = {
        "drink_ready": candidates["evidence:sensitive_lookup:terms:drink"]["recommendation"] == "ready",
        "server_hold": candidates["evidence:sensitive_lookup:terms:server"]["recommendation"] == "hold",
        "live_held_out": candidates["evidence:held_out_sensitive_lookup:terms:live"]["recommendation"] == "held_out",
        "retrieval_marker_hold": candidates[
            "retrieval:broad_generic:source_contains:report_template_note"
        ]["recommendation"]
        == "hold",
        "recommendation_counts_present": bool(report.get("recommendation_counts")),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "fixtures": [str(path) for path in FIXTURES],
        "recommendation_counts": report.get("recommendation_counts"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Candidate Promotion Readiness Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "\n".join(f"- {name}: `{ok}`" for name, ok in checks.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
