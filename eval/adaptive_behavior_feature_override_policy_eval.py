from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_cross_log_holdout import DEFAULT_TRAIN_LOGS, read_logs  # noqa: E402
from eval.adaptive_behavior_feature_scorer_eval import FEATURE_KEYS, accuracy, family_summary  # noqa: E402
from eval.adaptive_behavior_feature_scorer_hybrid_eval import (  # noqa: E402
    family_predict,
    residual_predict,
    summarize_residual,
    train_family_models,
    train_residual_model,
)


DEFAULT_TEST_LOGS = [
    Path(r"\\wsl.localhost\Ubuntu\home\victo\experiments_hermes\hermes_feature_residual_real_outcomes.jsonl"),
    REPO_ROOT / "experiments" / "adaptive_behavior_shadow_second_holdout_outcomes.jsonl",
    REPO_ROOT / "experiments" / "adaptive_behavior_shadow_third_holdout_outcomes.jsonl",
]
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_override_policy_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_override_policy_eval_report.md"


def parse_float_grid(raw: str) -> list[float]:
    values = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if item:
            values.append(round(float(item), 6))
    return values or [0.70, 0.80, 0.90, 0.95, 0.98, 0.99, 0.995, 0.999]


def policy_name(policy: dict[str, Any]) -> str:
    families = ",".join(policy["allowed_families"])
    suppressors = ",".join(policy.get("suppressors") or ["none"])
    return (
        f"res{policy['residual_threshold']}_fam{policy['family_confidence_threshold']}_"
        f"{families}_{policy['allowed_target']}_suppress_{suppressors}"
    )


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


SENSITIVE_PRIVATE_TERMS = (
    "api key",
    "bank pin",
    "database password",
    "deployment password",
    "hostname",
    "identity number",
    "passport",
    "password",
    "personal identity",
    "private",
    "recovery phrase",
    "secret",
    "token",
    "unlogged",
    "unrecorded",
)
STALE_PREVIOUS_TERMS = (
    "old",
    "previous",
    "before the correction",
    "before the update",
    "still valid",
    "still be used",
)
ORDINARY_NAMESPACE_PROFILE_TERMS = (
    "ordinary profile",
    "profile lookup",
    "cross namespaces",
    "namespace crossing",
)


