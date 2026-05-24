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
from core.config import load_config  # noqa: E402
from core.ogcf_intent import classify_ogcf_intent, normalize_ogcf_intent_config  # noqa: E402
from core.ogcf_selector import augment_selector_features  # noqa: E402
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_intent_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_intent_config_regression_report.md"


def meta(memory_ids: list[str]) -> dict[str, Any]:
    return {
        "max_interaction_z": 0.0,
        "bridge_overload_score": 0.0,
        "loop_count": 0,
        "risk_regions": [],
        "bridge_clusters": [{"cluster_id": 4, "size": 12, "unique_domains": 3}],
        "cluster_summary": [{"cluster_id": 4, "size": 12, "local_defect": 0.0}],
        "memory_cluster_map": {memory_id: 4 for memory_id in memory_ids},
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
        "text": "Meshlink routing memory joins weather, preference, and selector evidence.",
    }


def run(
    query: str,
    rows: list[dict[str, Any]],
    intent_config: dict[str, Any] | None,
    affected_memory_ids: list[str],
) -> dict[str, Any]:
    features, diagnostics = selector_features_from_retrieval_context(rows, condition_name="standard_budget144")
    augmented, augmented_diagnostics = augment_selector_features(
        features,
        rows,
        meta(affected_memory_ids),
        diagnostics,
        query=query,
        ogcf_intent_config=intent_config,
    )
    decision = CLCPolicySelector().select(augmented)
    return {
        "features": asdict(augmented),
        "diagnostics": augmented_diagnostics,
        "decision": asdict(decision),
    }


def main() -> int:
    root_config = load_config(ROOT)
    normalized = normalize_ogcf_intent_config(root_config.get("ogcf_intent"))
    custom_config = {
        "bridge_terms": "meshlink",
        "gate": {
            "high_intent_threshold": 0.75,
            "medium_intent_threshold": 0.55,
            "high_affected_multiplier": 0.75,
            "medium_min_weighted_ratio": 0.35,
            "low_min_weighted_ratio": 0.95,
        },
    }
    rows = [
        row("mem_meshlink_1", score=0.42, text_match=0.05, claim_scope=0.05),
        row("mem_meshlink_2", score=0.35, text_match=0.00, claim_scope=0.00),
        row("mem_context", score=0.90, text_match=0.90, claim_scope=0.90),
    ]

    query = "Why is meshlink important for memory?"
    default_intent = classify_ogcf_intent(query, rows)
    custom_intent = classify_ogcf_intent(query, rows, custom_config)
    affected_ids = ["mem_meshlink_1", "mem_meshlink_2"]
    default_run = run(query, rows, None, affected_ids)
    custom_run = run(query, rows, custom_config, affected_ids)

    checks = {
        "config_section_loaded": isinstance(root_config.get("ogcf_intent"), dict),
        "normalized_config_has_gate": "gate" in normalized and "high_intent_threshold" in normalized["gate"],
        "custom_term_changes_intent": default_intent.intent != "cross_domain_bridge_synthesis"
        and custom_intent.intent == "cross_domain_bridge_synthesis",
        "custom_term_allows_pressure": custom_run["diagnostics"].get("ogcf_effective_affected_memory_ratio", 0.0)
        > default_run["diagnostics"].get("ogcf_effective_affected_memory_ratio", 0.0),
        "decision_path_still_valid": custom_run["decision"]["action"] in {
            "PROTECT_PERIODIC",
            "LONG_SEVERE_VERIFIED_REFRESH",
            "XSEQ_MEMORY_REFRESH",
        },
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "default_intent": asdict(default_intent),
        "custom_intent": asdict(custom_intent),
        "default_run": default_run,
        "custom_run": custom_run,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# OGCF Intent Config Regression\n\n"
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
