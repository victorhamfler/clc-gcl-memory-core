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


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_intent_gate_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_intent_gate_regression_report.md"


def meta(memory_ids: list[str], *, true_loop: bool = False) -> dict[str, Any]:
    return {
        "max_interaction_z": 2.7 if true_loop else 0.0,
        "bridge_overload_score": 0.9 if true_loop else 0.0,
        "loop_count": 3 if true_loop else 0,
        "risk_regions": [
            {
                "clusters": "7-8-9",
                "interaction_z": 2.7,
                "failure_mode": "bridge_overload",
                "recommended_action": "review",
            }
        ]
        if true_loop
        else [],
        "bridge_clusters": [{"cluster_id": 7, "size": 18, "unique_domains": 4}],
        "cluster_summary": [{"cluster_id": 7, "size": 18, "local_defect": 0.0}],
        "memory_cluster_map": {memory_id: 7 for memory_id in memory_ids},
    }


def row(memory_id: str, *, score: float, text_match: float, claim_scope: float, text: str) -> dict[str, Any]:
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
        "text": text,
    }


def run(query: str, rows: list[dict[str, Any]], ogcf_meta: dict[str, Any]) -> dict[str, Any]:
    features, diagnostics = selector_features_from_retrieval_context(rows, condition_name="standard_budget144")
    augmented, augmented_diagnostics = augment_selector_features(
        features,
        rows,
        ogcf_meta,
        diagnostics,
        query=query,
    )
    decision = CLCPolicySelector().select(augmented)
    return {
        "features": asdict(augmented),
        "diagnostics": augmented_diagnostics,
        "decision": asdict(decision),
    }


def main() -> int:
    rows = [
        row(
            "mem_bridge_1",
            score=0.46,
            text_match=0.10,
            claim_scope=0.10,
            text="Aurelia routing bridge diagnostic across weather, routine, and selector memories.",
        ),
        row(
            "mem_bridge_2",
            score=0.40,
            text_match=0.05,
            claim_scope=0.05,
            text="Cross-domain selector refresh note connecting calendar and robotics claims.",
        ),
        row(
            "mem_bridge_3",
            score=0.31,
            text_match=0.0,
            claim_scope=0.0,
            text="Bridge cluster evidence about embedding geometry and loop pressure.",
        ),
        row(
            "mem_context",
            score=0.89,
            text_match=0.89,
            claim_scope=0.89,
            text="Victor has a normal calendar preference fact stored as current evidence.",
        ),
    ]
    non_loop_meta = meta(["mem_bridge_1", "mem_bridge_2", "mem_bridge_3"])
    loop_meta = meta(["mem_bridge_1"], true_loop=True)

    ordinary = run("What is Victor's calendar preference?", rows, non_loop_meta)
    explicit_geometry = run("What OGCF bridge geometry connects the selector refresh memories?", rows, non_loop_meta)
    true_loop = run("What is Victor's calendar preference?", rows, loop_meta)

    checks = {
        "ordinary_query_gates_passive_bridge_membership": ordinary["diagnostics"].get(
            "ogcf_effective_affected_memory_ratio"
        )
        == 0.0
        and ordinary["diagnostics"].get("ogcf_csd_ratio_delta") == 0.0,
        "explicit_geometry_query_allows_passive_bridge_pressure": explicit_geometry["diagnostics"].get(
            "ogcf_effective_affected_memory_ratio", 0.0
        )
        > 0.35
        and explicit_geometry["diagnostics"].get("ogcf_csd_ratio_delta", 0.0) > 0.0,
        "true_loop_pressure_survives_ordinary_intent": true_loop["diagnostics"].get(
            "ogcf_memory_bad_rate_delta", 0.0
        )
        > 0.0
        and true_loop["diagnostics"].get("ogcf_bridge_overload_score", 0.0) > 0.5,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "ordinary": ordinary,
        "explicit_geometry": explicit_geometry,
        "true_loop": true_loop,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# OGCF Intent Gate Regression\n\n"
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
