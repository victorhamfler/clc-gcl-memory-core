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
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read answer behavior proposals {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Answer behavior proposals must be a JSON object: {path}")
    return loaded


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def text_blob(proposal: dict[str, Any]) -> str:
    parts = [
        proposal.get("id"),
        proposal.get("target_behavior"),
        proposal.get("proposal"),
        " ".join(str(item) for item in proposal.get("preconditions") or []),
        " ".join(str(item) for item in proposal.get("guard_requirements") or []),
    ]
    for example in proposal.get("examples") or []:
        if isinstance(example, dict):
            parts.append(example.get("query"))
            parts.append(example.get("answer_preview"))
    return normalize_text(" ".join(str(part or "") for part in parts))


def report_only(proposal: dict[str, Any]) -> bool:
    return (
        proposal.get("mutates_config") is False
        and proposal.get("mutates_runtime") is False
        and proposal.get("auto_promote") is False
        and normalize_text(proposal.get("status")) == "proposal_only"
    )


def evidence_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    value = proposal.get("evidence_summary")
    return value if isinstance(value, dict) else {}


def numeric(summary: dict[str, Any], key: str) -> float:
    try:
        return float(summary.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def check_supported_answer(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    summary = evidence_summary(proposal)
    support = numeric(proposal, "support")
    selected = numeric(summary, "selected_memory_count")
    text = text_blob(proposal)
    if selected < support:
        issues.append({"severity": "error", "reason": "supported_answer_without_selected_evidence"})
    if numeric(summary, "positive_count") <= 0:
        issues.append({"severity": "error", "reason": "supported_answer_without_positive_feedback"})
    if "cite" not in text and "evidence" not in text:
        issues.append({"severity": "error", "reason": "supported_answer_missing_citation_or_evidence_requirement"})
    if "stale" not in text and "conflict" not in text:
        issues.append({"severity": "warning", "reason": "supported_answer_missing_stale_conflict_disclosure_guard"})
    return issues


def check_bridge_warning(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    summary = evidence_summary(proposal)
    support = numeric(proposal, "support")
    selected = numeric(summary, "selected_memory_count")
    ogcf = numeric(summary, "ogcf_signal_count")
    text = text_blob(proposal)
    if ogcf < support:
        issues.append({"severity": "error", "reason": "bridge_warning_without_ogcf_for_all_support"})
    if selected < support:
        issues.append({"severity": "error", "reason": "bridge_warning_without_selected_evidence"})
    if "ordinary" not in text or "suppression" not in text:
        issues.append({"severity": "error", "reason": "bridge_warning_missing_ordinary_suppression_guard"})
    if "suppressible" not in text and "negative answer feedback" not in text:
        issues.append({"severity": "error", "reason": "bridge_warning_missing_feedback_suppression_guard"})
    if "ogcf" not in text:
        issues.append({"severity": "error", "reason": "bridge_warning_missing_ogcf_requirement"})
    return issues


def check_missing_support(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    summary = evidence_summary(proposal)
    text = text_blob(proposal)
    if numeric(summary, "selected_memory_count") != 0:
        issues.append({"severity": "error", "reason": "missing_support_has_selected_memory"})
    if numeric(summary, "positive_count") > 0:
        issues.append({"severity": "error", "reason": "missing_support_has_positive_feedback"})
    if numeric(summary, "negative_count") <= 0:
        issues.append({"severity": "error", "reason": "missing_support_without_negative_feedback"})
    if "refusal" not in text and "insufficient-support" not in text and "insufficient support" not in text:
        issues.append({"severity": "error", "reason": "missing_support_missing_refusal_language"})
    if "supported answer" not in text and "valid supported" not in text:
        issues.append({"severity": "error", "reason": "missing_support_missing_supported_answer_protection"})
    if "raw retrieval score" not in text and "weak raw" not in text:
        issues.append({"severity": "warning", "reason": "missing_support_missing_raw_candidate_guard"})
    return issues


def check_proposal(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    proposal_id = str(proposal.get("id") or "")
    target = normalize_text(proposal.get("target_behavior"))
    if not report_only(proposal):
        issues.append({"severity": "error", "reason": "proposal_not_report_only"})
    if not proposal.get("source_cluster_key"):
        issues.append({"severity": "error", "reason": "missing_source_cluster_key"})
    if not proposal.get("preconditions"):
        issues.append({"severity": "error", "reason": "missing_preconditions"})
    if not proposal.get("guard_requirements"):
        issues.append({"severity": "error", "reason": "missing_guard_requirements"})
    if target == "supported_answer_quality":
        issues.extend(check_supported_answer(proposal))
    elif target == "bridge_warning_disclosure":
        issues.extend(check_bridge_warning(proposal))
    elif target == "missing_support_refusal":
        issues.extend(check_missing_support(proposal))
    else:
        issues.append({"severity": "warning", "reason": "unknown_target_behavior"})
    return [{**issue, "proposal_id": proposal_id, "target_behavior": target} for issue in issues]


def build_report(proposals_path: Path) -> dict[str, Any]:
    artifact = read_json(proposals_path)
    if artifact.get("schema") != "answer_behavior_proposals/v1":
        return {
            "schema": "answer_behavior_proposal_guard/v1",
            "ok": False,
            "proposals_path": str(proposals_path),
            "error": f"Unsupported schema: {artifact.get('schema')}",
            "checks": {},
            "issues": [],
        }
    proposals = [item for item in artifact.get("proposals") or [] if isinstance(item, dict)]
    issues = [issue for proposal in proposals for issue in check_proposal(proposal)]
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    targets = {normalize_text(item.get("target_behavior")) for item in proposals}
    checks = {
        "schema_ok": artifact.get("schema") == "answer_behavior_proposals/v1",
        "source_proposals_passed": artifact.get("ok") is True,
        "all_proposals_report_only": all(report_only(item) for item in proposals),
        "has_supported_answer_proposal": "supported_answer_quality" in targets,
        "has_bridge_warning_proposal": "bridge_warning_disclosure" in targets,
        "has_missing_support_proposal": "missing_support_refusal" in targets,
        "supported_answer_guarded": not any(
            issue.get("target_behavior") == "supported_answer_quality" and issue.get("severity") == "error"
            for issue in issues
        ),
        "bridge_warning_guarded": not any(
            issue.get("target_behavior") == "bridge_warning_disclosure" and issue.get("severity") == "error"
            for issue in issues
        ),
        "missing_support_guarded": not any(
            issue.get("target_behavior") == "missing_support_refusal" and issue.get("severity") == "error"
            for issue in issues
        ),
        "no_error_issues": not errors,
    }
    return {
        "schema": "answer_behavior_proposal_guard/v1",
        "description": "Report-only safety guard for answer behavior proposals before resolver implementation.",
        "ok": all(checks.values()),
        "proposals_path": str(proposals_path),
        "proposal_count": len(proposals),
        "checks": checks,
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
        "guarded_proposals": [
            {
                "id": proposal.get("id"),
                "target_behavior": proposal.get("target_behavior"),
                "source_cluster_key": proposal.get("source_cluster_key"),
                "status": "guarded_ready"
                if not any(issue.get("proposal_id") == proposal.get("id") and issue.get("severity") == "error" for issue in issues)
                else "blocked",
            }
            for proposal in proposals
        ],
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Behavior Proposal Guard",
        "",
        "This guard is advisory only. It does not change resolver behavior, selector policy, runtime config, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Proposals: `{report.get('proposal_count', 0)}`",
        f"Issues: `{report.get('issue_count', 0)}`",
        f"Errors: `{report.get('error_count', 0)}`",
        f"Warnings: `{report.get('warning_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Guarded Proposals", "", "| id | target | status |", "| --- | --- | --- |"])
    for proposal in report.get("guarded_proposals") or []:
        lines.append(f"| `{proposal.get('id')}` | `{proposal.get('target_behavior')}` | `{proposal.get('status')}` |")
    lines.extend(["", "## Issues", ""])
    if not report.get("issues"):
        lines.append("- None")
    for issue in report.get("issues") or []:
        lines.append(
            f"- `{issue.get('severity')}` `{issue.get('proposal_id')}` "
            f"`{issue.get('target_behavior')}`: `{issue.get('reason')}`"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard report-only answer behavior proposals before implementation.")
    parser.add_argument("--proposals", default=str(REPO_ROOT / "experiments" / "answer_behavior_proposals_results.json"))
    parser.add_argument("--out-json", default=str(REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_results.json"))
    parser.add_argument("--out-md", default=str(REPO_ROOT / "experiments" / "answer_behavior_proposal_guard_report.md"))
    args = parser.parse_args()

    report = build_report(Path(args.proposals))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "proposal_count": report.get("proposal_count"),
                "issue_count": report.get("issue_count"),
                "error_count": report.get("error_count"),
                "warning_count": report.get("warning_count"),
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
