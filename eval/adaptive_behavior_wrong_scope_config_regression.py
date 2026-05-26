from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_behavior_shadow import adaptive_behavior_shadow_advisories  # noqa: E402
from core.config import load_config  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_wrong_scope_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_wrong_scope_config_regression_report.md"


@dataclass
class Context:
    diagnostics: dict[str, Any]
    retrieval_context: list[dict[str, Any]]
    ogcf_meta_present: bool = False
    ok: bool = True

    def feature_dict(self) -> dict[str, Any]:
        return {
            "memory_bad_rate": self.diagnostics.get("memory_bad_rate", 0.18),
            "probe_drop": self.diagnostics.get("probe_drop", 0.04),
            "csd_ratio": self.diagnostics.get("csd_ratio", 0.75),
        }


def row(
    memory_id: str,
    *,
    score: float = 0.62,
    claim_scope: float = 0.75,
    answer_type: float = 0.0,
    scope_deflection: float = 0.0,
) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "score": score,
        "claim_scope_score": claim_scope,
        "text_match_score": 0.6,
        "answer_type_score": answer_type,
        "intent_match_score": 0.0,
        "scope_deflection_penalty": scope_deflection,
        "authority_state": "standalone",
    }


def decision(payload: dict[str, Any], family: str) -> dict[str, Any]:
    for item in payload.get("decisions") or []:
        if isinstance(item, dict) and item.get("behavior_family") == family:
            return item
    return {}


def config_with_shadow(base_config: dict[str, Any], **shadow_overrides: Any) -> dict[str, Any]:
    updated = copy.deepcopy(base_config)
    shadow = updated.setdefault("shadow", {})
    if not isinstance(shadow, dict):
        shadow = {}
        updated["shadow"] = shadow
    shadow.update(shadow_overrides)
    return updated


def run_case(case: dict[str, Any], base_config: dict[str, Any]) -> dict[str, Any]:
    selected = case.get("evidence") or []
    retrieval_context = case.get("retrieval_context") or selected
    context = Context(
        diagnostics=case.get("diagnostics") or {},
        retrieval_context=retrieval_context,
    )
    payload = adaptive_behavior_shadow_advisories(
        query=case["query"],
        answer=case.get("answer") or "Answer grounded in selected memory evidence.",
        evidence=selected,
        stale_context=case.get("stale_context") or [],
        adaptive_context=context,
        resolver_shadow=case.get("resolver_shadow"),
        config=config_with_shadow(base_config, **(case.get("shadow_overrides") or {})),
    )
    wrong_scope = decision(payload, "wrong_scope")
    probability = wrong_scope.get("shadow_probability")
    route_confidence = wrong_scope.get("route_confidence")
    expected_probability = case.get("expected_probability")
    expected_route_confidence = case.get("expected_route_confidence")
    probability_ok = abs(float(probability) - float(expected_probability)) <= 1e-6
    route_confidence_ok = abs(float(route_confidence) - float(expected_route_confidence)) <= 1e-6
    advisory_ok = wrong_scope.get("advisory") == case["expected_advisory"]
    required_reasons = case.get("required_reasons") or []
    actual_reasons = wrong_scope.get("reasons") or []
    reasons_ok = all(reason in actual_reasons for reason in required_reasons)
    return {
        "id": case["id"],
        "description": case["description"],
        "query": case["query"],
        "shadow_overrides": case.get("shadow_overrides") or {},
        "expected_advisory": case["expected_advisory"],
        "actual_advisory": wrong_scope.get("advisory"),
        "expected_probability": expected_probability,
        "actual_probability": probability,
        "expected_route_confidence": expected_route_confidence,
        "actual_route_confidence": route_confidence,
        "required_reasons": required_reasons,
        "actual_reasons": actual_reasons,
        "passed": bool(advisory_ok and probability_ok and route_confidence_ok and reasons_ok),
        "checks": {
            "advisory_ok": advisory_ok,
            "probability_ok": probability_ok,
            "route_confidence_ok": route_confidence_ok,
            "reasons_ok": reasons_ok,
        },
    }


