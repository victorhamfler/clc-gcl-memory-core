from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def build_guard(profile_path: Path) -> dict[str, Any]:
    profile = read_json(profile_path)
    issues: list[dict[str, Any]] = []
    proposals = profile.get("proposals") if isinstance(profile.get("proposals"), list) else []

    if profile.get("schema") != "adaptive_behavior_candidate_profile/v1":
        issues.append({"severity": "error", "reason": "bad_schema", "value": profile.get("schema")})
    if profile.get("source_calibration_schema") != "adaptive_behavior_shadow_real_log_calibration/v1":
        issues.append(
            {
                "severity": "error",
                "reason": "bad_source_calibration_schema",
                "value": profile.get("source_calibration_schema"),
            }
        )
    for key in ("report_only", "requires_guard_before_promotion"):
        if profile.get(key) is not True:
            issues.append({"severity": "error", "reason": f"profile_{key}_not_true"})
    for key in ("mutates_config", "mutates_runtime"):
        if profile.get(key) is not False:
            issues.append({"severity": "error", "reason": f"profile_{key}_not_false"})
    if not proposals:
        issues.append({"severity": "warning", "reason": "no_candidate_proposals"})

    for item in proposals:
        if not isinstance(item, dict):
            issues.append({"severity": "error", "reason": "proposal_not_object"})
            continue
        proposal_id = item.get("id")
        if not proposal_id:
            issues.append({"severity": "error", "reason": "proposal_missing_id"})
        if item.get("report_only") is not True:
            issues.append({"severity": "error", "reason": "proposal_not_report_only", "id": proposal_id})
        if item.get("requires_guard_before_promotion") is not True:
            issues.append({"severity": "error", "reason": "proposal_missing_guard_requirement", "id": proposal_id})
        if item.get("mutates_config") is not False or item.get("mutates_runtime") is not False:
            issues.append({"severity": "error", "reason": "proposal_mutation_flag", "id": proposal_id})
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        if "family_match_rate" not in evidence:
            issues.append({"severity": "warning", "reason": "proposal_missing_match_rate", "id": proposal_id})
        delta = item.get("suggested_profile_delta")
        if not isinstance(delta, dict) or not delta:
            issues.append({"severity": "warning", "reason": "proposal_missing_suggested_delta", "id": proposal_id})
        if any(key in item for key in ("runtime_config_patch", "apply_to_config", "auto_promote")):
            issues.append({"severity": "error", "reason": "proposal_contains_promotion_field", "id": proposal_id})

    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    return {
        "schema": "adaptive_behavior_candidate_profile_guard/v1",
        "ok": not errors,
        "readiness": "analysis_ready" if not errors else "blocked",
        "profile": str(profile_path),
        "proposal_count": len(proposals),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }


def write_guard(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Candidate Profile Guard",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Proposal count: `{report['proposal_count']}`",
        f"Errors: `{report['error_count']}`",
        f"Warnings: `{report['warning_count']}`",
        "",
        "## Issues",
        "",
        "```json",
        json.dumps(report["issues"], indent=2),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard report-only adaptive behavior candidate profile artifacts.")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_guard(args.profile)
    write_guard(report, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "json": str(args.out_json)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
