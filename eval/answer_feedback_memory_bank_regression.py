from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.answer_feedback_memory_bank import build_report  # noqa: E402


FIXTURES = [
    ROOT / "test_corpora" / "answer_feedback_signals_a.json",
    ROOT / "test_corpora" / "answer_feedback_signals_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_regression_report.md"


def cluster_by_key(report: dict, key: str) -> dict:
    for cluster in report.get("clusters") or []:
        if cluster.get("key") == key:
            return cluster
    return {}


def main() -> int:
    report = build_report(FIXTURES, ready_support=2, ready_logs=2, ready_queries=1)
    answer_quality = cluster_by_key(report, "answer_quality:answer_correct")
    bridge_quality = cluster_by_key(report, "bridge_warning_quality:answer_bridge_warning_useful")
    missing_support = cluster_by_key(report, "missing_support_refusal:answer_missing_support")
    checks = {
        "schema_ok": report.get("schema") == "answer_feedback_memory_bank/v1",
        "six_signals_loaded": report.get("signal_count") == 6,
        "three_clusters": report.get("cluster_count") == 3,
        "answer_quality_ready": answer_quality.get("readiness") == "ready",
        "bridge_quality_ready": bridge_quality.get("readiness") == "ready",
        "bridge_requires_ogcf": bridge_quality.get("ogcf_signal_count") == 2,
        "missing_support_ready": missing_support.get("readiness") == "ready",
        "all_clusters_have_two_logs": all(
            cluster.get("distinct_source_logs") == 2 for cluster in report.get("clusters") or []
        ),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "readiness_counts": report.get("readiness_counts"),
        "clusters": report.get("clusters"),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Answer Feedback Memory Bank Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({"checks": checks, "readiness_counts": result["readiness_counts"]}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
