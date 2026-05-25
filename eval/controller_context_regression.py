from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.controller_context import build_adaptive_memory_context
from core.ogcf_selector import augment_selector_features
from core.selector_runtime import (
    apply_retrieval_policy_guard,
    build_policy_selector,
    selector_features_from_retrieval_context,
)


OUT_JSON = REPO_ROOT / "experiments" / "controller_context_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_context_regression_report.md"


def fixture_rows() -> list[dict]:
    return [
        {
            "memory_id": "mem_current_bridge",
            "id": "mem_current_bridge",
            "text": "The current bridge synthesis plan connects OGCF geometry with canonical memory support.",
            "score": 0.92,
            "cosine": 0.92,
            "text_match_score": 0.78,
            "claim_scope_score": 0.82,
            "answer_type_score": 0.70,
            "authority_state": "current",
            "canonical_support_count": 4,
            "canonical_is_keeper": True,
        },
        {
            "memory_id": "mem_bridge_cluster",
            "id": "mem_bridge_cluster",
            "text": "OGCF bridge cluster pressure can indicate cross-domain composition risk.",
            "score": 0.84,
            "cosine": 0.84,
            "text_match_score": 0.66,
            "claim_scope_score": 0.70,
            "answer_type_score": 0.60,
            "authority_state": "current",
            "canonical_support_count": 1,
            "canonical_is_keeper": True,
        },
    ]


def fixture_ogcf_meta() -> dict:
    return {
        "bridge_overload_score": 0.96,
        "max_interaction_z": 2.8,
        "loop_count": 1,
        "cluster_summary": [{"cluster_id": 7, "size": 2}],
        "bridge_clusters": [{"cluster_id": 7, "reason": "fixture_bridge"}],
        "risk_regions": [{"clusters": "7", "interaction_z": 2.8}],
        "memory_cluster_map": {"mem_current_bridge": 7, "mem_bridge_cluster": 7},
    }


def expected_snapshot(root: Path, config: dict, payload: dict, rows: list[dict]) -> dict:
    features, diagnostics = selector_features_from_retrieval_context(
        rows,
        condition_name=str(payload.get("condition_name") or "hard_budget144"),
        label_cost=float(payload.get("label_cost", 0.0002) or 0.0002),
        budget_pressure=float(payload.get("budget_pressure", 0.2) or 0.2),
    )
    features, diagnostics = augment_selector_features(
        features,
        rows,
        payload["ogcf_meta"],
        diagnostics,
        query=str(payload.get("query") or ""),
        ogcf_intent_config=config.get("ogcf_intent"),
    )
    selector = build_policy_selector(root, config)
    decision = apply_retrieval_policy_guard(selector.select(features), features, diagnostics)
    return {
        "policy": decision.policy,
        "action": decision.action,
        "reason": decision.reason,
        "confidence": decision.confidence,
        "diagnostics": diagnostics,
    }


def main() -> int:
    rows = fixture_rows()
    config = {
        "selector": {"mode": "current"},
        "ogcf_intent": {
            "bridge_terms": "bridge,cross-domain,synthesis",
            "geometry_terms": "ogcf,geometry,cluster",
        },
    }
    payload = {
        "query": "Should this cross-domain OGCF bridge synthesis be treated as bridge risk?",
        "condition_name": "hard_budget144",
        "label_cost": 0.0002,
        "budget_pressure": 0.2,
        "ogcf_meta": fixture_ogcf_meta(),
    }
    context = build_adaptive_memory_context(
        root=ROOT,
        config=config,
        payload=payload,
        retrieval_rows=rows,
        include_decision=True,
    )
    snapshot = context.selector_snapshot()
    expected = expected_snapshot(ROOT, config, payload, rows)
    no_rows = build_adaptive_memory_context(
        root=ROOT,
        config=config,
        payload={"condition_name": "standard_budget144"},
        retrieval_rows=None,
        include_decision=True,
    )
    checks = {
        "context_ok": context.ok is True,
        "schema_ok": snapshot.get("schema") == "adaptive_memory_context/v1",
        "ogcf_present": snapshot.get("ogcf_meta_present") is True,
        "decision_matches_existing_path": (snapshot.get("decision") or {}).get("policy") == expected["policy"]
        and (snapshot.get("decision") or {}).get("action") == expected["action"]
        and (snapshot.get("decision") or {}).get("reason") == expected["reason"],
        "ogcf_diagnostics_present": float(snapshot.get("diagnostics", {}).get("ogcf_bridge_overload_score") or 0.0) > 0.0,
        "selector_context_has_rows": len(context.selector_context().get("retrieval_context") or []) == 2,
        "no_rows_context_ok": no_rows.ok is True and no_rows.decision is not None,
    }
    report = {
        "schema": "controller_context_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "snapshot": snapshot,
        "expected_decision": {key: expected[key] for key in ("policy", "action", "reason", "confidence")},
        "no_rows_snapshot": no_rows.selector_snapshot(),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Context Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
