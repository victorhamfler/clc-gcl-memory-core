from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_candidate_profile import build_profile, write_profile  # noqa: E402
from eval.adaptive_behavior_candidate_profile_guard import build_guard, write_guard  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_guard_regression_report.md"


def fixture_calibration() -> dict:
    family_summary = {
        "missing_support": {"matches": 8, "total": 10, "match_rate": 0.8},
        "stale_conflict": {"matches": 7, "total": 10, "match_rate": 0.7},
        "supported_evidence": {"matches": 6, "total": 10, "match_rate": 0.6},
        "wrong_scope": {"matches": 10, "total": 10, "match_rate": 1.0},
    }
    mismatches = [
        {
            "behavior_family": "missing_support",
            "actual_advisory": "uncertain_keep_symbolic",
            "expected_advisory": "likely_helpful",
            "reasons": ["selected_evidence_present"],
        },
        {
            "behavior_family": "stale_conflict",
            "actual_advisory": "likely_helpful",
            "expected_advisory": "uncertain_keep_symbolic",
            "reasons": ["stale_conflict_present"],
        },
        {
            "behavior_family": "supported_evidence",
            "actual_advisory": "likely_harmful",
            "expected_advisory": "likely_helpful",
            "reasons": ["selected_evidence_low_retrieval_support"],
        },
    ]
    return {
        "schema": "adaptive_behavior_shadow_real_log_calibration/v1",
        "ok": True,
        "improvement": {"replayed_match_rate": 0.7},
        "replayed_current_runtime_logic": {
            "family_summary": family_summary,
            "mismatch_examples": mismatches,
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="adaptive_behavior_candidate_profile_") as raw_tmp:
        tmp = Path(raw_tmp)
        calibration = tmp / "calibration.json"
        profile_json = tmp / "profile.json"
        profile_md = tmp / "profile.md"
        guard_json = tmp / "guard.json"
        guard_md = tmp / "guard.md"
        calibration.write_text(json.dumps(fixture_calibration(), indent=2), encoding="utf-8")
        profile = build_profile(calibration)
        write_profile(profile, profile_json, profile_md)
        guard = build_guard(profile_json)
        write_guard(guard, guard_json, guard_md)
        checks = {
            "profile_schema": profile.get("schema") == "adaptive_behavior_candidate_profile/v1",
            "profile_report_only": profile.get("report_only") is True,
            "profile_mutates_config_false": profile.get("mutates_config") is False,
            "has_missing_support_candidate": any(
                item.get("id") == "missing_support_sensitive_lookup_boost"
                for item in profile.get("proposals") or []
            ),
            "has_stale_candidate": any(
                item.get("id") == "stale_conflict_explicit_signal_gate"
                for item in profile.get("proposals") or []
            ),
            "guard_ok": guard.get("ok") is True,
            "guard_analysis_ready": guard.get("readiness") == "analysis_ready",
        }
    report = {
        "schema": "adaptive_behavior_candidate_profile_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Behavior Candidate Profile Guard Regression\n\n"
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
