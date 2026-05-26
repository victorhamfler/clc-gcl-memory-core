from __future__ import annotations

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


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_stale_conflict_candidate_promotion_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_stale_conflict_candidate_promotion_report.md"


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


def decision(payload: dict[str, Any], family: str) -> dict[str, Any]:
    for row in payload.get("decisions") or []:
        if isinstance(row, dict) and row.get("behavior_family") == family:
            return row
    return {}


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


def run_case(case: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    selected = case.get("evidence") or [row("mem_current")]
    context = Context(
        diagnostics=case.get("diagnostics") or {},
        retrieval_context=case.get("retrieval_context") or selected,
        ogcf_meta_present=False,
    )
    shadow = adaptive_behavior_shadow_advisories(
        query=case["query"],
        answer=case.get("answer") or "Answer grounded in selected memory evidence.",
        evidence=selected,
        stale_context=case.get("stale_context") or [],
        adaptive_context=context,
        resolver_shadow=case.get("resolver_shadow"),
        config=config,
    )
    stale = decision(shadow, "stale_conflict")
    return {
        "id": case["id"],
        "description": case["description"],
        "query": case["query"],
        "expected_advisory": case["expected_advisory"],
        "actual_advisory": stale.get("advisory"),
        "shadow_probability": stale.get("shadow_probability"),
        "reasons": stale.get("reasons") or [],
        "passed": stale.get("advisory") == case["expected_advisory"],
    }


def cases() -> list[dict[str, Any]]:
    stale_evidence = [row("mem_current", score=0.64), row("mem_old", score=0.57, claim_scope=0.55)]
    stale_context = [row("mem_old", score=0.51, claim_scope=0.5)]
    return [
        {
            "id": "incidental_stale_context_suppressed",
            "description": "Selected evidence has incidental stale context, but query is not asking for stale/history.",
            "query": "What should Hermes cite in answers?",
            "evidence": stale_evidence,
            "stale_context": stale_context,
            "diagnostics": {},
            "expected_advisory": "uncertain_keep_symbolic",
        },
        {
            "id": "explicit_old_query_triggers",
            "description": "Old/history-shaped query with stale context should trigger stale-conflict advisory.",
            "query": "What is the old project policy?",
            "evidence": stale_evidence,
            "stale_context": stale_context,
            "diagnostics": {},
            "expected_advisory": "likely_helpful",
        },
        {
            "id": "previous_query_triggers",
            "description": "Previous-version query should trigger stale-conflict advisory.",
            "query": "What was the previous backend port?",
            "evidence": stale_evidence,
            "stale_context": stale_context,
            "diagnostics": {},
            "expected_advisory": "likely_helpful",
        },
        {
            "id": "current_query_suppresses",
            "description": "Current/corrected query should suppress stale over-fire even with stale context.",
            "query": "What is the current project policy after the correction?",
            "evidence": stale_evidence,
            "stale_context": stale_context,
            "diagnostics": {},
            "expected_advisory": "uncertain_keep_symbolic",
        },
        {
            "id": "diagnostic_conflict_triggers",
            "description": "Explicit stale_current_conflict diagnostic should trigger even without stale wording.",
            "query": "Which resolver bridge threshold policy should be used now?",
            "evidence": stale_evidence,
            "stale_context": [],
            "diagnostics": {"stale_current_conflict": 1.0},
            "expected_advisory": "likely_helpful",
        },
        {
            "id": "resolver_disclosure_alone_suppressed_without_explicit_signal",
            "description": "Resolver stale action alone is not enough without explicit query/diagnostic conflict.",
            "query": "What should Hermes cite in answers?",
            "evidence": stale_evidence,
            "stale_context": stale_context,
            "resolver_shadow": {"actions": ["disclose_stale_conflict"]},
            "diagnostics": {},
            "expected_advisory": "uncertain_keep_symbolic",
        },
    ]


def build_report() -> dict[str, Any]:
    config = load_config(ROOT).get("adaptive_behavior")
    rows = [run_case(case, config) for case in cases()]
    return {
        "schema": "adaptive_behavior_stale_conflict_candidate_promotion/v1",
        "candidate": "stale_conflict_explicit_signal_gate",
        "description": "Targeted promotion guard for recurrence-ready stale-conflict adaptive behavior candidate.",
        "ok": all(row["passed"] for row in rows),
        "case_count": len(rows),
        "passed_count": sum(1 for row in rows if row["passed"]),
        "cases": rows,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Stale-Conflict Candidate Promotion Guard",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate: `{report['candidate']}`",
        f"Cases: `{report['passed_count']}/{report['case_count']}`",
        "",
        "| case | expected | actual | probability | pass | reasons |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for item in report["cases"]:
        reasons = ", ".join(item.get("reasons") or [])
        lines.append(
            f"| `{item['id']}` | `{item['expected_advisory']}` | `{item['actual_advisory']}` | "
            f"`{item['shadow_probability']}` | `{item['passed']}` | {reasons} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "passed": report["passed_count"], "total": report["case_count"], "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
