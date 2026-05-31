from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_CANDIDATE = REPO_ROOT / "experiments" / "adaptive_behavior_override_policy_candidate_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_override_policy_candidate_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_override_policy_candidate_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return loaded


def numeric(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_report(candidate_path: Path) -> dict[str, Any]:
    artifact = read_json(candidate_path)
    candidate = artifact.get("candidate") if isinstance(artifact.get("candidate"), dict) else {}
    blocked = artifact.get("blocked_candidate") if isinstance(artifact.get("blocked_candidate"), dict) else {}
    if not candidate and blocked:
        checks = {
            "schema_ok": artifact.get("schema") == "adaptive_behavior_override_policy_candidate/v1",
            "source_candidate_artifact_ok": artifact.get("ok") is True,
            "artifact_report_only": artifact.get("report_only") is True,
            "no_runtime_mutation": artifact.get("mutates_runtime") is False,
            "no_config_mutation": artifact.get("mutates_config") is False,
            "promotion_blocked": artifact.get("promotion_ready") is False,
            "blocked_reason_present": bool(blocked.get("reason")),
            "blocked_top_zero_harm": blocked.get("best_top_all_holdouts_zero_harm") is True,
            "blocked_top_not_all_improving": blocked.get("best_top_all_holdouts_improve") is False,
        }
        return {
            "schema": "adaptive_behavior_override_policy_candidate_guard/v1",
            "description": "Report-only safety guard for adaptive behavior learned-residual override policy candidates.",
            "ok": all(checks.values()),
            "candidate_path": str(candidate_path),
            "checks": checks,
            "readiness": "blocked_no_three_holdout_candidate",
            "candidate_id": None,
            "blocked_candidate": blocked,
            "policy": None,
            "aggregate": {},
            "holdout_summary": [],
            "promotion_ready": False,
            "promotion_blocker": "no policy improved all three holdouts with zero harm",
            "report_only": True,
            "mutates_runtime": False,
            "mutates_config": False,
        }
    policy = candidate.get("policy") if isinstance(candidate.get("policy"), dict) else {}
    aggregate = candidate.get("aggregate") if isinstance(candidate.get("aggregate"), dict) else {}
    holdouts = [row for row in candidate.get("holdout_summary") or [] if isinstance(row, dict)]
    checks = {
        "schema_ok": artifact.get("schema") == "adaptive_behavior_override_policy_candidate/v1",
        "source_candidate_ok": artifact.get("ok") is True,
        "artifact_report_only": artifact.get("report_only") is True,
        "candidate_report_only_status": candidate.get("status") == "candidate_report_only",
        "no_runtime_mutation": artifact.get("mutates_runtime") is False and candidate.get("mutates_runtime") is False,
        "no_config_mutation": artifact.get("mutates_config") is False and candidate.get("mutates_config") is False,
        "no_auto_promote": candidate.get("auto_promote") is False,
        "promotion_blocked": artifact.get("promotion_ready") is False,
        "has_two_or_more_holdouts": len(holdouts) >= 2,
        "all_holdouts_improve": all(numeric(row.get("hybrid_delta_vs_symbolic")) > 0.0 for row in holdouts),
        "all_holdouts_zero_harm": all(int(row.get("harmful_override_count") or 0) == 0 for row in holdouts),
        "has_helpful_overrides": int(aggregate.get("total_helpful_override_count") or 0) > 0,
        "zero_total_harmful": int(aggregate.get("total_harmful_override_count") or 0) == 0,
        "supported_evidence_only": policy.get("allowed_families") == ["supported_evidence"],
        "positive_rescue_only": policy.get("allowed_target") == "likely_helpful",
        "has_context_suppressors": bool(policy.get("suppressors")),
        "residual_threshold_safe_with_suppressors": (
            numeric(policy.get("residual_threshold")) >= 0.995
            or (numeric(policy.get("residual_threshold")) >= 0.70 and bool(policy.get("suppressors")))
        ),
        "blocked_other_families": set(candidate.get("blocked_runtime_families") or []) >= {
            "missing_support",
            "stale_conflict",
            "wrong_scope",
            "ogcf_bridge_warning",
        },
    }
    readiness = "guarded_report_only_candidate" if all(checks.values()) else "blocked"
    return {
        "schema": "adaptive_behavior_override_policy_candidate_guard/v1",
        "description": "Report-only safety guard for adaptive behavior learned-residual override policy candidates.",
        "ok": all(checks.values()),
        "candidate_path": str(candidate_path),
        "checks": checks,
        "readiness": readiness,
        "candidate_id": candidate.get("id"),
        "policy": policy,
        "aggregate": aggregate,
        "holdout_summary": holdouts,
        "promotion_ready": False,
        "promotion_blocker": "guarded report-only candidate; requires another natural holdout before runtime/config promotion",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Override Policy Candidate Guard",
        "",
        "This guard is advisory only. It does not change runtime behavior, selector policy, config, memory rows, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Candidate: `{report.get('candidate_id')}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard report-only adaptive behavior override policy candidate.")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.candidate)
    write_report(report, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "json": str(args.out_json)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
