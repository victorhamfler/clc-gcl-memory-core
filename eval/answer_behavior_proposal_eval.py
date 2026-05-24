from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_BANK = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_results.json"
DEFAULT_GUARD = REPO_ROOT / "experiments" / "answer_feedback_bank_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "answer_behavior_proposals_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_behavior_proposals_report.md"


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


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def index_clusters(bank: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_text(cluster.get("key")): cluster
        for cluster in bank.get("clusters") or []
        if isinstance(cluster, dict) and normalize_text(cluster.get("key"))
    }


def proposal_for_cluster(cluster: dict[str, Any]) -> dict[str, Any] | None:
    key = normalize_text(cluster.get("key"))
    family = normalize_text(cluster.get("family"))
    readiness = normalize_text(cluster.get("readiness"))
    if not readiness.startswith("ready"):
        return None

    base = {
        "source_cluster_key": cluster.get("key"),
        "family": cluster.get("family"),
        "support": cluster.get("support"),
        "distinct_source_logs": cluster.get("distinct_source_logs"),
        "distinct_queries": cluster.get("distinct_queries"),
        "mean_rating": cluster.get("mean_rating"),
        "evidence_summary": {
            "positive_count": cluster.get("positive_count"),
            "negative_count": cluster.get("negative_count"),
            "ogcf_signal_count": cluster.get("ogcf_signal_count"),
            "selected_memory_count": cluster.get("selected_memory_count"),
        },
        "mutates_config": False,
        "mutates_runtime": False,
        "auto_promote": False,
        "status": "proposal_only",
        "examples": cluster.get("examples") or [],
    }

    if family == "answer_quality" and "answer_correct" in key:
        return {
            **base,
            "id": "proposal_require_evidence_backed_supported_answers",
            "target_behavior": "supported_answer_quality",
            "proposal": "Prefer answer forms that cite selected memory evidence and mark weak support when evidence is limited.",
            "preconditions": [
                "selected_memory_count >= support",
                "positive answer-quality feedback is repeated across runs",
                "no stale/current conflict is hidden by the selected evidence",
            ],
            "guard_requirements": [
                "supported_answer_ready_requires_evidence",
                "answer-quality regression must still pass",
                "no resolver config mutation from this artifact",
            ],
            "next_eval": "answer_behavior_proposal_guard.py",
        }
    if family == "bridge_warning_quality" and "answer_bridge_warning_useful" in key:
        return {
            **base,
            "id": "proposal_emit_ogcf_bridge_warning_when_supported",
            "target_behavior": "bridge_warning_disclosure",
            "proposal": "When OGCF bridge diagnostics are present and retrieved evidence supports a cross-domain bridge answer, consider emitting a concise bridge-risk warning.",
            "preconditions": [
                "ogcf_signal_count == support",
                "selected_memory_count >= support",
                "query or evidence has bridge/geometry intent",
                "ordinary fact lookup suppression still passes",
            ],
            "guard_requirements": [
                "bridge_ready_requires_ogcf",
                "ogcf_intent_gate_regression must pass",
                "canonical_ogcf_policy_distribution_regression must pass",
                "bridge warning must be suppressible by negative answer feedback",
            ],
            "next_eval": "answer_behavior_proposal_guard.py",
        }
    if family == "missing_support_refusal" and "answer_missing_support" in key:
        return {
            **base,
            "id": "proposal_preserve_missing_support_refusal",
            "target_behavior": "missing_support_refusal",
            "proposal": "When no selected evidence supports a query, preserve refusal or insufficient-support language instead of composing from weak raw candidates.",
            "preconditions": [
                "selected_memory_count == 0",
                "negative missing-support feedback is repeated across runs",
                "raw retrieval score alone is not treated as answer support",
            ],
            "guard_requirements": [
                "missing_support_refusal_guarded",
                "supported answer cases must not be downgraded to refusal",
                "no hallucinated answer from weak raw_results",
            ],
            "next_eval": "answer_behavior_proposal_guard.py",
        }
    return {
        **base,
        "id": f"proposal_hold_{key.replace(':', '_').replace(' ', '_')}",
        "target_behavior": "unknown",
        "proposal": "Hold this ready cluster for manual review because no behavior mapping exists yet.",
        "preconditions": [],
        "guard_requirements": ["manual_review_required"],
        "next_eval": "manual_review",
    }


