from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCPolicyFeatures,
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)


OUT_JSON = REPO_ROOT / "experiments" / "clc_policy_feature_signal_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_policy_feature_signal_regression_report.md"


def decide(features: CLCPolicyFeatures) -> dict:
    decision = CLCPolicySelector().select(features)
    return {
        "features": features.__dict__,
        "decision": decision.__dict__,
    }


def main() -> int:
    cases = {
        "hard_clean_supported": decide(
            CLCPolicyFeatures.from_condition_name(
                "hard_budget144",
                memory_bad_rate=0.148,
                probe_drop=0.028,
                csd_ratio=0.75,
            )
        ),
        "standard_clean_supported": decide(
            CLCPolicyFeatures.from_condition_name(
                "standard_budget144",
                memory_bad_rate=0.148,
                probe_drop=0.028,
                csd_ratio=0.75,
            )
        ),
        "standard_moderate_risk": decide(
            CLCPolicyFeatures.from_condition_name(
                "standard_budget144",
                memory_bad_rate=0.25,
                probe_drop=0.08,
                csd_ratio=0.90,
            )
        ),
        "ogcf_bridge_risk": decide(
            CLCPolicyFeatures.from_condition_name(
                "standard_budget144",
                memory_bad_rate=0.25655,
                probe_drop=0.116,
                csd_ratio=1.2311,
            )
        ),
        "hard_severe_risk": decide(
            CLCPolicyFeatures.from_condition_name(
                "hard_budget144",
                memory_bad_rate=0.75,
                probe_drop=0.18,
                csd_ratio=1.40,
            )
        ),
        "long_clean": decide(
            CLCPolicyFeatures.from_condition_name(
                "long2_standard_budget288",
                memory_bad_rate=0.20,
                probe_drop=0.03,
                csd_ratio=0.60,
            )
        ),
        "long_severe": decide(
            CLCPolicyFeatures.from_condition_name(
                "long2_standard_budget288",
                memory_bad_rate=0.60,
                probe_drop=0.17,
                csd_ratio=1.30,
            )
        ),
        "label_cost_guard": decide(
            CLCPolicyFeatures.from_condition_name(
                "hard_budget144",
                memory_bad_rate=0.80,
                probe_drop=0.20,
                csd_ratio=1.50,
                label_cost=0.001,
            )
        ),
    }
    checks = {
        "hard_clean_can_protect": cases["hard_clean_supported"]["decision"]["policy"] == POLICY_PERIODIC,
        "standard_clean_can_protect": cases["standard_clean_supported"]["decision"]["policy"] == POLICY_PERIODIC,
        "standard_moderate_uses_verified_refresh": cases["standard_moderate_risk"]["decision"]["policy"]
        == POLICY_LONG_SEVERE,
        "ogcf_bridge_risk_uses_verified_refresh": cases["ogcf_bridge_risk"]["decision"]["policy"]
        == POLICY_LONG_SEVERE,
        "hard_severe_uses_xseq": cases["hard_severe_risk"]["decision"]["policy"] == POLICY_XSEQ_MEMORY,
        "long_clean_stays_periodic": cases["long_clean"]["decision"]["policy"] == POLICY_PERIODIC,
        "long_severe_uses_verified_refresh_not_xseq": cases["long_severe"]["decision"]["policy"]
        == POLICY_LONG_SEVERE,
        "label_cost_guard_still_protects": cases["label_cost_guard"]["decision"]["policy"] == POLICY_PERIODIC,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "cases": cases,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# CLC Policy Feature Signal Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
