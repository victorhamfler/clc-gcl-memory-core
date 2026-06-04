from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_review_memory_bank import build_memory_bank  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
RUN1_CANDIDATES = OUT_DIR / "ogcf_maintenance_review_memory_bank_run1_candidates.json"
RUN1_LABELS = OUT_DIR / "ogcf_maintenance_review_memory_bank_run1_labels.json"
RUN2_CANDIDATES = OUT_DIR / "ogcf_maintenance_review_memory_bank_run2_candidates.json"
RUN2_LABELS = OUT_DIR / "ogcf_maintenance_review_memory_bank_run2_labels.json"
OUT_JSON = OUT_DIR / "ogcf_maintenance_review_memory_bank_regression_results.json"
OUT_MD = OUT_DIR / "ogcf_maintenance_review_memory_bank_regression_report.md"


def candidate(candidate_id: str, action: str, priority: float) -> dict:
    return {
        "id": candidate_id,
        "action": action,
        "recommendation": "review",
        "keeper_memory_id": f"keeper_{candidate_id}",
        "candidate_memory_ids": [f"candidate_{candidate_id}"],
        "support": 2,
        "confidence": min(1.0, priority),
        "maintenance_priority": {
            "schema": "ogcf_maintenance_priority/v1",
            "priority_score": priority,
            "report_only": True,
            "mutates_db": False,
        },
    }


def candidates_report(run_name: str, rows: list[dict]) -> dict:
    return {
        "schema": "ogcf_maintenance_candidates/v1",
        "description": f"fixture candidates for {run_name}",
        "candidate_count": len(rows),
        "candidates": rows,
        "maintenance_priority_summary": {
            "schema": "ogcf_maintenance_priority_summary/v1",
            "candidate_count": len(rows),
            "prioritized_candidate_count": len(rows),
            "readiness": "ready_for_review",
            "report_only": True,
            "mutates_db": False,
        },
        "report_only": True,
        "mutates_db": False,
    }


def labels(rows: list[tuple[str, str]]) -> dict:
    return {
        "schema": "ogcf_maintenance_review_labels/v1",
        "labels": [
            {
                "candidate_id": candidate_id,
                "label": label,
                "reviewer": "regression",
                "reason": "controlled multi-run maintenance review label",
            }
            for candidate_id, label in rows
        ],
        "report_only": True,
        "mutates_db": False,
    }


def write_fixture() -> list[tuple[Path, Path]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run1_candidates = candidates_report(
        "run1",
        [
            candidate("dup_alpha_r1", "exact_duplicate_group", 0.95),
            candidate("stale_beta_r1", "stale_version_candidate", 0.88),
            candidate("bridge_noise_r1", "bridge_cluster_review", 0.50),
        ],
    )
    run1_labels = labels(
        [
            ("dup_alpha_r1", "useful_review"),
            ("stale_beta_r1", "useful_review"),
            ("bridge_noise_r1", "noisy_review"),
        ]
    )
    run2_candidates = candidates_report(
        "run2",
        [
            candidate("dup_alpha_r2", "exact_duplicate_group", 0.93),
            candidate("stale_beta_r2", "stale_version_candidate", 0.86),
            candidate("semantic_hold_r2", "semantic_duplicate_group", 0.55),
        ],
    )
    run2_labels = labels(
        [
            ("dup_alpha_r2", "useful_review"),
            ("stale_beta_r2", "useful_review"),
            ("semantic_hold_r2", "needs_more_evidence"),
        ]
    )
    RUN1_CANDIDATES.write_text(json.dumps(run1_candidates, indent=2), encoding="utf-8")
    RUN1_LABELS.write_text(json.dumps(run1_labels, indent=2), encoding="utf-8")
    RUN2_CANDIDATES.write_text(json.dumps(run2_candidates, indent=2), encoding="utf-8")
    RUN2_LABELS.write_text(json.dumps(run2_labels, indent=2), encoding="utf-8")
    return [(RUN1_CANDIDATES, RUN1_LABELS), (RUN2_CANDIDATES, RUN2_LABELS)]


def main() -> int:
    report = build_memory_bank(write_fixture(), top_k=3, min_runs=2, min_useful=2)
    clusters = {cluster["key"]: cluster for cluster in report.get("clusters") or []}
    exact = clusters.get("exact_duplicate_group|useful") or {}
    stale = clusters.get("stale_version_candidate|useful") or {}
    bridge = clusters.get("bridge_cluster_review|negative") or {}
    checks = {
        "schema_ok": report.get("schema") == "ogcf_maintenance_review_memory_bank/v1",
        "report_only": report.get("report_only") is True and report.get("mutates_db") is False,
        "two_runs_loaded": report.get("run_count") == 2,
        "exact_duplicate_evidence_ready": exact.get("readiness") == "maintenance_candidate_evidence_ready",
        "stale_version_evidence_ready": stale.get("readiness") == "maintenance_candidate_evidence_ready",
        "negative_bridge_not_ready": bridge.get("readiness") == "review_negative_outcomes",
        "evidence_ready_count": int(report.get("evidence_ready_count") or 0) == 2,
        "next_action_ready_for_guard": report.get("next_action") == "prepare_guarded_maintenance_candidate_review",
        "no_high_priority_negative": not report.get("high_priority_negative_ids"),
    }
    result = {
        "schema": "ogcf_maintenance_review_memory_bank_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "memory_bank": report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Review Memory Bank Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Memory Bank Summary", "", "```json", json.dumps({
        "run_count": report.get("run_count"),
        "cluster_count": report.get("cluster_count"),
        "readiness_counts": report.get("readiness_counts"),
        "evidence_ready_count": report.get("evidence_ready_count"),
        "next_action": report.get("next_action"),
    }, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
