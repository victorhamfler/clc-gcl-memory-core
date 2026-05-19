from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
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
    POLICY_ORDER,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from hermes_hard_stale_escalation_v2 import selector_features  # noqa: E402


MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"
COMBINED = REPO_ROOT / "experiments" / "clc_selector_combined_training_report.json"
V2 = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_v2_results.json"
OUTCOME_LOG = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "clc_outcome_log_selector_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_outcome_log_selector_eval_report.md"

POLICY_TO_FORCED_MODE = {
    POLICY_PERIODIC: "periodic_baseline",
    POLICY_LONG_SEVERE: "long_severe",
    POLICY_XSEQ_MEMORY: "xseq_memory",
}
HIGH_CONFIDENCE_LABELS = {"oracle_match_passed", "helped"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def matrix_samples(data: dict[str, Any]) -> list[CLCLearnedPolicySample]:
    samples = []
    for row in data.get("scenarios", []):
        features = row.get("features")
        policy = str(row.get("oracle_policy") or "")
        if isinstance(features, dict) and policy in POLICY_ORDER:
            samples.append(
                CLCLearnedPolicySample(
                    features=CLCPolicyFeatures(**features),
                    policy=policy,
                    weight=1.0,
                    source=f"matrix:{row.get('id')}",
                )
            )
    return samples


def outcome_policy(row: dict[str, Any]) -> str:
    policy = str(row.get("oracle_policy") or "")
    if policy in POLICY_ORDER:
        return policy
    if str(row.get("outcome_label") or "") == "helped":
        policy = str(row.get("selected_policy") or "")
    return policy if policy in POLICY_ORDER else ""


def outcome_features(row: dict[str, Any]) -> CLCPolicyFeatures:
    if "stale_count" in row:
        dynamic = selector_features(
            int(row.get("stale_count") or 0),
            str(row.get("semantic_similarity") or "high"),
            str(row.get("domain_noise") or "none"),
            str(row.get("query_specificity") or "exact"),
        )
        return CLCPolicyFeatures.from_condition_name(
            str(dynamic.get("condition_name") or "hard_budget144"),
            **{key: value for key, value in dynamic.items() if key != "condition_name"},
        )

    family = str(row.get("family") or "").lower()
    condition = str(row.get("condition_name") or "")
    kwargs: dict[str, Any] = {}
    if family == "hard_bad_majority":
        kwargs = {"memory_bad_rate": 0.75, "probe_drop": 0.18, "csd_ratio": 1.4}
    elif family == "standard_update":
        kwargs = {"memory_bad_rate": 0.25, "probe_drop": 0.08, "csd_ratio": 0.9}
    elif family == "long_topic":
        kwargs = {"memory_bad_rate": 0.35, "probe_drop": 0.04, "csd_ratio": 0.7}
    elif family == "long_session":
        kwargs = {"memory_bad_rate": 0.2, "probe_drop": 0.03, "csd_ratio": 0.6}
    return CLCPolicyFeatures.from_condition_name(condition, **kwargs)


def feature_key(features: CLCPolicyFeatures) -> tuple[Any, ...]:
    data = asdict(features)
    return tuple((key, round(float(value), 6) if isinstance(value, float) else value) for key, value in sorted(data.items()))


def outcome_weight(row: dict[str, Any]) -> float:
    label = str(row.get("outcome_label") or "")
    if label == "oracle_match_passed":
        return 1.5
    if label == "helped":
        return 1.25
    return 1.0


def filtered_outcome_samples(
    rows: list[dict[str, Any]], *, conflict_safe: bool = False
) -> tuple[list[CLCLearnedPolicySample], dict[str, Any]]:
    grouped_rows: dict[tuple[Any, ...], list[tuple[dict[str, Any], CLCPolicyFeatures, str]]] = defaultdict(list)
    skipped = Counter()
    used = Counter()
    for row in rows:
        label = str(row.get("outcome_label") or "")
        if label not in HIGH_CONFIDENCE_LABELS:
            skipped[f"label:{label or 'missing'}"] += 1
            continue
        policy = outcome_policy(row)
        if policy not in POLICY_ORDER:
            skipped["no_policy"] += 1
            continue
        features = outcome_features(row)
        grouped_rows[feature_key(features)].append((row, features, policy))

    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    conflict_skipped_rows = 0
    conflict_skipped_features = 0
    for feature_signature, feature_rows in grouped_rows.items():
        policies = {policy for _, _, policy in feature_rows}
        if conflict_safe and len(policies) > 1:
            conflict_skipped_features += 1
            conflict_skipped_rows += len(feature_rows)
            continue
        for row, features, policy in feature_rows:
            label = str(row.get("outcome_label") or "")
            key = (feature_signature, policy)
            entry = grouped.setdefault(
                key,
                {
                    "features": features,
                    "policy": policy,
                    "weight": 0.0,
                    "sources": Counter(),
                    "labels": Counter(),
                },
            )
            entry["weight"] += outcome_weight(row)
            entry["sources"][str(row.get("source") or "unknown")] += 1
            entry["labels"][label] += 1
            used[label] += 1

    samples = []
    for index, entry in enumerate(grouped.values()):
        # Cap repeated identical outcomes so one benchmark source cannot drown out the balanced seed matrix.
        weight = min(3.0, float(entry["weight"]))
        source_bits = ",".join(f"{name}:{count}" for name, count in sorted(entry["sources"].items()))
        samples.append(
            CLCLearnedPolicySample(
                features=entry["features"],
                policy=str(entry["policy"]),
                weight=weight,
                source=f"outcome:{index}:{source_bits}",
            )
        )
    return samples, {
        "raw_rows": len(rows),
        "conflict_safe": conflict_safe,
        "used_rows_by_label": dict(used),
        "skipped_rows_by_reason": dict(skipped),
        "conflict_skipped_features": conflict_skipped_features,
        "conflict_skipped_rows": conflict_skipped_rows,
        "deduped_samples": len(samples),
        "policy_counts": dict(Counter(sample.policy for sample in samples)),
        "total_capped_weight": round(sum(sample.weight for sample in samples), 6),
    }


def v2_groups(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.get("results", []):
        groups[str(row["scenario_key"])].append(row)
    return dict(groups)


def v2_features(row: dict[str, Any]) -> CLCPolicyFeatures:
    dynamic = selector_features(
        int(row["stale_count"]),
        str(row["semantic_similarity"]),
        str(row["domain_noise"]),
        str(row["query_specificity"]),
    )
    return CLCPolicyFeatures.from_condition_name(
        str(dynamic.get("condition_name") or "hard_budget144"),
        **{key: value for key, value in dynamic.items() if key != "condition_name"},
    )


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
        decision = selector.select(v2_features(rows[0]))
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


def public_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in stats.items() if key != "decisions"}


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# CLC Outcome Log Selector Eval",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        "## Outcome Samples",
        "",
        f"- Raw outcome rows: `{report['outcome_sample_summary']['raw_rows']}`",
        f"- Deduped high-confidence samples: `{report['outcome_sample_summary']['deduped_samples']}`",
        f"- Total capped outcome weight: `{report['outcome_sample_summary']['total_capped_weight']}`",
        f"- Conflict-safe samples: `{report['safe_outcome_sample_summary']['deduped_samples']}`",
        f"- Conflict-skipped feature signatures: `{report['safe_outcome_sample_summary']['conflict_skipped_features']}`",
        "",
        "## Results",
        "",
        "| Selector | Matrix utility | Matrix pass | Matrix oracle | V2 utility | V2 pass | V2 oracle |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in report["summary"].items():
        matrix = stats["matrix"]
        v2 = stats["v2_boundary"]
        lines.append(
            f"| `{name}` | {matrix['utility']} | {matrix['pass_rate']} | {matrix['oracle_match_rate']} | "
            f"{v2['utility']} | {v2['pass_rate']} | {v2['oracle_match_rate']} |"
        )
    lines.extend(["", "## Failures", ""])
    if report["raw_failures"]:
        lines.append("Raw outcome augmentation:")
        lines.extend(f"- {failure}" for failure in report["raw_failures"])
    if report["safe_failures"]:
        lines.append("Conflict-safe outcome augmentation:")
        lines.extend(f"- {failure}" for failure in report["safe_failures"])
    if not report["raw_failures"] and not report["safe_failures"]:
        lines.append("- None")
    lines.extend(["", "## Recommendation", ""])
    if report["conflict_safe_ok"] and not report["raw_outcome_ok"]:
        lines.append(
            "Use conflict-safe outcome admission before any continual selector update. The raw log contains label conflicts at identical feature signatures."
        )
    elif report["conflict_safe_ok"]:
        lines.append("Conflict-safe outcome augmentation passed the current guard tests.")
    else:
        lines.append("Do not use outcome-log augmentation yet; even the conflict-safe filter failed guard tests.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    matrix = load_json(MATRIX)
    combined = load_json(COMBINED)
    v2 = load_json(V2)
    outcome_rows = load_jsonl(OUTCOME_LOG)
    combined_samples = matrix_samples(combined)
    outcome_samples, outcome_summary = filtered_outcome_samples(outcome_rows)
    safe_outcome_samples, safe_outcome_summary = filtered_outcome_samples(outcome_rows, conflict_safe=True)

    selectors = {
        "current_clc": CLCPolicySelector(),
        "combined_only": CLCLearnedPolicySelector(combined_samples, k=3),
        "outcome_only_filtered": CLCLearnedPolicySelector(outcome_samples, k=3),
        "combined_plus_outcome_filtered": CLCLearnedPolicySelector(combined_samples + outcome_samples, k=3),
        "outcome_only_conflict_safe": CLCLearnedPolicySelector(safe_outcome_samples, k=3),
        "combined_plus_outcome_conflict_safe": CLCLearnedPolicySelector(
            combined_samples + safe_outcome_samples, k=3
        ),
    }

    summary = {}
    for name, selector in selectors.items():
        summary[name] = {
            "matrix": public_stats(evaluate_matrix(selector, matrix)),
            "v2_boundary": public_stats(evaluate_v2(selector, v2)),
        }

    combined = summary["combined_only"]
    combined_plus = summary["combined_plus_outcome_filtered"]
    safe_combined_plus = summary["combined_plus_outcome_conflict_safe"]
    failures = []
    if combined_plus["matrix"]["pass_rate"] < combined["matrix"]["pass_rate"]:
        failures.append("raw outcome augmentation reduced matrix pass rate")
    if combined_plus["v2_boundary"]["pass_rate"] < combined["v2_boundary"]["pass_rate"]:
        failures.append("raw outcome augmentation reduced v2 boundary pass rate")
    if combined_plus["matrix"]["utility"] < 19.7:
        failures.append("raw outcome augmentation dropped matrix utility below 19.7")
    if combined_plus["v2_boundary"]["utility"] < 5.85:
        failures.append("raw outcome augmentation dropped v2 boundary utility below 5.85")

    safe_failures = []
    if safe_combined_plus["matrix"]["pass_rate"] < combined["matrix"]["pass_rate"]:
        safe_failures.append("conflict-safe outcome augmentation reduced matrix pass rate")
    if safe_combined_plus["v2_boundary"]["pass_rate"] < combined["v2_boundary"]["pass_rate"]:
        safe_failures.append("conflict-safe outcome augmentation reduced v2 boundary pass rate")
    if safe_combined_plus["matrix"]["utility"] < 19.7:
        safe_failures.append("conflict-safe outcome augmentation dropped matrix utility below 19.7")
    if safe_combined_plus["v2_boundary"]["utility"] < 5.85:
        safe_failures.append("conflict-safe outcome augmentation dropped v2 boundary utility below 5.85")

    report = {
        "ok": not safe_failures,
        "raw_outcome_ok": not failures,
        "conflict_safe_ok": not safe_failures,
        "sources": {
            "matrix": str(MATRIX),
            "combined_training": str(COMBINED),
            "v2": str(V2),
            "outcome_log": str(OUTCOME_LOG),
        },
        "sample_counts": {
            "combined": len(combined_samples),
            "outcome_filtered": len(outcome_samples),
            "combined_plus_outcome_filtered": len(combined_samples) + len(outcome_samples),
            "outcome_conflict_safe": len(safe_outcome_samples),
            "combined_plus_outcome_conflict_safe": len(combined_samples) + len(safe_outcome_samples),
        },
        "outcome_sample_summary": outcome_summary,
        "safe_outcome_sample_summary": safe_outcome_summary,
        "summary": summary,
        "combined_plus_matrix_non_oracle": [
            row
            for row in evaluate_matrix(selectors["combined_plus_outcome_filtered"], matrix)["decisions"]
            if row["policy"] != row["oracle_policy"]
        ],
        "combined_plus_v2_non_oracle": [
            row
            for row in evaluate_v2(selectors["combined_plus_outcome_filtered"], v2)["decisions"]
            if row["policy"] != row["oracle_policy"]
        ],
        "conflict_safe_v2_non_oracle": [
            row
            for row in evaluate_v2(selectors["combined_plus_outcome_conflict_safe"], v2)["decisions"]
            if row["policy"] != row["oracle_policy"]
        ],
        "raw_failures": failures,
        "safe_failures": safe_failures,
        "failures": safe_failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "raw_outcome_ok": report["raw_outcome_ok"],
                "conflict_safe_ok": report["conflict_safe_ok"],
                "summary": summary,
                "sample_counts": report["sample_counts"],
                "raw_failures": failures,
                "safe_failures": safe_failures,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
