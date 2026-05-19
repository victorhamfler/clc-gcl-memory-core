from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
    CLCPolicyFeatures,
    CLCPolicySelector,
)


EXPECTED = {
    "hard_budget144": POLICY_XSEQ_MEMORY,
    "standard_budget144": POLICY_LONG_SEVERE,
    "long2_hard_budget288": POLICY_PERIODIC,
    "long2_standard_budget288": POLICY_PERIODIC,
}


def load_combined_selector_result() -> dict:
    path = REPO_ROOT / "experiments" / "csd_gemma_clc_selector_combined6_results.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def result_delta(data: dict, condition: str) -> float | None:
    for row in data.get("summary", []):
        if (
            row.get("condition") == condition
            and row.get("policy") == "clc_selector_hard_xseq_standard_long_long2_periodic"
        ):
            return float(row.get("delta_label_compute_vs_periodic", 0.0))
    return None


def main() -> int:
    selector = CLCPolicySelector()
    failures: list[str] = []
    decisions = {}
    for condition, expected_policy in EXPECTED.items():
        decision = selector.select(CLCPolicyFeatures.from_condition_name(condition))
        decisions[condition] = {
            "policy": decision.policy,
            "action": decision.action,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "expected": expected_policy,
        }
        if decision.policy != expected_policy:
            failures.append(f"{condition}: expected {expected_policy}, got {decision.policy}")

    high_label = selector.select(
        {
            "condition_name": "hard_budget144",
            "label_cost": 0.0003,
            "budget_pressure": 0.0,
        }
    )
    decisions["hard_budget144_high_label_cost"] = {
        "policy": high_label.policy,
        "action": high_label.action,
        "reason": high_label.reason,
    }
    if high_label.policy != POLICY_PERIODIC:
        failures.append("high label cost should force periodic/protect")

    high_pressure = selector.select(
        {
            "condition_name": "standard_budget144",
            "label_cost": 0.0002,
            "budget_pressure": 0.95,
        }
    )
    decisions["standard_budget144_high_budget_pressure"] = {
        "policy": high_pressure.policy,
        "action": high_pressure.action,
        "reason": high_pressure.reason,
    }
    if high_pressure.policy != POLICY_PERIODIC:
        failures.append("high budget pressure should force periodic/protect")

    evidence = load_combined_selector_result()
    evidence_deltas = {
        condition: result_delta(evidence, condition)
        for condition in EXPECTED
    }

    report = {
        "status": "fail" if failures else "pass",
        "selector": "CLCPolicySelector",
        "decisions": decisions,
        "evidence_file": str(REPO_ROOT / "experiments" / "csd_gemma_clc_selector_combined6_results.json"),
        "evidence_deltas": evidence_deltas,
        "failures": failures,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
