from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCLearnedPolicySample,
    CLCLearnedPolicySelector,
    CLCPolicyFeatures,
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)


LIVE_MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"
HASH_MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_results.json"
OUTCOME_LOG = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "clc_learned_policy_selector_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_learned_policy_selector_eval_report.md"


def matrix_path() -> Path:
    return LIVE_MATRIX if LIVE_MATRIX.exists() else HASH_MATRIX


def load_matrix() -> dict[str, Any]:
    path = matrix_path()
    return json.loads(path.read_text(encoding="utf-8"))


def samples_from_rows(rows: list[dict[str, Any]]) -> list[CLCLearnedPolicySample]:
    samples: list[CLCLearnedPolicySample] = []
    for row in rows:
        policy = str(row.get("oracle_policy") or "")
        features = row.get("features")
        if policy and isinstance(features, dict):
            samples.append(
                CLCLearnedPolicySample(
                    features=CLCPolicyFeatures(**features),
                    policy=policy,
                    weight=1.0,
                    source=str(row.get("id") or ""),
                )
            )
    return samples


def score_strategy(data: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    rows = data.get("scenarios", [])
    total_utility = 0.0
    pass_count = 0
    oracle_count = 0
    decisions = []
    for idx, row in enumerate(rows):
        features = CLCPolicyFeatures(**row["features"])
        if strategy_name == "current_clc_selector":
            decision = CLCPolicySelector().select(features)
        elif strategy_name == "learned_knn_leave_one_out":
            train_rows = rows[:idx] + rows[idx + 1 :]
            decision = CLCLearnedPolicySelector(samples_from_rows(train_rows), k=3).select(features)
        elif strategy_name == "learned_knn_full":
            decision = CLCLearnedPolicySelector.from_matrix_report(matrix_path(), k=3).select(features)
        else:
            raise ValueError(f"unknown strategy: {strategy_name}")
        result = row["policy_results"][decision.policy]
        total_utility += float(result["utility"])
        pass_count += 1 if result["passed"] else 0
        oracle_count += 1 if decision.policy == row["oracle_policy"] else 0
        decisions.append(
            {
                "id": row["id"],
                "family": row["family"],
                "condition_name": row["condition_name"],
                "policy": decision.policy,
                "oracle_policy": row["oracle_policy"],
                "passed": bool(result["passed"]),
                "utility": float(result["utility"]),
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        )
    return {
        "utility": round(total_utility, 6),
        "pass_rate": round(pass_count / len(rows), 6),
        "oracle_match_rate": round(oracle_count / len(rows), 6),
        "decisions": decisions,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# CLC Learned Policy Selector Eval",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        f"Training/eval matrix: `{report['matrix_path']}`",
        f"Outcome log samples loaded: **{report['outcome_log_samples']}**",
        "",
        "| Strategy | Utility | Pass rate | Oracle match |",
        "|---|---:|---:|---:|",
    ]
    for name, stats in report["strategy_summary"].items():
        lines.append(f"| {name} | {stats['utility']} | {stats['pass_rate']} | {stats['oracle_match_rate']} |")
    lines.extend(["", "## API Checks", ""])
    for key, value in report["api_checks"].items():
        lines.append(f"- {key}: `{value}`")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    data = load_matrix()
    failures: list[str] = []

    current = score_strategy(data, "current_clc_selector")
    learned_loo = score_strategy(data, "learned_knn_leave_one_out")
    learned_full = score_strategy(data, "learned_knn_full")

    if learned_loo["pass_rate"] < current["pass_rate"]:
        failures.append("learned leave-one-out pass rate regressed versus current selector")
    if learned_loo["utility"] < current["utility"]:
        failures.append("learned leave-one-out utility regressed versus current selector")
    if learned_loo["oracle_match_rate"] < current["oracle_match_rate"]:
        failures.append("learned leave-one-out oracle match regressed versus current selector")

    full_selector = CLCLearnedPolicySelector.from_matrix_report(matrix_path(), k=3)
    outcome_selector = CLCLearnedPolicySelector.from_outcome_log(OUTCOME_LOG, k=3)
    hard_decision = full_selector.select(
        CLCPolicyFeatures.from_condition_name("hard_budget144", memory_bad_rate=0.75, probe_drop=0.18, csd_ratio=1.4)
    )
    standard_decision = full_selector.select(
        CLCPolicyFeatures.from_condition_name("standard_budget144", memory_bad_rate=0.25, probe_drop=0.08, csd_ratio=0.9)
    )
    long_decision = full_selector.select(
        CLCPolicyFeatures.from_condition_name("long2_hard_budget288", memory_bad_rate=0.35, probe_drop=0.04, csd_ratio=0.7)
    )
    guard_decision = full_selector.select({"condition_name": "hard_budget144", "label_cost": 0.0004})
    fallback_decision = CLCLearnedPolicySelector([]).select(CLCPolicyFeatures.from_condition_name("hard_budget144"))

    api_checks = {
        "hard_bad_majority_policy": hard_decision.policy,
        "standard_update_policy": standard_decision.policy,
        "long_stream_policy": long_decision.policy,
        "high_label_cost_guard": guard_decision.policy,
        "empty_training_fallback": fallback_decision.policy,
        "outcome_log_sample_count": len(outcome_selector.samples),
    }
    if hard_decision.policy != POLICY_PERIODIC:
        failures.append(f"learned selector should avoid XSEQ over-spend on hard_bad_majority, got {hard_decision.policy}")
    if standard_decision.policy != POLICY_LONG_SEVERE:
        failures.append(f"learned selector should preserve standard update refresh, got {standard_decision.policy}")
    if long_decision.policy != POLICY_PERIODIC:
        failures.append(f"learned selector should keep long streams periodic, got {long_decision.policy}")
    if guard_decision.policy != POLICY_PERIODIC:
        failures.append("high label cost guard should force periodic")
    if fallback_decision.policy != POLICY_XSEQ_MEMORY:
        failures.append("empty learned selector should fall back to current CLC hard policy")

    report = {
        "ok": not failures,
        "matrix_path": str(matrix_path()),
        "outcome_log": str(OUTCOME_LOG),
        "outcome_log_samples": len(outcome_selector.samples),
        "strategy_summary": {
            "current_clc_selector": {k: current[k] for k in ("utility", "pass_rate", "oracle_match_rate")},
            "learned_knn_leave_one_out": {k: learned_loo[k] for k in ("utility", "pass_rate", "oracle_match_rate")},
            "learned_knn_full": {k: learned_full[k] for k in ("utility", "pass_rate", "oracle_match_rate")},
        },
        "api_checks": api_checks,
        "failures": failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
