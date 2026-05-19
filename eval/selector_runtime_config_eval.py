from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import load_config  # noqa: E402
from core.clc_policy_selector import CLCPolicyFeatures, POLICY_LONG_SEVERE, POLICY_PERIODIC  # noqa: E402
from core.selector_runtime import (  # noqa: E402
    build_policy_selector,
    selector_config_view,
    selector_features_for_condition,
)
from hermes_hard_stale_escalation_v2 import selector_features  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "selector_runtime_config_eval_results.json"


def v2_boundary_selector_features() -> CLCPolicyFeatures:
    dynamic = selector_features(3, "adversarial", "same_domain", "stale_biased")
    return CLCPolicyFeatures.from_condition_name(
        str(dynamic.get("condition_name") or "hard_budget144"),
        **{key: value for key, value in dynamic.items() if key != "condition_name"},
    )


def main() -> int:
    config = load_config(ROOT)
    selector = build_policy_selector(ROOT, config)
    view = selector_config_view(ROOT, config)
    decisions = {
        "hard_budget144": selector.select(selector_features_for_condition("hard_budget144")).policy,
        "standard_budget144": selector.select(selector_features_for_condition("standard_budget144")).policy,
        "long2_hard_budget288": selector.select(selector_features_for_condition("long2_hard_budget288")).policy,
        "v2_stale_boundary": selector.select(v2_boundary_selector_features()).policy,
        "high_label_cost_guard": selector.select({"condition_name": "hard_budget144", "label_cost": 0.0004}).policy,
    }
    failures = []
    if view["mode"] != "learned":
        failures.append(f"expected selector.mode learned, got {view['mode']}")
    if view["class"] != "CLCLearnedPolicySelector":
        failures.append(f"expected learned selector class, got {view['class']}")
    if view["sample_count"] <= 0:
        failures.append("learned selector should load at least one sample")
    if "clc_selector_guarded_continual_training_report.json" not in str(view.get("matrix_report", "")):
        failures.append(f"selector should load the guarded continual training report, got {view.get('matrix_report')}")
    if view["sample_count"] < 34:
        failures.append(f"guarded continual selector should load at least 34 samples, got {view['sample_count']}")
    if decisions["hard_budget144"] != POLICY_PERIODIC:
        failures.append(f"learned hard decision should be periodic, got {decisions['hard_budget144']}")
    if decisions["standard_budget144"] != POLICY_LONG_SEVERE:
        failures.append(f"standard update should use long severe refresh, got {decisions['standard_budget144']}")
    if decisions["long2_hard_budget288"] != POLICY_PERIODIC:
        failures.append(f"long stream should be periodic, got {decisions['long2_hard_budget288']}")
    if decisions["v2_stale_boundary"] != POLICY_LONG_SEVERE:
        failures.append(f"v2 stale boundary should use long severe refresh, got {decisions['v2_stale_boundary']}")
    if decisions["high_label_cost_guard"] != POLICY_PERIODIC:
        failures.append("high label cost guard should be periodic")

    report = {
        "ok": not failures,
        "selector_config": view,
        "decisions": decisions,
        "failures": failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
