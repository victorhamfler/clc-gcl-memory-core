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


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_stale_conflict_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_stale_conflict_config_regression_report.md"


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


def row(memory_id: str, *, score: float = 0.62, claim_scope: float = 0.75, text: float = 0.6) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "score": score,
        "claim_scope_score": claim_scope,
        "text_match_score": text,
        "answer_type_score": 0.0,
        "intent_match_score": 0.0,
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
    config = config_with_shadow(base_config, **(case.get("shadow_overrides") or {}))
    selected = case.get("evidence") or [row("mem_current")]
    stale_context = case.get("stale_context") or [row("mem_old", score=0.51, claim_scope=0.5)]
    context = Context(
        diagnostics=case.get("diagnostics") or {},
        retrieval_context=case.get("retrieval_context") or selected,
    )
    payload = adaptive_behavior_shadow_advisories(
        query=case["query"],
        answer=case.get("answer") or "Answer grounded in selected memory evidence.",
        evidence=selected,
        stale_context=stale_context,
        adaptive_context=context,
        resolver_shadow=case.get("resolver_shadow"),
        config=config,
    )
    stale = decision(payload, "stale_conflict")
    probability = stale.get("shadow_probability")
    expected_probability = case.get("expected_probability")
    probability_ok = True
    if expected_probability is not None:
        probability_ok = abs(float(probability) - float(expected_probability)) <= 1e-6
    required_reasons = case.get("required_reasons") or []
    reasons = stale.get("reasons") or []
    reasons_ok = all(reason in reasons for reason in required_reasons)
    advisory_ok = stale.get("advisory") == case["expected_advisory"]
    return {
        "id": case["id"],
        "description": case["description"],
        "query": case["query"],
        "shadow_overrides": case.get("shadow_overrides") or {},
        "expected_advisory": case["expected_advisory"],
        "actual_advisory": stale.get("advisory"),
        "expected_probability": expected_probability,
        "actual_probability": probability,
        "required_reasons": required_reasons,
        "actual_reasons": reasons,
        "passed": bool(advisory_ok and probability_ok and reasons_ok),
        "checks": {
            "advisory_ok": advisory_ok,
            "probability_ok": probability_ok,
            "reasons_ok": reasons_ok,
        },
    }


def cases() -> list[dict[str, Any]]:
    stale_evidence = [row("mem_current", score=0.64), row("mem_old", score=0.57, claim_scope=0.55)]
    return [
        {
            "id": "default_incidental_stale_context_suppressed",
            "description": "Default config requires an explicit stale signal, so incidental stale context remains advisory-neutral.",
            "query": "What should Hermes cite in answers?",
            "evidence": stale_evidence,
            "expected_advisory": "uncertain_keep_symbolic",
            "expected_probability": 0.50,
            "required_reasons": ["stale_context_present_without_explicit_conflict"],
        },
        {
            "id": "config_allows_incidental_stale_context",
            "description": "A config override can intentionally promote incidental stale context into a positive advisory.",
            "query": "What should Hermes cite in answers?",
            "evidence": stale_evidence,
            "shadow_overrides": {"stale_conflict_requires_explicit_signal": False},
            "expected_advisory": "likely_helpful",
            "expected_probability": 0.82,
            "required_reasons": ["config_allows_incidental_stale_context"],
        },
        {
            "id": "config_sets_positive_probability",
            "description": "The positive stale-conflict probability is now controlled by config rather than hardcoded in shadow code.",
            "query": "What is the old project policy?",
            "evidence": stale_evidence,
            "shadow_overrides": {"stale_conflict_positive_probability": 0.66},
            "expected_advisory": "likely_helpful",
            "expected_probability": 0.66,
            "required_reasons": ["stale_conflict_present"],
        },
        {
            "id": "config_sets_neutral_probability",
            "description": "The neutral stale-conflict probability is configurable for suppressed/current-query cases.",
            "query": "What is the current project policy after the correction?",
            "evidence": stale_evidence,
            "shadow_overrides": {"stale_conflict_neutral_probability": 0.52},
            "expected_advisory": "uncertain_keep_symbolic",
            "expected_probability": 0.52,
            "required_reasons": ["current_query_suppresses_stale_advisory"],
        },
    ]


def build_report() -> dict[str, Any]:
    base_config = load_config(ROOT).get("adaptive_behavior") or {}
    rows = [run_case(case, base_config) for case in cases()]
    return {
        "schema": "adaptive_behavior_stale_conflict_config_regression/v1",
        "candidate": "stale_conflict_configurable_control_surface",
        "description": "Regression guard proving stale-conflict shadow behavior is config-controlled and report-only.",
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
        "# Adaptive Behavior Stale-Conflict Config Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate: `{report['candidate']}`",
        f"Cases: `{report['passed_count']}/{report['case_count']}`",
        "",
        "| case | expected | actual | probability | pass | reasons |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for item in report["cases"]:
        reasons = ", ".join(item.get("actual_reasons") or [])
        lines.append(
            f"| `{item['id']}` | `{item['expected_advisory']}` | `{item['actual_advisory']}` | "
            f"`{item['actual_probability']}` | `{item['passed']}` | {reasons} |"
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
