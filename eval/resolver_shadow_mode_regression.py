from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.answer_behavior_shadow import normalize_resolver_shadow_config, resolver_shadow_actions

OUT_JSON = ROOT.parent / "experiments" / "resolver_shadow_mode_regression_results.json"
OUT_MD = ROOT.parent / "experiments" / "resolver_shadow_mode_regression_report.md"


def row(memory_id: str, text: str, authority_state: str = "standalone") -> dict:
    return {
        "memory_id": memory_id,
        "text": text,
        "authority_state": authority_state,
        "score": 0.8,
        "claim_scope_score": 0.8,
    }


def selector_snapshot(**diagnostics) -> dict:
    return {
        "ok": True,
        "ogcf_meta_present": any(str(key).startswith("ogcf_") for key in diagnostics),
        "decision": {"policy": "periodic_baseline", "action": "PROTECT_PERIODIC"},
        "diagnostics": diagnostics,
    }


def has_action(case: dict, action: str) -> bool:
    return action in set(case.get("actions") or [])


def run_cases() -> list[dict]:
    supported = resolver_shadow_actions(
        query="What should Hermes cite?",
        answer="Relevant memory indicates: cite selected evidence ids.",
        evidence=[row("mem_supported", "Hermes should cite selected evidence ids.")],
        selector_snapshot=selector_snapshot(),
        config={"enabled": True},
    )
    bridge = resolver_shadow_actions(
        query="How does weather uncertainty connect to selector refresh clusters?",
        answer="Relevant memory indicates: weather uncertainty connects to selector refresh evidence.",
        evidence=[row("mem_bridge", "Weather uncertainty connects to selector refresh evidence.")],
        selector_snapshot=selector_snapshot(
            ogcf_bridge_overload_score=0.91,
            ogcf_effective_affected_memory_ratio=0.8,
            ogcf_intent="bridge_geometry_query",
        ),
        config={"enabled": True},
    )
    ordinary_bridge = resolver_shadow_actions(
        query="What is the calendar location named Bridge Room?",
        answer="Relevant memory indicates: Bridge Room is the meeting location.",
        evidence=[row("mem_calendar", "Bridge Room is the meeting location.")],
        selector_snapshot=selector_snapshot(
            ogcf_bridge_overload_score=0.91,
            ogcf_effective_affected_memory_ratio=0.8,
            ogcf_intent="ordinary_fact_lookup",
        ),
        config={"enabled": True},
    )
    missing = resolver_shadow_actions(
        query="What private launch code should Hermes use?",
        answer="I do not have enough memory evidence to answer that yet.",
        evidence=[],
        selector_snapshot=selector_snapshot(),
        config={"enabled": True},
    )
    stale = resolver_shadow_actions(
        query="What is the current evidence citation policy?",
        answer="Relevant memory indicates: current policy requires selected evidence ids.",
        evidence=[row("mem_current", "Current policy requires selected evidence ids.", "current")],
        stale_context=[row("mem_stale", "Old policy allowed broad answers.", "stale")],
        selector_snapshot=selector_snapshot(stale_current_conflict=0.4),
        conflict=True,
        config={"enabled": True},
    )
    high_threshold_bridge = resolver_shadow_actions(
        query="How does weather uncertainty connect to selector refresh clusters?",
        answer="Relevant memory indicates: weather uncertainty connects to selector refresh evidence.",
        evidence=[row("mem_bridge", "Weather uncertainty connects to selector refresh evidence.")],
        selector_snapshot=selector_snapshot(
            ogcf_bridge_overload_score=0.91,
            ogcf_effective_affected_memory_ratio=0.8,
            ogcf_intent="bridge_geometry_query",
        ),
        config={
            "enabled": True,
            "bridge_warning_score_threshold": 0.95,
            "bridge_warning_effective_ratio_threshold": 0.95,
        },
    )
    cases = [
        {
            "id": "supported_answer",
            "passed": has_action(supported, "require_evidence_backed_answer")
            and not has_action(supported, "emit_ogcf_bridge_warning")
            and supported["mutates_answer"] is False,
            "shadow": supported,
        },
        {
            "id": "bridge_warning_supported",
            "passed": has_action(bridge, "require_evidence_backed_answer")
            and has_action(bridge, "emit_ogcf_bridge_warning"),
            "shadow": bridge,
        },
        {
            "id": "ordinary_bridge_suppressed",
            "passed": has_action(ordinary_bridge, "require_evidence_backed_answer")
            and not has_action(ordinary_bridge, "emit_ogcf_bridge_warning"),
            "shadow": ordinary_bridge,
        },
        {
            "id": "missing_support_refusal",
            "passed": has_action(missing, "preserve_missing_support_refusal")
            and missing["annotations"][0]["answer_has_refusal_language"] is True,
            "shadow": missing,
        },
        {
            "id": "stale_conflict_disclosure",
            "passed": has_action(stale, "require_evidence_backed_answer")
            and has_action(stale, "disclose_stale_conflict"),
            "shadow": stale,
        },
        {
            "id": "configurable_bridge_threshold",
            "passed": has_action(high_threshold_bridge, "require_evidence_backed_answer")
            and not has_action(high_threshold_bridge, "emit_ogcf_bridge_warning"),
            "shadow": high_threshold_bridge,
        },
        {
            "id": "config_normalization",
            "passed": normalize_resolver_shadow_config({"refusal_markers": "no support,cannot answer"})["refusal_markers"]
            == ("no support", "cannot answer"),
            "shadow": {},
        },
    ]
    return cases


def write_report(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Mode Regression",
        "",
        "This regression validates report-only resolver-shadow actions. It does not modify resolver answers or runtime config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| case | pass | actions |",
        "| --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{', '.join(case.get('shadow', {}).get('actions') or [])}` |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    cases = run_cases()
    report = {
        "schema": "resolver_shadow_mode_regression/v1",
        "ok": all(case["passed"] for case in cases),
        "case_count": len(cases),
        "cases": cases,
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
    }
    write_report(report)
    print(json.dumps({"ok": report["ok"], "case_count": report["case_count"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