def suppression_reasons(sample: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    text = normalize_text(sample.get("query"))
    suppressors = set(policy.get("suppressors") or [])
    reasons = []
    if "sensitive_private" in suppressors and contains_any(text, SENSITIVE_PRIVATE_TERMS):
        reasons.append("sensitive_private_lookup_pressure")
    if "stale_previous" in suppressors and contains_any(text, STALE_PREVIOUS_TERMS):
        reasons.append("stale_previous_lookup_pressure")
    if "ordinary_namespace_profile" in suppressors and contains_any(text, ORDINARY_NAMESPACE_PROFILE_TERMS):
        reasons.append("ordinary_namespace_profile_lookup_pressure")
    return reasons


def evaluate_policy(
    samples: list[dict[str, Any]],
    family_models: dict[str, dict[str, Any]],
    residual_model: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for sample in samples:
        family_advisory, family_confidence, family_source = family_predict(family_models, sample)
        residual_label, residual_confidence = residual_predict(residual_model, sample)
        hybrid_advisory = sample["symbolic_advisory"]
        hybrid_source = "symbolic"
        suppressed = suppression_reasons(sample, policy)
        if (
            residual_label == "symbolic_wrong"
            and residual_confidence >= policy["residual_threshold"]
            and family_confidence >= policy["family_confidence_threshold"]
            and family_source == "family_model"
            and str(sample.get("behavior_family") or "") in policy["allowed_families"]
            and family_advisory == policy["allowed_target"]
            and not suppressed
        ):
            hybrid_advisory = family_advisory
            hybrid_source = "family_override"
        rows.append(
            {
                **sample,
                "family_advisory": family_advisory,
                "family_confidence": family_confidence,
                "family_source": family_source,
                "residual_prediction": residual_label,
                "residual_confidence": residual_confidence,
                "hybrid_advisory": hybrid_advisory,
                "hybrid_source": hybrid_source,
                "suppression_reasons": suppressed,
            }
        )
    overrides = [row for row in rows if row.get("hybrid_source") == "family_override"]
    helpful = [row for row in overrides if row.get("hybrid_advisory") == row.get("expected_advisory")]
    harmful = [
        row
        for row in overrides
        if row.get("symbolic_advisory") == row.get("expected_advisory")
        and row.get("hybrid_advisory") != row.get("expected_advisory")
    ]
    neutral_wrong = [
        row
        for row in overrides
        if row.get("symbolic_advisory") != row.get("expected_advisory")
        and row.get("hybrid_advisory") != row.get("expected_advisory")
    ]
    symbolic_rate = accuracy(rows, "symbolic_advisory")
    hybrid_rate = accuracy(rows, "hybrid_advisory")
    return {
        "policy": policy,
        "policy_name": policy_name(policy),
        "symbolic_match_rate": symbolic_rate,
        "hybrid_match_rate": hybrid_rate,
        "hybrid_delta_vs_symbolic": round(hybrid_rate - symbolic_rate, 6),
        "override_count": len(overrides),
        "helpful_override_count": len(helpful),
        "harmful_override_count": len(harmful),
        "neutral_wrong_override_count": len(neutral_wrong),
        "residual_summary": summarize_residual(rows),
        "family_summary_hybrid": family_summary(rows, "hybrid_advisory"),
        "harmful_examples": compact_examples(harmful),
        "helpful_examples": compact_examples(helpful),
    }


def compact_examples(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {
            "query": row.get("query"),
            "behavior_family": row.get("behavior_family"),
            "expected_advisory": row.get("expected_advisory"),
            "symbolic_advisory": row.get("symbolic_advisory"),
            "family_advisory": row.get("family_advisory"),
            "hybrid_advisory": row.get("hybrid_advisory"),
            "family_confidence": row.get("family_confidence"),
            "residual_confidence": row.get("residual_confidence"),
            "suppression_reasons": row.get("suppression_reasons"),
        }
        for row in rows[:limit]
    ]


def build_policies(residual_grid: list[float], family_grid: list[float]) -> list[dict[str, Any]]:
    policies = []
    family_sets = [
        ["supported_evidence"],
        ["supported_evidence", "stale_conflict"],
        ["supported_evidence", "wrong_scope"],
        ["supported_evidence", "missing_support"],
    ]
    suppressor_sets = [
        [],
        ["sensitive_private"],
        ["stale_previous"],
        ["ordinary_namespace_profile"],
        ["sensitive_private", "stale_previous"],
        ["sensitive_private", "ordinary_namespace_profile"],
        ["stale_previous", "ordinary_namespace_profile"],
        ["sensitive_private", "stale_previous", "ordinary_namespace_profile"],
    ]
    for residual_threshold in residual_grid:
        for family_confidence_threshold in family_grid:
            for allowed_families in family_sets:
                for suppressors in suppressor_sets:
                    policies.append(
                        {
                            "residual_threshold": residual_threshold,
                            "family_confidence_threshold": family_confidence_threshold,
                            "allowed_families": allowed_families,
                            "allowed_target": "likely_helpful",
                            "suppressors": suppressors,
                        }
                    )
    return policies


def best_policy(policy_reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for report in policy_reports:
        holdouts = report.get("holdouts") or []
        if not holdouts:
            continue
        if any(int(row.get("harmful_override_count") or 0) > 0 for row in holdouts):
            continue
        if any(float(row.get("hybrid_delta_vs_symbolic") or 0.0) <= 0.0 for row in holdouts):
            continue
        candidates.append(report)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda report: (
            float(report.get("mean_delta_vs_symbolic") or 0.0),
            int(report.get("total_helpful_override_count") or 0),
            -int(report.get("total_override_count") or 0),
        ),
    )


def build_report(
    train_logs: list[Path],
    test_logs: list[Path],
    residual_grid: list[float],
    family_grid: list[float],
) -> dict[str, Any]:
    train_samples, train_counts = read_logs(train_logs)
    family_models = train_family_models(train_samples)
    residual_model = train_residual_model(train_samples)
    policies = build_policies(residual_grid, family_grid)
    policy_reports = []
    test_counts = {}
    for policy in policies:
        holdouts = []
        for test_log in test_logs:
            samples, counts = read_logs([test_log])
            test_counts.update(counts)
            holdout = evaluate_policy(samples, family_models, residual_model, policy)
            holdout["test_log"] = str(test_log)
            holdout["test_sample_count"] = len(samples)
            holdouts.append(holdout)
        deltas = [float(row.get("hybrid_delta_vs_symbolic") or 0.0) for row in holdouts]
        policy_reports.append(
            {
                "policy": policy,
                "policy_name": policy_name(policy),
                "holdouts": holdouts,
                "mean_delta_vs_symbolic": round(sum(deltas) / len(deltas), 6) if deltas else 0.0,
                "min_delta_vs_symbolic": round(min(deltas), 6) if deltas else 0.0,
                "total_override_count": sum(int(row.get("override_count") or 0) for row in holdouts),
                "total_helpful_override_count": sum(int(row.get("helpful_override_count") or 0) for row in holdouts),
                "total_harmful_override_count": sum(int(row.get("harmful_override_count") or 0) for row in holdouts),
                "all_holdouts_zero_harm": all(int(row.get("harmful_override_count") or 0) == 0 for row in holdouts),
                "all_holdouts_improve": all(float(row.get("hybrid_delta_vs_symbolic") or 0.0) > 0.0 for row in holdouts),
            }
        )
    selected = best_policy(policy_reports)
    top = sorted(
        policy_reports,
        key=lambda report: (
            bool(report.get("all_holdouts_zero_harm")),
            bool(report.get("all_holdouts_improve")),
            float(report.get("mean_delta_vs_symbolic") or 0.0),
        ),
        reverse=True,
    )[:12]
    return {
        "schema": "adaptive_behavior_feature_override_policy_eval/v1",
        "description": "Report-only multi-holdout grid search for conservative learned residual override policies.",
        "ok": bool(train_samples and test_logs and policy_reports),
        "train_logs": [str(path) for path in train_logs],
        "test_logs": [str(path) for path in test_logs],
        "train_sample_count": len(train_samples),
        "train_counts_by_log": train_counts,
        "test_counts_by_log": test_counts,
        "feature_keys": list(FEATURE_KEYS),
        "family_model_count": len(family_models),
        "policy_count": len(policy_reports),
        "selected_policy": selected,
        "top_policies": top,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
        "promotion_blocker": "candidate policy requires more independent real holdouts before runtime promotion",
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    selected = report.get("selected_policy") or {}
    lines = [
        "# Adaptive Behavior Feature Override Policy Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Train samples: `{report['train_sample_count']}`",
        f"Policy count: `{report['policy_count']}`",
        f"Selected policy: `{selected.get('policy_name')}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Selected Policy",
        "",
        "```json",
        json.dumps(selected.get("policy") or {}, indent=2),
        "```",
        "",
        "## Selected Holdouts",
        "",
        "| holdout | samples | symbolic | hybrid | delta | overrides | helpful | harmful | neutral wrong |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in selected.get("holdouts") or []:
        lines.append(
            f"| `{Path(str(row.get('test_log'))).name}` | `{row.get('test_sample_count')}` | "
            f"`{row.get('symbolic_match_rate')}` | `{row.get('hybrid_match_rate')}` | "
            f"`{row.get('hybrid_delta_vs_symbolic')}` | `{row.get('override_count')}` | "
            f"`{row.get('helpful_override_count')}` | `{row.get('harmful_override_count')}` | "
            f"`{row.get('neutral_wrong_override_count')}` |"
        )
    lines.extend(["", "## Top Policies", "", "| policy | mean delta | min delta | helpful | harmful |", "| --- | ---: | ---: | ---: | ---: |"])
    for row in report.get("top_policies") or []:
        lines.append(
            f"| `{row.get('policy_name')}` | `{row.get('mean_delta_vs_symbolic')}` | "
            f"`{row.get('min_delta_vs_symbolic')}` | `{row.get('total_helpful_override_count')}` | "
            f"`{row.get('total_harmful_override_count')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate conservative residual override policies across holdout logs.")
    parser.add_argument("--train-log", action="append", type=Path, default=None)
    parser.add_argument("--test-log", action="append", type=Path, default=None)
    parser.add_argument("--residual-thresholds", default="0.70,0.80,0.90,0.95,0.98,0.99,0.995,0.999")
    parser.add_argument("--family-thresholds", default="0.0,0.6,0.8,0.9,0.95")
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(
        args.train_log or DEFAULT_TRAIN_LOGS,
        args.test_log or DEFAULT_TEST_LOGS,
        parse_float_grid(args.residual_thresholds),
        parse_float_grid(args.family_thresholds),
    )
    write_report(report, args.out_json, args.out_md)
    selected = report.get("selected_policy") or {}
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "selected_policy": selected.get("policy_name"),
                "mean_delta": selected.get("mean_delta_vs_symbolic"),
                "total_harmful": selected.get("total_harmful_override_count"),
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] and selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
