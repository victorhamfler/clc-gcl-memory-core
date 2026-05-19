from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.clc_policy_selector import POLICY_LONG_SEVERE, POLICY_PERIODIC  # noqa: E402
from core.selector_runtime import (  # noqa: E402
    apply_retrieval_explanation_guard,
    build_policy_selector,
    selector_features_from_retrieval_context,
)


OUT_JSON = REPO_ROOT / "experiments" / "selector_retrieval_feature_eval_results.json"


STALE_CONTEXT = [
    {
        "memory_id": "old_pref_1",
        "score": 0.92,
        "stored_contradiction_score": 0.9,
        "supersession_score": -0.8,
        "relation_supersession_score": -0.7,
        "source_reliability": -0.2,
        "domain_reliability": -0.1,
        "authority_state": "superseded",
        "superseded_by_memory_ids": ["new_pref_1"],
        "text": "Victor likes espresso and green tea.",
    },
    {
        "memory_id": "old_pref_2",
        "score": 0.88,
        "stored_contradiction_score": 0.75,
        "supersession_score": -0.6,
        "relation_supersession_score": -0.5,
        "source_reliability": -0.1,
        "domain_reliability": 0.0,
        "authority_state": "stale",
        "superseded_by_memory_ids": ["new_pref_1"],
        "text": "Victor's old drink preference was espresso.",
    },
    {
        "memory_id": "new_pref_1",
        "score": 0.84,
        "stored_contradiction_score": 0.0,
        "supersession_score": 0.8,
        "relation_supersession_score": 0.7,
        "source_reliability": 0.4,
        "domain_reliability": 0.3,
        "authority_state": "authoritative",
        "supersedes_memory_ids": ["old_pref_1", "old_pref_2"],
        "text": "Victor currently drinks water, not espresso or green tea.",
    },
]

CLEAN_CONTEXT = [
    {
        "memory_id": "current_1",
        "score": 0.91,
        "stored_contradiction_score": 0.0,
        "supersession_score": 0.7,
        "relation_supersession_score": 0.6,
        "source_reliability": 0.5,
        "domain_reliability": 0.4,
        "authority_state": "authoritative",
        "supersedes_memory_ids": ["old_1"],
        "text": "Victor currently drinks water.",
    },
    {
        "memory_id": "current_2",
        "score": 0.86,
        "stored_contradiction_score": 0.0,
        "supersession_score": 0.2,
        "relation_supersession_score": 0.1,
        "source_reliability": 0.4,
        "domain_reliability": 0.3,
        "authority_state": "current",
        "text": "Victor's current beverage preference is water.",
    },
]


def main() -> int:
    config = load_config(ROOT)
    selector = build_policy_selector(ROOT, config)
    stale_features, stale_diagnostics = selector_features_from_retrieval_context(
        STALE_CONTEXT,
        condition_name="hard_budget144",
    )
    clean_features, clean_diagnostics = selector_features_from_retrieval_context(
        CLEAN_CONTEXT,
        condition_name="standard_budget144",
    )
    stale_explanation = apply_retrieval_explanation_guard(
        selector.explain(stale_features, top_k=5),
        stale_features,
        stale_diagnostics,
    )
    clean_explanation = apply_retrieval_explanation_guard(
        selector.explain(clean_features, top_k=5),
        clean_features,
        clean_diagnostics,
    )
    failures = []
    if not stale_features.hard:
        failures.append("stale retrieval context should produce hard selector features")
    if stale_diagnostics["stale_ratio"] < 0.5:
        failures.append("stale retrieval context should expose high stale ratio")
    if stale_explanation["decision"]["policy"] != POLICY_LONG_SEVERE:
        failures.append(f"stale retrieval context should select long severe, got {stale_explanation['decision']['policy']}")
    if clean_features.hard:
        failures.append("clean retrieval context should not produce hard selector features")
    if clean_diagnostics["stale_ratio"] != 0.0:
        failures.append("clean retrieval context should have zero stale ratio")
    if clean_explanation["decision"]["policy"] != POLICY_PERIODIC:
        failures.append(f"clean retrieval guard should protect periodic, got {clean_explanation['decision']['policy']}")

    report = {
        "ok": not failures,
        "stale": {
            "features": stale_features.__dict__,
            "diagnostics": stale_diagnostics,
            "decision": stale_explanation["decision"],
            "retrieval_guard": stale_explanation.get("retrieval_guard"),
            "votes": stale_explanation["votes"],
            "nearest_samples": stale_explanation["nearest_samples"][:5],
        },
        "clean": {
            "features": clean_features.__dict__,
            "diagnostics": clean_diagnostics,
            "decision": clean_explanation["decision"],
            "base_decision": clean_explanation.get("base_decision"),
            "retrieval_guard": clean_explanation.get("retrieval_guard"),
            "votes": clean_explanation["votes"],
            "nearest_samples": clean_explanation["nearest_samples"][:5],
        },
        "failures": failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
