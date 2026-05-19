from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import (  # noqa: E402
    CLCLearnedPolicySample,
    CLCLearnedPolicySelector,
    CLCPolicyFeatures,
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from hermes_hard_stale_escalation_v2 import selector_features  # noqa: E402


MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"
V2 = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_v2_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "clc_boundary_retrain_selector_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_boundary_retrain_selector_eval_report.md"

POLICY_TO_FORCED_MODE = {
    POLICY_PERIODIC: "periodic_baseline",
    POLICY_LONG_SEVERE: "long_severe",
    POLICY_XSEQ_MEMORY: "xseq_memory",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_samples(data: dict[str, Any]) -> list[CLCLearnedPolicySample]:
    samples = []
    for row in data.get("scenarios", []):
        policy = str(row.get("oracle_policy") or "")
        features = row.get("features")
        if policy and isinstance(features, dict):
            samples.append(
                CLCLearnedPolicySample(
                    features=CLCPolicyFeatures(**features),
                    policy=policy,
                    weight=1.0,
                    source=f"matrix:{row.get('id')}",
                )
            )
    return samples


def v2_groups(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.get("results", []):
        groups[str(row["scenario_key"])].append(row)
    return dict(groups)


def v2_features(row: dict[str, Any]) -> CLCPolicyFeatures:
    return CLCPolicyFeatures.from_condition_name(
        "hard_budget144",
        **{
            key: value
            for key, value in selector_features(
                int(row["stale_count"]),
                str(row["semantic_similarity"]),
                str(row["domain_noise"]),
                str(row["query_specificity"]),
            ).items()
            if key != "condition_name"
        },
    )


def v2_samples(data: dict[str, Any], *, weight: float = 2.0) -> list[CLCLearnedPolicySample]:
    samples = []
    for key, rows in v2_groups(data).items():
        oracle = rows[0].get("oracle_policy")
        if oracle not in {POLICY_PERIODIC, POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}:
            continue
        samples.append(
            CLCLearnedPolicySample(
                features=v2_features(rows[0]),
                policy=str(oracle),
                weight=weight,
                source=f"v2:{key}",
            )
        )
    return samples


def row_for_policy(rows: list[dict[str, Any]], policy: str) -> dict[str, Any] | None:
    forced_mode = POLICY_TO_FORCED_MODE.get(policy)
    for row in rows:
        if row.get("policy_mode") == forced_mode:
            return row
    for row in rows:
        if row.get("selected_policy") == policy:
            return row
    return None


def evaluate_v2(selector: CLCLearnedPolicySelector | CLCPolicySelector, data: dict[str, Any]) -> dict[str, Any]:
    total_utility = 0.0
    pass_count = 0
    oracle_count = 0
    decisions = []
    groups = v2_groups(data)
    for key, rows in groups.items():
        features = v2_features(rows[0])
        decision = selector.select(features)
        outcome = row_for_policy(rows, decision.policy)
        if outcome is None:
            raise RuntimeError(f"no outcome row for policy {decision.policy} in {key}")
        total_utility += float(outcome["utility"])
        pass_count += 1 if outcome["answer_passed"] else 0
        oracle_count += 1 if decision.policy == rows[0].get("oracle_policy") else 0
        decisions.append(
            {
                "scenario_key": key,
                "policy": decision.policy,
                "oracle_policy": rows[0].get("oracle_policy"),
                "passed": bool(outcome["answer_passed"]),
                "utility": float(outcome["utility"]),
                "stale_dominated": bool(outcome["stale_dominated"]),
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        )
    total = max(1, len(groups))
    return {
        "utility": round(total_utility, 6),
        "pass_rate": round(pass_count / total, 6),
        "oracle_match_rate": round(oracle_count / total, 6),
        "decisions": decisions,
    }


def evaluate_matrix(selector: CLCLearnedPolicySelector | CLCPolicySelector, data: dict[str, Any]) -> dict[str, Any]:
    total_utility = 0.0
    pass_count = 0
    oracle_count = 0
    decisions = []
    for row in data.get("scenarios", []):
        features = CLCPolicyFeatures(**row["features"])
        decision = selector.select(features)
        result = row["policy_results"][decision.policy]
        total_utility += float(result["utility"])
        pass_count += 1 if result["passed"] else 0
        oracle_count += 1 if decision.policy == row["oracle_policy"] else 0
        decisions.append(
            {
                "id": row["id"],
                "family": row["family"],
                "policy": decision.policy,
                "oracle_policy": row["oracle_policy"],
                "passed": bool(result["passed"]),
                "utility": float(result["utility"]),
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        )
    total = max(1, len(data.get("scenarios", [])))
    return {
        "utility": round(total_utility, 6),
        "pass_rate": round(pass_count / total, 6),
        "oracle_match_rate": round(oracle_count / total, 6),
        "decisions": decisions,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# CLC Boundary Retrain Selector Eval",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        "| Selector | Dataset | Utility | Pass rate | Oracle match |",
        "|---|---|---:|---:|---:|",
    ]
    for selector_name, dataset_stats in report["summary"].items():
        for dataset_name, stats in dataset_stats.items():
            lines.append(
                f"| {selector_name} | {dataset_name} | {stats['utility']} | {stats['pass_rate']} | {stats['oracle_match_rate']} |"
            )
    lines.extend(["", "## Key Decisions", ""])
    for row in report["boundary_retrained_v2_decisions"]:
        lines.append(
            f"- `{row['scenario_key']}` -> `{row['policy']}`; oracle `{row['oracle_policy']}`; passed `{row['passed']}`"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    matrix = load_json(MATRIX)
    v2 = load_json(V2)
    base_samples = matrix_samples(matrix)
    boundary_samples = v2_samples(v2, weight=2.0)

    selectors = {
        "current_clc": CLCPolicySelector(),
        "learned_matrix_only": CLCLearnedPolicySelector(base_samples, k=3),
        "learned_matrix_plus_boundary": CLCLearnedPolicySelector(base_samples + boundary_samples, k=3),
        "learned_boundary_only": CLCLearnedPolicySelector(boundary_samples, k=3),
    }
    summary = {}
    failures = []
    for name, selector in selectors.items():
        summary[name] = {
            "matrix": {k: v for k, v in evaluate_matrix(selector, matrix).items() if k != "decisions"},
            "v2_boundary": {k: v for k, v in evaluate_v2(selector, v2).items() if k != "decisions"},
        }

    retrained_matrix = evaluate_matrix(selectors["learned_matrix_plus_boundary"], matrix)
    retrained_v2 = evaluate_v2(selectors["learned_matrix_plus_boundary"], v2)
    matrix_only_v2 = evaluate_v2(selectors["learned_matrix_only"], v2)

    if retrained_v2["pass_rate"] < 1.0:
        failures.append("boundary-retrained selector should pass v2 boundary cases")
    if retrained_v2["oracle_match_rate"] < 1.0:
        failures.append("boundary-retrained selector should match v2 oracle policy")
    if retrained_matrix["pass_rate"] < 1.0:
        failures.append("boundary-retrained selector should not reduce original matrix pass rate")
    if retrained_matrix["utility"] < 19.7:
        failures.append("boundary-retrained selector utility on matrix dropped too far")
    if matrix_only_v2["pass_rate"] >= retrained_v2["pass_rate"]:
        failures.append("boundary retraining should improve over matrix-only learned selector on v2")

    report = {
        "ok": not failures,
        "matrix": str(MATRIX),
        "v2": str(V2),
        "sample_counts": {"matrix": len(base_samples), "boundary": len(boundary_samples)},
        "summary": summary,
        "boundary_retrained_v2_decisions": retrained_v2["decisions"],
        "boundary_retrained_matrix_non_oracle": [
            row for row in retrained_matrix["decisions"] if row["policy"] != row["oracle_policy"]
        ],
        "failures": failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "sample_counts": report["sample_counts"],
                "summary": summary,
                "failures": failures,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
