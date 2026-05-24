from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_PROPOSALS = REPO_ROOT / "experiments" / "answer_behavior_proposals_results.json"
DEFAULT_GUARD = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_shadow_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_shadow_eval_report.md"


CASES = [
    {
        "id": "supported_answer_with_evidence",
        "query": "What should Hermes cite in answers?",
        "selected_memory_ids": ["mem_supported"],
        "raw_result_count": 2,
        "ogcf_meta_present": False,
        "ordinary_fact_lookup": False,
        "stale_conflict": False,
        "expected_actions": ["require_evidence_backed_answer"],
        "forbidden_actions": ["preserve_missing_support_refusal", "emit_ogcf_bridge_warning"],
    },
    {
        "id": "bridge_warning_supported",
        "query": "How can weather uncertainty interact with selector refresh evidence across clusters?",
        "selected_memory_ids": ["mem_bridge"],
        "raw_result_count": 3,
        "ogcf_meta_present": True,
        "ogcf_diagnostics": {
            "ogcf_bridge_overload_score": 0.94,
            "ogcf_effective_affected_memory_ratio": 1.0,
            "ogcf_intent": "bridge_geometry_query",
        },
        "ordinary_fact_lookup": False,
        "stale_conflict": False,
        "expected_actions": ["require_evidence_backed_answer", "emit_ogcf_bridge_warning"],
        "forbidden_actions": ["preserve_missing_support_refusal"],
    },
    {
        "id": "ordinary_fact_with_bridge_word",
        "query": "What is the calendar location named Bridge Room?",
        "selected_memory_ids": ["mem_calendar"],
        "raw_result_count": 2,
        "ogcf_meta_present": True,
        "ogcf_diagnostics": {
            "ogcf_bridge_overload_score": 0.2,
            "ogcf_effective_affected_memory_ratio": 0.0,
            "ogcf_intent": "ordinary_fact_lookup",
        },
        "ordinary_fact_lookup": True,
        "stale_conflict": False,
        "expected_actions": ["require_evidence_backed_answer"],
        "forbidden_actions": ["emit_ogcf_bridge_warning", "preserve_missing_support_refusal"],
    },
    {
        "id": "unsupported_private_code",
        "query": "What private launch code should Hermes use?",
        "selected_memory_ids": [],
        "raw_result_count": 3,
        "ogcf_meta_present": False,
        "ordinary_fact_lookup": False,
        "stale_conflict": False,
        "expected_actions": ["preserve_missing_support_refusal"],
        "forbidden_actions": ["require_evidence_backed_answer", "emit_ogcf_bridge_warning"],
    },
    {
        "id": "stale_conflict_supported",
        "query": "What is the current project policy after the correction?",
        "selected_memory_ids": ["mem_current_policy"],
        "raw_result_count": 4,
        "ogcf_meta_present": False,
        "ordinary_fact_lookup": False,
        "stale_conflict": True,
        "expected_actions": ["require_evidence_backed_answer", "disclose_stale_conflict"],
        "forbidden_actions": ["preserve_missing_support_refusal", "emit_ogcf_bridge_warning"],
    },
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return loaded


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def guarded_targets(guard: dict[str, Any]) -> set[str]:
    return {
        normalize_text(item.get("target_behavior"))
        for item in guard.get("guarded_proposals") or []
        if isinstance(item, dict) and normalize_text(item.get("status")) == "guarded_ready"
    }


def proposal_targets(proposals: dict[str, Any]) -> set[str]:
    return {
        normalize_text(item.get("target_behavior"))
        for item in proposals.get("proposals") or []
        if isinstance(item, dict)
    }


def simulate_case(case: dict[str, Any], available_targets: set[str]) -> dict[str, Any]:
    actions: list[str] = []
    reasons: list[str] = []
    selected_count = len(case.get("selected_memory_ids") or [])
    ogcf = case.get("ogcf_diagnostics") if isinstance(case.get("ogcf_diagnostics"), dict) else {}

    if "supported_answer_quality" in available_targets and selected_count > 0:
        actions.append("require_evidence_backed_answer")
        reasons.append("selected_evidence_present")
    if case.get("stale_conflict"):
        actions.append("disclose_stale_conflict")
        reasons.append("stale_conflict_present")
    if "bridge_warning_disclosure" in available_targets:
        ogcf_score = float(ogcf.get("ogcf_bridge_overload_score") or 0.0)
        ogcf_effective = float(ogcf.get("ogcf_effective_affected_memory_ratio") or 0.0)
        ordinary = bool(case.get("ordinary_fact_lookup")) or normalize_text(ogcf.get("ogcf_intent")) == "ordinary_fact_lookup"
        if selected_count > 0 and case.get("ogcf_meta_present") and not ordinary and (ogcf_score >= 0.7 or ogcf_effective >= 0.5):
            actions.append("emit_ogcf_bridge_warning")
            reasons.append("ogcf_bridge_pressure_with_selected_evidence")
    if "missing_support_refusal" in available_targets and selected_count == 0:
        actions.append("preserve_missing_support_refusal")
        reasons.append("no_selected_evidence")

    expected = set(case.get("expected_actions") or [])
    forbidden = set(case.get("forbidden_actions") or [])
    actual = set(actions)
    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "actions": actions,
        "reasons": reasons,
        "expected_actions": sorted(expected),
        "forbidden_actions": sorted(forbidden),
        "missing_expected": sorted(expected - actual),
        "forbidden_hits": sorted(forbidden & actual),
        "passed": not (expected - actual) and not (forbidden & actual),
    }


