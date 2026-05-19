from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import CLCLearnedPolicySelector  # noqa: E402
from clc_outcome_log_selector_eval import (  # noqa: E402
    COMBINED,
    MATRIX,
    OUTCOME_LOG,
    V2,
    evaluate_matrix,
    evaluate_v2,
    filtered_outcome_samples,
    load_json,
    load_jsonl,
)


OUT_JSON = REPO_ROOT / "experiments" / "clc_selector_guarded_continual_candidate_report.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_selector_guarded_continual_candidate_report.md"
ACCEPTED_JSON = REPO_ROOT / "experiments" / "clc_selector_guarded_continual_training_report.json"
ACCEPTED_MD = REPO_ROOT / "experiments" / "clc_selector_guarded_continual_training_report.md"


def public_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in stats.items() if key != "decisions"}


def condition_name_from_features(features: dict[str, Any]) -> str:
    if features.get("long_stream"):
        return "long2_hard_budget288" if features.get("hard") else "long2_standard_budget288"
    return "hard_budget144" if features.get("hard") else "standard_budget144"


def candidate_rows(base_rows: list[dict[str, Any]], outcome_samples: list[Any]) -> list[dict[str, Any]]:
    rows = [dict(row, weight=float(row.get("weight", 1.0) or 1.0)) for row in base_rows]
    for index, sample in enumerate(outcome_samples):
        features = asdict(sample.features)
        rows.append(
            {
                "id": f"outcome_conflict_safe_{index:03d}",
                "family": "outcome_conflict_safe",
                "condition_name": condition_name_from_features(features),
                "source": sample.source,
                "features": features,
                "oracle_policy": sample.policy,
                "weight": sample.weight,
            }
        )
    return rows


def evaluate_report(path: Path) -> dict[str, Any]:
    matrix = load_json(MATRIX)
    v2 = load_json(V2)
    selector = CLCLearnedPolicySelector.from_matrix_report(path, k=3)
    return {
        "matrix": public_stats(evaluate_matrix(selector, matrix)),
        "v2_boundary": public_stats(evaluate_v2(selector, v2)),
        "sample_count": len(selector.samples),
    }


def guard_failures(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    failures = []
    if candidate["matrix"]["pass_rate"] < baseline["matrix"]["pass_rate"]:
        failures.append("candidate reduced matrix pass rate")
    if candidate["v2_boundary"]["pass_rate"] < baseline["v2_boundary"]["pass_rate"]:
        failures.append("candidate reduced v2 boundary pass rate")
    if candidate["matrix"]["oracle_match_rate"] < baseline["matrix"]["oracle_match_rate"]:
        failures.append("candidate reduced matrix oracle-match rate")
    if candidate["v2_boundary"]["oracle_match_rate"] < baseline["v2_boundary"]["oracle_match_rate"]:
        failures.append("candidate reduced v2 oracle-match rate")
    if candidate["matrix"]["utility"] < baseline["matrix"]["utility"]:
        failures.append("candidate reduced matrix utility")
    if candidate["v2_boundary"]["utility"] < baseline["v2_boundary"]["utility"]:
        failures.append("candidate reduced v2 boundary utility")
    return failures


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# CLC Guarded Continual Selector Candidate",
        "",
        f"Accepted: **{'YES' if report['accepted'] else 'NO'}**",
        "",
        "## Samples",
        "",
        f"- Base combined samples: `{report['sample_counts']['base_combined']}`",
        f"- Conflict-safe outcome samples: `{report['sample_counts']['outcome_conflict_safe']}`",
        f"- Candidate total samples: `{report['sample_counts']['candidate_total']}`",
        f"- Conflict-skipped feature signatures: `{report['outcome_sample_summary']['conflict_skipped_features']}`",
        f"- Conflict-skipped rows: `{report['outcome_sample_summary']['conflict_skipped_rows']}`",
        "",
        "## Guard Results",
        "",
        "| Selector | Matrix utility | Matrix pass | Matrix oracle | V2 utility | V2 pass | V2 oracle | Samples |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in report["guard_summary"].items():
        matrix = stats["matrix"]
        v2 = stats["v2_boundary"]
        lines.append(
            f"| `{name}` | {matrix['utility']} | {matrix['pass_rate']} | {matrix['oracle_match_rate']} | "
            f"{v2['utility']} | {v2['pass_rate']} | {v2['oracle_match_rate']} | {stats['sample_count']} |"
        )
    lines.extend(["", "## Failures", ""])
    if report["failures"]:
        lines.extend(f"- {failure}" for failure in report["failures"])
    else:
        lines.append("- None")
    lines.extend(["", "## Recommendation", ""])
    if report["accepted"]:
        lines.append(
            "This candidate is safe to test as the next learned-selector training source because it preserves both guard suites."
        )
    else:
        lines.append("Do not promote this candidate; keep the previous combined selector report as the default.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    combined = load_json(COMBINED)
    outcome_rows = load_jsonl(OUTCOME_LOG)
    safe_samples, outcome_summary = filtered_outcome_samples(outcome_rows, conflict_safe=True)
    scenarios = candidate_rows(combined.get("scenarios", []), safe_samples)
    policy_counts = Counter(str(row["oracle_policy"]) for row in scenarios)
    report = {
        "ok": True,
        "accepted": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "guarded continual learned-policy selector training candidate",
        "source_reports": {
            "base_combined": str(COMBINED),
            "outcome_log": str(OUTCOME_LOG),
            "matrix_guard": str(MATRIX),
            "v2_boundary_guard": str(V2),
        },
        "sample_counts": {
            "base_combined": len(combined.get("scenarios", [])),
            "outcome_conflict_safe": len(safe_samples),
            "candidate_total": len(scenarios),
        },
        "oracle_policy_counts": dict(sorted(policy_counts.items())),
        "outcome_sample_summary": outcome_summary,
        "scenarios": scenarios,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    baseline_stats = evaluate_report(COMBINED)
    candidate_stats = evaluate_report(OUT_JSON)
    failures = guard_failures(baseline_stats, candidate_stats)
    report["accepted"] = not failures
    report["guard_summary"] = {
        "combined_baseline": baseline_stats,
        "guarded_continual_candidate": candidate_stats,
    }
    report["failures"] = failures
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, OUT_MD)

    if report["accepted"]:
        ACCEPTED_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        write_markdown(report, ACCEPTED_MD)

    print(
        json.dumps(
            {
                "accepted": report["accepted"],
                "candidate_json": str(OUT_JSON),
                "accepted_json": str(ACCEPTED_JSON) if report["accepted"] else None,
                "sample_counts": report["sample_counts"],
                "guard_summary": report["guard_summary"],
                "failures": failures,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
