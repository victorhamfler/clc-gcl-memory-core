from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_profile_memory_bank import build_bank, write_bank  # noqa: E402
from eval.adaptive_behavior_profile_memory_bank_guard import build_guard, write_guard  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_guard_regression_report.md"


def profile(path: Path, *, source: str, status: str) -> None:
    data = {
        "schema": "adaptive_behavior_candidate_profile/v1",
        "source_calibration": source,
        "source_match_rate": 0.86,
        "proposal_count": 1,
        "proposals": [
            {
                "id": "stale_conflict_explicit_signal_gate",
                "behavior_family": "stale_conflict",
                "status": status,
                "rationale": "Fixture recurring stale-conflict candidate.",
                "evidence": {"family_match_rate": 0.82, "mismatch_count": 2},
                "suggested_profile_delta": {"stale_conflict.requires_explicit_stale_signal": True},
                "report_only": True,
                "mutates_config": False,
                "mutates_runtime": False,
                "requires_guard_before_promotion": True,
            }
        ],
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
        "requires_guard_before_promotion": True,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_behavior_profile_bank_") as raw_tmp:
        tmp = Path(raw_tmp)
        p1 = tmp / "profile_a.json"
        p2 = tmp / "profile_b.json"
        bank_json = tmp / "bank.json"
        bank_md = tmp / "bank.md"
        guard_json = tmp / "guard.json"
        guard_md = tmp / "guard.md"
        profile(p1, source="log_a.jsonl", status="candidate")
        profile(p2, source="log_b.jsonl", status="candidate")
        bank = build_bank([p1, p2], ready_profiles=2, candidate_profiles=2)
        write_bank(bank, bank_json, bank_md)
        guard = build_guard(bank_json)
        write_guard(guard, guard_json, guard_md)
        checks = {
            "bank_schema": bank.get("schema") == "adaptive_behavior_profile_memory_bank/v1",
            "bank_report_only": bank.get("report_only") is True,
            "has_recurrence_ready": bank.get("readiness_counts", {}).get("recurrence_ready") == 1,
            "guard_ok": guard.get("ok") is True,
            "guard_analysis_ready": guard.get("readiness") == "analysis_ready",
            "ready_cluster_count": guard.get("ready_cluster_count") == 1,
        }
    report = {
        "schema": "adaptive_behavior_profile_memory_bank_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Profile Memory Bank Guard Regression\n\n"
        f"Passed: **{report['ok']}**\n\n"
        "```json\n"
        + json.dumps(checks, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