def cases() -> list[dict[str, Any]]:
    selected_weak = [row("mem_weak_scope", score=0.58, claim_scope=0.05, answer_type=0.05)]
    candidate_scope_available = [row("mem_scope_candidate", score=0.67, claim_scope=0.72)]
    selected_normal = [row("mem_selected", score=0.68, claim_scope=0.7)]
    return [
        {
            "id": "default_scope_deflection_positive",
            "description": "Explicit scope deflection remains a positive wrong-scope advisory.",
            "query": "Who approves GitHub uploads?",
            "evidence": selected_normal,
            "retrieval_context": [row("mem_deflect", scope_deflection=0.30)],
            "expected_advisory": "likely_helpful",
            "expected_probability": 0.78,
            "expected_route_confidence": 0.56,
            "required_reasons": ["scope_deflection_signal"],
        },
        {
            "id": "config_sets_scope_deflection_probability",
            "description": "Scope-deflection probability is configurable.",
            "query": "Who approves GitHub uploads?",
            "evidence": selected_normal,
            "retrieval_context": [row("mem_deflect", scope_deflection=0.30)],
            "shadow_overrides": {"wrong_scope_deflection_probability": 0.70},
            "expected_advisory": "likely_helpful",
            "expected_probability": 0.70,
            "expected_route_confidence": 0.56,
            "required_reasons": ["scope_deflection_signal"],
        },
        {
            "id": "config_sets_no_evidence_github_probability",
            "description": "No-evidence GitHub approval scope queries can be tuned through config.",
            "query": "Is GitHub approval automatic?",
            "shadow_overrides": {"wrong_scope_no_evidence_github_probability": 0.66},
            "expected_advisory": "likely_helpful",
            "expected_probability": 0.66,
            "expected_route_confidence": 0.56,
            "required_reasons": ["scope_sensitive_query_without_selected_evidence"],
        },
        {
            "id": "config_sets_no_evidence_probability",
            "description": "No-evidence scope-sensitive probability is configurable and can remain neutral.",
            "query": "Who owns the calendar policy?",
            "shadow_overrides": {"wrong_scope_no_evidence_probability": 0.61},
            "expected_advisory": "uncertain_keep_symbolic",
            "expected_probability": 0.61,
            "expected_route_confidence": 0.56,
            "required_reasons": ["scope_sensitive_query_without_selected_evidence"],
        },
        {
            "id": "config_sets_selected_evidence_probability",
            "description": "Selected-evidence scope-sensitive neutrality is configurable.",
            "query": "Does calendar approval need Victor?",
            "evidence": selected_normal,
            "shadow_overrides": {"wrong_scope_selected_evidence_probability": 0.48},
            "expected_advisory": "uncertain_keep_symbolic",
            "expected_probability": 0.48,
            "expected_route_confidence": 0.56,
            "required_reasons": ["scope_sensitive_query_with_selected_evidence"],
        },
        {
            "id": "config_sets_low_route_confidence",
            "description": "Weak selected scope without a scope-sensitive query uses the configurable low route confidence.",
            "query": "Summarize deployment operations",
            "evidence": selected_weak,
            "retrieval_context": selected_weak + candidate_scope_available,
            "shadow_overrides": {
                "wrong_scope_deflection_probability": 0.63,
                "wrong_scope_low_route_confidence": 0.38,
            },
            "expected_advisory": "uncertain_keep_symbolic",
            "expected_probability": 0.63,
            "expected_route_confidence": 0.38,
            "required_reasons": ["scope_deflection_signal", "candidate_scope_match_available"],
        },
    ]


def build_report() -> dict[str, Any]:
    base_config = load_config(ROOT).get("adaptive_behavior") or {}
    rows = [run_case(case, base_config) for case in cases()]
    return {
        "schema": "adaptive_behavior_wrong_scope_config_regression/v1",
        "candidate": "wrong_scope_configurable_control_surface",
        "description": "Regression guard proving wrong-scope shadow behavior is config-controlled and report-only.",
        "ok": all(item["passed"] for item in rows),
        "case_count": len(rows),
        "passed_count": sum(1 for item in rows if item["passed"]),
        "cases": rows,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Wrong-Scope Config Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate: `{report['candidate']}`",
        f"Cases: `{report['passed_count']}/{report['case_count']}`",
        "",
        "| case | expected | actual | probability | route confidence | pass | reasons |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in report["cases"]:
        reasons = ", ".join(item.get("actual_reasons") or [])
        lines.append(
            f"| `{item['id']}` | `{item['expected_advisory']}` | `{item['actual_advisory']}` | "
            f"`{item['actual_probability']}` | `{item['actual_route_confidence']}` | `{item['passed']}` | {reasons} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "passed": report["passed_count"],
                "total": report["case_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
