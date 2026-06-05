from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rehearsal_candidate_guard import build_report  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
FIXTURE_DIR = OUT_DIR / "memory_maintenance_rehearsal_candidate_guard_fixture"
SAFE_BANK = FIXTURE_DIR / "safe_bank.json"
RISK_BANK = FIXTURE_DIR / "risk_bank.json"
OUT_JSON = OUT_DIR / "memory_maintenance_rehearsal_candidate_guard_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rehearsal_candidate_guard_regression_report.md"


def cluster(key: str, readiness: str, *, safe: int, blocked: int) -> dict:
    return {
        "schema": "memory_maintenance_rehearsal_review_memory_bank_cluster/v1",
        "key": key,
        "run_count": 2,
        "runs": [1, 2],
        "support": max(safe, blocked, 2),
        "operation_kinds": {"duplicate_deprecation": max(safe, blocked, 2)},
        "decisions": {key.split("|", 1)[1]: max(safe, blocked, 2)},
        "blocked_count": blocked,
        "safe_count": safe,
        "readiness": readiness,
        "examples": [],
    }


def write_bank(path: Path, clusters: list[dict]) -> None:
    bank = {
        "schema": "memory_maintenance_rehearsal_review_memory_bank/v1",
        "run_count": 2,
        "cluster_count": len(clusters),
        "safe_evidence_ready_count": sum(
            1 for item in clusters if item.get("readiness") == "rehearsal_safe_evidence_ready"
        ),
        "recurrent_risk_count": sum(1 for item in clusters if item.get("readiness") == "blocked_recurrent_risk"),
        "clusters": clusters,
        "report_only": True,
        "mutates_db": False,
    }
    path.write_text(json.dumps(bank, indent=2), encoding="utf-8")


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    write_bank(
        SAFE_BANK,
        [cluster("duplicate_deprecation|safe_to_review", "rehearsal_safe_evidence_ready", safe=2, blocked=0)],
    )
    write_bank(
        RISK_BANK,
        [
            cluster("duplicate_deprecation|safe_to_review", "rehearsal_safe_evidence_ready", safe=2, blocked=0),
            cluster("duplicate_deprecation|blocked_stale_risk", "blocked_recurrent_risk", safe=0, blocked=2),
        ],
    )
    safe_report = build_report(SAFE_BANK)
    risk_report = build_report(RISK_BANK)
    safe_candidate = (safe_report.get("guarded_candidates") or [{}])[0]
    risk_blocked = {
        item.get("source_cluster_key"): item for item in risk_report.get("blocked_candidates") or []
    }
    checks = {
        "safe_bank_emits_candidate": safe_report.get("operator_review_candidate_count") == 1
        and safe_report.get("blocked_count") == 0
        and safe_candidate.get("ready_for_operator_review") is True,
        "safe_candidate_non_mutating": safe_candidate.get("mutates_db") is False
        and safe_candidate.get("promotion_ready") is False,
        "risk_bank_blocks_all_duplicate_family": risk_report.get("operator_review_candidate_count") == 0
        and risk_report.get("blocked_count") == 2
        and "duplicate_deprecation" in (risk_report.get("risky_operation_kinds") or []),
        "safe_cluster_blocked_by_family_risk": "operation_family_has_recurrent_risk"
        in ((risk_blocked.get("duplicate_deprecation|safe_to_review") or {}).get("blocked_reasons") or []),
        "risk_cluster_blocked_not_safe_ready": "not_safe_evidence_ready"
        in ((risk_blocked.get("duplicate_deprecation|blocked_stale_risk") or {}).get("blocked_reasons") or []),
        "reports_non_mutating": safe_report.get("mutates_db") is False
        and risk_report.get("mutates_db") is False
        and safe_report.get("report_only") is True
        and risk_report.get("report_only") is True,
    }
    result = {
        "schema": "memory_maintenance_rehearsal_candidate_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "safe_report": safe_report,
        "risk_report": risk_report,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Rehearsal Candidate Guard Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