def guard_ready_keys(guard: dict[str, Any]) -> set[str]:
    return {normalize_text(item.get("key")) for item in guard.get("ready_clusters") or [] if isinstance(item, dict)}


def build_report(bank_path: Path, guard_path: Path) -> dict[str, Any]:
    bank = read_json(bank_path)
    guard = read_json(guard_path)
    if bank.get("schema") != "answer_feedback_memory_bank/v1":
        return {
            "schema": "answer_behavior_proposals/v1",
            "ok": False,
            "error": f"Unsupported bank schema: {bank.get('schema')}",
            "proposals": [],
        }
    if guard.get("schema") != "answer_feedback_bank_guard/v1":
        return {
            "schema": "answer_behavior_proposals/v1",
            "ok": False,
            "error": f"Unsupported guard schema: {guard.get('schema')}",
            "proposals": [],
        }
    clusters = index_clusters(bank)
    ready_keys = guard_ready_keys(guard)
    proposals = []
    held = []
    for key in sorted(ready_keys):
        cluster = clusters.get(key)
        if not cluster:
            held.append({"key": key, "reason": "guard_ready_cluster_missing_from_bank"})
            continue
        proposal = proposal_for_cluster(cluster)
        if proposal:
            proposals.append(proposal)
        else:
            held.append({"key": key, "reason": "no_proposal_mapping"})

    checks = {
        "bank_schema_ok": bank.get("schema") == "answer_feedback_memory_bank/v1",
        "guard_schema_ok": guard.get("schema") == "answer_feedback_bank_guard/v1",
        "guard_passed": guard.get("ok") is True,
        "has_proposals": bool(proposals),
        "all_proposals_report_only": all(
            not item.get("mutates_config") and not item.get("mutates_runtime") and not item.get("auto_promote")
            for item in proposals
        ),
        "missing_support_proposal_present": any(item.get("target_behavior") == "missing_support_refusal" for item in proposals),
        "bridge_warning_proposal_present": any(item.get("target_behavior") == "bridge_warning_disclosure" for item in proposals),
        "supported_answer_proposal_present": any(item.get("target_behavior") == "supported_answer_quality" for item in proposals),
        "no_missing_guard_clusters": not any(item.get("reason") == "guard_ready_cluster_missing_from_bank" for item in held),
    }
    return {
        "schema": "answer_behavior_proposals/v1",
        "description": "Report-only answer behavior proposals derived from guarded answer-feedback memory-bank clusters.",
        "ok": all(checks.values()),
        "bank_path": str(bank_path),
        "guard_path": str(guard_path),
        "checks": checks,
        "proposal_count": len(proposals),
        "held_count": len(held),
        "mutates_config": False,
        "mutates_runtime": False,
        "auto_promote": False,
        "proposals": proposals,
        "held": held,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Behavior Proposals",
        "",
        "This artifact is advisory only. It does not change resolver behavior, selector policy, runtime config, or learned artifacts.",
        "",
        f"Passed: **{report['ok']}**",
        f"Bank: `{report.get('bank_path')}`",
        f"Guard: `{report.get('guard_path')}`",
        f"Proposals: `{report.get('proposal_count', 0)}`",
        f"Held: `{report.get('held_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Proposals", "", "| id | target | cluster | proposal |", "| --- | --- | --- | --- |"])
    for proposal in report.get("proposals") or []:
        lines.append(
            f"| `{proposal.get('id')}` | `{proposal.get('target_behavior')}` | "
            f"`{proposal.get('source_cluster_key')}` | {clean_cell(proposal.get('proposal'))} |"
        )
    lines.extend(["", "## Held", ""])
    if not report.get("held"):
        lines.append("- None")
    for item in report.get("held") or []:
        lines.append(f"- `{item.get('key')}`: `{item.get('reason')}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create report-only answer behavior proposals from a guarded memory bank.")
    parser.add_argument("--bank", default=str(DEFAULT_BANK))
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.bank), Path(args.guard))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "proposal_count": report.get("proposal_count"),
                "held_count": report.get("held_count"),
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