def build_report(proposals_path: Path, guard_path: Path) -> dict[str, Any]:
    proposals = read_json(proposals_path)
    guard = read_json(guard_path)
    if proposals.get("schema") != "answer_behavior_proposals/v1":
        return {"schema": "answer_behavior_shadow_eval/v1", "ok": False, "error": "unsupported_proposals_schema"}
    if guard.get("schema") != "answer_behavior_proposal_guard/v1":
        return {"schema": "answer_behavior_shadow_eval/v1", "ok": False, "error": "unsupported_guard_schema"}
    targets = proposal_targets(proposals) & guarded_targets(guard)
    case_results = [simulate_case(case, targets) for case in CASES]
    checks = {
        "proposals_passed": proposals.get("ok") is True,
        "guard_passed": guard.get("ok") is True,
        "has_supported_answer_target": "supported_answer_quality" in targets,
        "has_bridge_warning_target": "bridge_warning_disclosure" in targets,
        "has_missing_support_target": "missing_support_refusal" in targets,
        "all_cases_pass": all(item["passed"] for item in case_results),
        "ordinary_bridge_word_suppressed": next(
            item for item in case_results if item["id"] == "ordinary_fact_with_bridge_word"
        )["passed"],
        "missing_support_refusal_preserved": next(
            item for item in case_results if item["id"] == "unsupported_private_code"
        )["passed"],
        "stale_conflict_disclosed": next(item for item in case_results if item["id"] == "stale_conflict_supported")[
            "passed"
        ],
    }
    return {
        "schema": "answer_behavior_shadow_eval/v1",
        "description": "Report-only shadow simulation of guarded answer behavior proposals over controlled cases.",
        "ok": all(checks.values()),
        "proposals_path": str(proposals_path),
        "guard_path": str(guard_path),
        "available_targets": sorted(targets),
        "checks": checks,
        "case_count": len(case_results),
        "passed_count": sum(1 for item in case_results if item["passed"]),
        "mutates_config": False,
        "mutates_runtime": False,
        "case_results": case_results,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Behavior Shadow Eval",
        "",
        "This shadow eval is advisory only. It does not modify resolver code, selector policy, runtime config, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report.get('case_count', 0)}`",
        f"Passed cases: `{report.get('passed_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Cases", "", "| case | pass | actions | missing | forbidden hits |", "| --- | --- | --- | --- | --- |"])
    for case in report.get("case_results") or []:
        lines.append(
            f"| `{case.get('id')}` | `{case.get('passed')}` | `{', '.join(case.get('actions') or [])}` | "
            f"`{', '.join(case.get('missing_expected') or [])}` | `{', '.join(case.get('forbidden_hits') or [])}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a report-only shadow eval for guarded answer behavior proposals.")
    parser.add_argument("--proposals", default=str(DEFAULT_PROPOSALS))
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.proposals), Path(args.guard))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "case_count": report.get("case_count"),
                "passed_count": report.get("passed_count"),
                "checks": report.get("checks"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
