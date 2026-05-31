from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_EVAL = REPO_ROOT / "experiments" / "adaptive_behavior_feature_override_policy_eval_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_override_policy_candidate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_override_policy_candidate_report.md"


def read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return loaded


def build_report(eval_path: Path) -> dict[str, Any]:
    source = read_json(eval_path)
    selected = source.get("selected_policy") if isinstance(source.get("selected_policy"), dict) else {}
    top = source.get("top_policies") if isinstance(source.get("top_policies"), list) else []
    best_top = top[0] if top and isinstance(top[0], dict) else {}
    if not selected:
        checks = {
            "source_schema_ok": source.get("schema") == "adaptive_behavior_feature_override_policy_eval/v1",
            "source_ok": source.get("ok") is True,
            "report_only_source": source.get("report_only") is True,
            "source_no_runtime_mutation": source.get("mutates_runtime") is False,
            "source_no_config_mutation": source.get("mutates_config") is False,
            "source_promotion_blocked": source.get("promotion_ready") is False,
            "no_selected_policy": True,
            "best_top_zero_harm": bool(best_top.get("all_holdouts_zero_harm")),
            "best_top_not_all_improving": best_top.get("all_holdouts_improve") is False,
        }
        return {
            "schema": "adaptive_behavior_override_policy_candidate/v1",
            "description": "Report-only candidate artifact for a guarded learned-residual adaptive behavior override policy.",
            "ok": all(checks.values()),
            "source_eval": str(eval_path),
            "checks": checks,
            "candidate": None,
            "blocked_candidate": {
                "reason": "no_policy_improved_all_holdouts_with_zero_harm",
                "best_top_policy_name": best_top.get("policy_name"),
                "best_top_mean_delta_vs_symbolic": best_top.get("mean_delta_vs_symbolic"),
                "best_top_min_delta_vs_symbolic": best_top.get("min_delta_vs_symbolic"),
                "best_top_total_helpful_override_count": best_top.get("total_helpful_override_count"),
                "best_top_total_harmful_override_count": best_top.get("total_harmful_override_count"),
                "best_top_all_holdouts_zero_harm": best_top.get("all_holdouts_zero_harm"),
                "best_top_all_holdouts_improve": best_top.get("all_holdouts_improve"),
            },
            "promotion_ready": False,
            "promotion_blocker": "three-holdout matrix blocked candidate promotion; needs context-filtered policy or more natural data",
            "report_only": True,
            "mutates_runtime": False,
            "mutates_config": False,
        }
    policy = selected.get("policy") if isinstance(selected.get("policy"), dict) else {}
    holdouts = [row for row in selected.get("holdouts") or [] if isinstance(row, dict)]
    checks = {
        "source_schema_ok": source.get("schema") == "adaptive_behavior_feature_override_policy_eval/v1",
        "source_ok": source.get("ok") is True,
        "selected_policy_present": bool(selected),
        "all_holdouts_zero_harm": bool(selected.get("all_holdouts_zero_harm")),
        "all_holdouts_improve": bool(selected.get("all_holdouts_improve")),
        "has_two_or_more_holdouts": len(holdouts) >= 2,
        "supported_evidence_only": policy.get("allowed_families") == ["supported_evidence"],
        "positive_rescue_only": policy.get("allowed_target") == "likely_helpful",
        "residual_threshold_safe_with_suppressors": (
            float(policy.get("residual_threshold") or 0.0) >= 0.995
            or (float(policy.get("residual_threshold") or 0.0) >= 0.70 and bool(policy.get("suppressors")))
        ),
        "has_context_suppressors": bool(policy.get("suppressors")),
        "report_only_source": source.get("report_only") is True,
        "source_no_runtime_mutation": source.get("mutates_runtime") is False,
        "source_no_config_mutation": source.get("mutates_config") is False,
        "source_promotion_blocked": source.get("promotion_ready") is False,
    }
    candidate = {
        "id": "adaptive_behavior_supported_evidence_positive_rescue_v1",
        "target_surface": "adaptive_behavior_shadow.learned_residual_override",
        "policy": policy,
        "proposal": (
            "Allow a learned residual override only for high-confidence supported-evidence false negatives "
            "where the family model changes the advisory to likely_helpful."
        ),
        "intended_effect": "rescue overly conservative symbolic supported-evidence advisories without weakening stale/scope/missing-support protections",
        "guard_requirements": [
            "report_only_candidate",
            "all_holdouts_zero_harm",
            "all_holdouts_improve",
            "supported_evidence_only",
            "positive_rescue_only",
            "residual_threshold_safe_with_suppressors",
            "context_suppressors_enabled",
            "no_runtime_or_config_mutation",
            "promotion_blocked_until_additional_natural_holdout",
        ],
        "blocked_runtime_families": ["missing_support", "stale_conflict", "wrong_scope", "ogcf_bridge_warning"],
        "context_suppressors": policy.get("suppressors") or [],
        "holdout_summary": [
            {
                "test_log": row.get("test_log"),
                "test_sample_count": row.get("test_sample_count"),
                "symbolic_match_rate": row.get("symbolic_match_rate"),
                "hybrid_match_rate": row.get("hybrid_match_rate"),
                "hybrid_delta_vs_symbolic": row.get("hybrid_delta_vs_symbolic"),
                "override_count": row.get("override_count"),
                "helpful_override_count": row.get("helpful_override_count"),
                "harmful_override_count": row.get("harmful_override_count"),
                "neutral_wrong_override_count": row.get("neutral_wrong_override_count"),
            }
            for row in holdouts
        ],
        "aggregate": {
            "mean_delta_vs_symbolic": selected.get("mean_delta_vs_symbolic"),
            "min_delta_vs_symbolic": selected.get("min_delta_vs_symbolic"),
            "total_override_count": selected.get("total_override_count"),
            "total_helpful_override_count": selected.get("total_helpful_override_count"),
            "total_harmful_override_count": selected.get("total_harmful_override_count"),
        },
        "status": "candidate_report_only",
        "auto_promote": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    return {
        "schema": "adaptive_behavior_override_policy_candidate/v1",
        "description": "Report-only candidate artifact for a guarded learned-residual adaptive behavior override policy.",
        "ok": all(checks.values()),
        "source_eval": str(eval_path),
        "checks": checks,
        "candidate": candidate,
        "promotion_ready": False,
        "promotion_blocker": "requires another independent natural Hermes holdout before runtime or config promotion",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    candidate = report.get("candidate") or {}
    blocked = report.get("blocked_candidate") or {}
    aggregate = candidate.get("aggregate") or {}
    lines = [
        "# Adaptive Behavior Override Policy Candidate",
        "",
        "This artifact is advisory only. It does not change runtime behavior, selector policy, config, memory rows, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate: `{candidate.get('id')}`",
        f"Blocked reason: `{blocked.get('reason')}`",
        f"Mean delta: `{aggregate.get('mean_delta_vs_symbolic')}`",
        f"Min delta: `{aggregate.get('min_delta_vs_symbolic')}`",
        f"Helpful overrides: `{aggregate.get('total_helpful_override_count')}`",
        f"Harmful overrides: `{aggregate.get('total_harmful_override_count')}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Policy",
        "",
        "```json",
        json.dumps(candidate.get("policy") or {}, indent=2),
        "```",
        "",
        "## Holdouts",
        "",
        "| holdout | samples | symbolic | hybrid | delta | helpful | harmful |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in candidate.get("holdout_summary") or []:
        lines.append(
            f"| `{Path(str(row.get('test_log'))).name}` | `{row.get('test_sample_count')}` | "
            f"`{row.get('symbolic_match_rate')}` | `{row.get('hybrid_match_rate')}` | "
            f"`{row.get('hybrid_delta_vs_symbolic')}` | `{row.get('helpful_override_count')}` | "
            f"`{row.get('harmful_override_count')}` |"
        )
    if blocked:
        lines.extend(
            [
                "",
                "## Blocked Candidate",
                "",
                "```json",
                json.dumps(blocked, indent=2),
                "```",
            ]
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build report-only adaptive behavior override policy candidate.")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.eval)
    write_report(report, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "json": str(args.out_json), "markdown": str(args.out_md)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
