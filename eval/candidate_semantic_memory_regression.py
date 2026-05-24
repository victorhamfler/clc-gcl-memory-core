from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.candidate_semantic_memory import build_report  # noqa: E402


FIXTURES = [
    ROOT / "test_corpora" / "candidate_semantic_readiness_a.json",
    ROOT / "test_corpora" / "candidate_semantic_readiness_b.json",
]
OUT_JSON = REPO_ROOT / "experiments" / "candidate_semantic_memory_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "candidate_semantic_memory_regression_report.md"


def main() -> int:
    report = build_report(FIXTURES, similarity_threshold=0.45)
    clusters = report.get("clusters") or []
    terms_by_cluster = [set(cluster.get("terms") or []) for cluster in clusters]
    drink_cluster = next((cluster for cluster in clusters if {"drink", "morning drink"} <= set(cluster.get("terms") or [])), None)
    checks = {
        "schema_ok": report.get("schema") == "candidate_semantic_memory/v1",
        "drink_terms_clustered": drink_cluster is not None,
        "drink_cluster_semantic_ready": bool(drink_cluster and drink_cluster.get("cluster_recommendation") == "semantic_ready"),
        "server_not_in_drink_cluster": bool(drink_cluster and "server" not in set(drink_cluster.get("terms") or [])),
        "held_out_not_clustered_with_hold": all(not ({"live", "server"} <= terms) for terms in terms_by_cluster),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "fixtures": [str(path) for path in FIXTURES],
        "cluster_recommendation_counts": report.get("cluster_recommendation_counts"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Candidate Semantic Memory Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "\n".join(f"- {name}: `{ok}`" for name, ok in checks.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
