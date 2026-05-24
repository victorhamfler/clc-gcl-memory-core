from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.mine_ogcf_intent_candidates import build_report  # noqa: E402


FIXTURE = ROOT / "test_corpora" / "ogcf_intent_candidate_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_intent_candidate_miner_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_intent_candidate_miner_regression_report.md"


def terms(report: dict, family: str) -> set[str]:
    support = report.get("support") if isinstance(report.get("support"), dict) else {}
    values = support.get(family)
    return set(values or {})


def main() -> int:
    report = build_report(FIXTURE, min_support=1)
    generic_terms = {
        "bridge",
        "connects",
        "evidence",
        "memo",
        "note",
        "notes",
        "pressure",
        "review",
        "reviewed",
    }
    checks = {
        "schema_ok": report.get("schema") == "ogcf_intent_candidates/v1",
        "bridge_candidate_mined": "meshlink" in terms(report, "bridge_terms"),
        "geometry_candidate_mined": "manifolddrift" in terms(report, "geometry_terms"),
        "ordinary_suppression_candidate_mined": "lunar" in terms(report, "ordinary_fact_terms"),
        "generic_bridge_terms_filtered": not (terms(report, "bridge_terms") & generic_terms),
        "generic_geometry_terms_filtered": not (terms(report, "geometry_terms") & generic_terms),
        "generic_maintenance_terms_filtered": not (terms(report, "maintenance_terms") & generic_terms),
        "generic_ordinary_terms_filtered": not (terms(report, "ordinary_fact_terms") & generic_terms),
        "candidate_sections_present": report.get("candidate_count", 0) >= 3,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "candidate_count": report.get("candidate_count"),
        "support": report.get("support"),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# OGCF Intent Candidate Miner Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({"checks": checks}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
