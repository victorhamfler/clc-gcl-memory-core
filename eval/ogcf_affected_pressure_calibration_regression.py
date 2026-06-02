from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicySelector  # noqa: E402
from core.ogcf_selector import augment_selector_features  # noqa: E402
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_affected_pressure_calibration_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_affected_pressure_calibration_regression_report.md"


def bridge_cluster_meta(memory_ids: list[str], *, true_loop: bool = False) -> dict[str, Any]:
    return {
        "max_interaction_z": 2.6 if true_loop else 0.0,
        "bridge_overload_score": 0.86 if true_loop else 0.0,
        "loop_count": 4 if true_loop else 0,
        "risk_regions": [
            {
                "clusters": "7-8-9",
                "interaction_z": 2.6,
                "failure_mode": "bridge_overload",
                "recommended_action": "review",
            }
        ]
        if true_loop
        else [],
        "bridge_clusters": [{"cluster_id": 7, "size": 20, "unique_domains": 5}],
        "cluster_summary": [{"cluster_id": 7, "size": 20, "local_defect": 0.0}],
        "memory_cluster_map": {memory_id: 7 for memory_id in memory_ids},
    }


def row(memory_id: str, *, score: float, text_match: float, claim_scope: float) -> dict[str, Any]:
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "score": score,
        "cosine": score,
        "text_match_score": text_match,
        "claim_scope_score": claim_scope,
        "answer_type_score": 0.0,
        "stored_contradiction_score": 0.0,
        "supersession_score": 0.0,
        "relation_supersession_score": 0.0,
        "source_reliability": 0.0,
        "domain_reliability": 0.0,
        "authority_state": "standalone",
        "text": "Aurelia bridge routing diagnostic memory.",
    }


def run(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    features, diagnostics = selector_features_from_retrieval_context(rows, condition_name="standard_budget144")
    augmented, augmented_diagnostics = augment_selector_features(features, rows, meta, diagnostics)
    decision = CLCPolicySelector().select(augmented)
    return {
        "features": asdict(augmented),
        "diagnostics": augmented_diagnostics,
        "decision": asdict(decision),
    }


def main() -> int:
    weak_rows = [
        row("mem_weak_1", score=0.45, text_match=0.10, claim_scope=0.10),
        row("mem_weak_2", score=0.35, text_match=0.05, claim_scope=0.05),
        row("mem_weak_3", score=0.25, text_match=0.00, claim_scope=0.00),
        row("mem_context", score=0.90, text_match=0.90, claim_scope=0.90),
    ]
    strong_rows = [
        row("mem_strong_1", score=0.92, text_match=0.92, claim_scope=0.92),
        row("mem_strong_2", score=0.88, text_match=0.88, claim_scope=0.88),
        row("mem_strong_3", score=0.84, text_match=0.84, claim_scope=0.84),
        row("mem_strong_4", score=0.80, text_match=0.80, claim_scope=0.80),
    ]

    weak = run(weak_rows, bridge_cluster_meta(["mem_weak_1", "mem_weak_2", "mem_weak_3"]))
    strong = run(strong_rows, bridge_cluster_meta([row["memory_id"] for row in strong_rows]))
    true_loop = run(weak_rows, bridge_cluster_meta(["mem_weak_1"], true_loop=True))

    checks = {
        "weak_bridge_membership_is_gated": weak["diagnostics"].get("ogcf_effective_affected_memory_ratio") == 0.0
        and weak["diagnostics"].get("ogcf_csd_ratio_delta") == 0.0,
        "strong_bridge_membership_keeps_pressure": strong["diagnostics"].get(
            "ogcf_effective_affected_memory_ratio", 0.0
        )
        > 0.55
        and strong["diagnostics"].get("ogcf_csd_ratio_delta", 0.0) > 0.0,
        "true_loop_overload_bypasses_membership_gate": true_loop["diagnostics"].get(
            "ogcf_bridge_overload_score", 0.0
        )
        > 0.5
        and true_loop["diagnostics"].get("ogcf_memory_bad_rate_delta", 0.0) > 0.0,
        "bridge_overload_does_not_create_contradiction_peak": true_loop["diagnostics"].get(
            "adjusted_contradiction_peak"
        )
        == true_loop["diagnostics"].get("contradiction_peak")
        == 0.0
        and true_loop["diagnostics"].get("ogcf_structural_pressure", 0.0) > 0.0,
    }
    result = {"ok": all(checks.values()), "checks": checks, "weak": weak, "strong": strong, "true_loop": true_loop}
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# OGCF Affected-Pressure Calibration Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps({"checks": checks}, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
