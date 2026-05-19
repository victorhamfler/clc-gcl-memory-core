from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
CURRENT_JSON = REPO_ROOT / "experiments" / "hermes_clc_selector_ab_eval_live_results.json"
LEARNED_JSON = REPO_ROOT / "experiments" / "hermes_clc_learned_selector_ab_eval_live_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_clc_selector_mode_comparison.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_clc_selector_mode_comparison.md"

POLICY_COST = {
    "periodic_baseline": 0.0,
    "long_severe_r16_overwrite": 0.015,
    "xseq_memory_r45_badmajority": 0.025,
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def strategy_stats(report: dict[str, Any]) -> dict[str, Any]:
    passed = 0
    helped = 0
    cost = 0.0
    policies: dict[str, int] = {}
    for row in report.get("scenarios", []):
        policy = row.get("selector_decision", {}).get("policy")
        policies[policy] = policies.get(policy, 0) + 1
        cost += POLICY_COST.get(policy, 0.0)
        if row.get("selector", {}).get("passed"):
            passed += 1
        if row.get("comparison") == "helped":
            helped += 1
    total = max(1, len(report.get("scenarios", [])))
    return {
        "pass_rate": round(passed / total, 6),
        "helped_count": helped,
        "policy_cost": round(cost, 6),
        "utility": round(passed - cost, 6),
        "policy_counts": policies,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Hermes CLC Selector Mode Comparison",
        "",
        "| Selector mode | Pass rate | Helped count | Policy cost | Utility | Policy counts |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for mode, stats in report["summary"].items():
        lines.append(
            f"| {mode} | {stats['pass_rate']} | {stats['helped_count']} | {stats['policy_cost']} | {stats['utility']} | {stats['policy_counts']} |"
        )
    lines.extend(["", "## Scenario Differences", "", "| Scenario | Current policy | Learned policy | Same pass result |", "|---|---|---|---:|"])
    for row in report["scenario_differences"]:
        lines.append(
            f"| {row['id']} | {row['current_policy']} | {row['learned_policy']} | {row['same_pass_result']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    current = load(CURRENT_JSON)
    learned = load(LEARNED_JSON)
    current_by_id = {row["id"]: row for row in current.get("scenarios", [])}
    learned_by_id = {row["id"]: row for row in learned.get("scenarios", [])}
    differences = []
    for scenario_id in sorted(set(current_by_id) | set(learned_by_id)):
        cur = current_by_id[scenario_id]
        lea = learned_by_id[scenario_id]
        differences.append(
            {
                "id": scenario_id,
                "current_policy": cur.get("selector_decision", {}).get("policy"),
                "learned_policy": lea.get("selector_decision", {}).get("policy"),
                "current_passed": bool(cur.get("selector", {}).get("passed")),
                "learned_passed": bool(lea.get("selector", {}).get("passed")),
                "same_pass_result": bool(cur.get("selector", {}).get("passed")) == bool(lea.get("selector", {}).get("passed")),
            }
        )
    report = {
        "ok": all(row["same_pass_result"] for row in differences)
        and strategy_stats(learned)["utility"] >= strategy_stats(current)["utility"],
        "inputs": {"current": str(CURRENT_JSON), "learned": str(LEARNED_JSON)},
        "summary": {
            "current": strategy_stats(current),
            "learned": strategy_stats(learned),
        },
        "scenario_differences": differences,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD), "summary": report["summary"]}, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
