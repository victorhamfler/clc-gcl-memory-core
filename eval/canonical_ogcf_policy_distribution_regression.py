from __future__ import annotations

import copy
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


OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_policy_distribution_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_policy_distribution_regression_report.md"


def row(
    memory_id: str,
    score: float,
    *,
    support_count: int = 1,
    is_keeper: bool = True,
) -> dict[str, Any]:
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "score": score,
        "cosine": score,
        "text": "Cedar Map uses selector outcome logs for adaptive memory routing.",
        "text_match_score": 0.9,
        "claim_scope_score": 0.9,
        "stored_contradiction_score": 0.0,
        "supersession_score": 0.0,
        "relation_supersession_score": 0.0,
        "source_reliability": 0.0,
        "domain_reliability": 0.0,
        "authority_state": "standalone",
        "canonical_claim_key": "claim::cedar-map-routing",
        "canonical_keeper_memory_id": memory_id if is_keeper else "mem_supported_keeper",
        "canonical_support_count": support_count,
        "canonical_duplicate_count": max(0, support_count - 1),
        "canonical_is_keeper": is_keeper,
        "canonical_score_adjustment": 0.08 if is_keeper and support_count > 1 else 0.0,
    }


def strip_canonical(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if not key.startswith("canonical_")}
        for row in rows
    ]


def bridge_meta(memory_ids: list[str]) -> dict[str, Any]:
    return {
        "max_interaction_z": 2.81,
        "bridge_overload_score": 0.937,
        "loop_count": 10,
        "risk_regions": [
            {
                "clusters": "15-31-59",
                "interaction_z": 2.81,
                "failure_mode": "bridge_overload",
                "recommended_action": "split_cluster",
            }
        ],
        "bridge_clusters": [{"cluster_id": 15, "size": 25, "unique_domains": 25}],
        "cluster_summary": [{"cluster_id": 15, "size": 25, "local_defect": 0.05}],
        "memory_cluster_map": {memory_id: 15 for memory_id in memory_ids},
    }


def run_mode(rows: list[dict[str, Any]], *, canonical: bool, ogcf: bool) -> dict[str, Any]:
    active_rows = copy.deepcopy(rows if canonical else strip_canonical(rows))
    features, diagnostics = selector_features_from_retrieval_context(
        active_rows,
        condition_name="standard_budget144",
    )
    if ogcf:
        features, diagnostics = augment_selector_features(
            features,
            active_rows,
            bridge_meta([str(row.get("memory_id") or row.get("id")) for row in active_rows]),
            diagnostics,
        )
    decision = CLCPolicySelector().select(features)
    return {
        "features": asdict(features),
        "diagnostics": diagnostics,
        "decision": asdict(decision),
    }


def main() -> int:
    supported_rows = [
        row("mem_supported_keeper", 0.92, support_count=8, is_keeper=True),
        row("mem_supported_context_1", 0.88),
        row("mem_supported_context_2", 0.84),
    ]
    duplicate_pressure_rows = [
        row("mem_dup_keeper", 0.92, support_count=8, is_keeper=True),
        row("mem_dup_1", 0.89, support_count=8, is_keeper=False),
        row("mem_dup_2", 0.87, support_count=8, is_keeper=False),
        row("mem_dup_3", 0.85, support_count=8, is_keeper=False),
    ]

    supported_modes = {
        "base": run_mode(supported_rows, canonical=False, ogcf=False),
        "canonical": run_mode(supported_rows, canonical=True, ogcf=False),
        "ogcf": run_mode(supported_rows, canonical=False, ogcf=True),
        "combined": run_mode(supported_rows, canonical=True, ogcf=True),
    }
    duplicate_modes = {
        "base": run_mode(duplicate_pressure_rows, canonical=False, ogcf=False),
        "canonical": run_mode(duplicate_pressure_rows, canonical=True, ogcf=False),
        "ogcf": run_mode(duplicate_pressure_rows, canonical=False, ogcf=True),
        "combined": run_mode(duplicate_pressure_rows, canonical=True, ogcf=True),
    }

    checks = {
        "canonical_clean_support_can_protect": supported_modes["canonical"]["decision"]["action"] == "PROTECT_PERIODIC",
        "ogcf_bridge_risk_changes_policy_vs_clean_canonical": supported_modes["ogcf"]["decision"]["action"]
        == "LONG_SEVERE_VERIFIED_REFRESH"
        and supported_modes["combined"]["decision"]["action"] == "LONG_SEVERE_VERIFIED_REFRESH",
        "combined_keeps_ogcf_diagnostics": supported_modes["combined"]["diagnostics"].get(
            "ogcf_bridge_overload_score", 0.0
        )
        > 0.5
        and supported_modes["combined"]["diagnostics"].get("ogcf_affected_memory_ratio", 0.0) > 0.0,
        "duplicate_pressure_blocks_clean_protect": duplicate_modes["canonical"]["decision"]["action"]
        == "LONG_SEVERE_VERIFIED_REFRESH"
        and duplicate_modes["canonical"]["diagnostics"].get("canonical_duplicate_pressure", 0.0) >= 0.7,
        "policy_distribution_not_collapsed": len(
            {
                supported_modes["canonical"]["decision"]["action"],
                supported_modes["combined"]["decision"]["action"],
                duplicate_modes["canonical"]["decision"]["action"],
            }
        )
        >= 2,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "supported_modes": supported_modes,
        "duplicate_modes": duplicate_modes,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical + OGCF Policy Distribution Regression\n\n"
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
