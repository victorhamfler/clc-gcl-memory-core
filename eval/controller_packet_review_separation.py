from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_PROPOSALS = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_results.json"
DEFAULT_GUARD = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_review_separation_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_review_separation_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return loaded


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def labels(proposal: dict[str, Any]) -> set[str]:
    raw = proposal.get("feedback_labels") if isinstance(proposal.get("feedback_labels"), dict) else {}
    return {str(label).strip().lower() for label in raw if str(label).strip()}


def intents(proposal: dict[str, Any]) -> set[str]:
    raw = proposal.get("ogcf_intents") if isinstance(proposal.get("ogcf_intents"), dict) else {}
    return {str(label).strip().lower() for label in raw if str(label).strip()}


def support(proposal: dict[str, Any]) -> int:
    try:
        return int(proposal.get("support") or 0)
    except (TypeError, ValueError):
        return 0


def source_logs(proposal: dict[str, Any]) -> int:
    try:
        return int(proposal.get("source_log_count") or 0)
    except (TypeError, ValueError):
        return 0


def guard_rows_by_id(guard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in guard.get("guarded_proposals") or []
        if isinstance(item, dict) and item.get("id")
    }


def proposal_by_id(proposals: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in proposals.get("proposals") or []
        if isinstance(item, dict) and item.get("id")
    }


def common_prefixes(values: set[str]) -> set[str]:
    tokens = set()
    for value in values:
        for token in value.replace("-", "_").split("_"):
            if token:
                tokens.add(token)
    return tokens


def separation_features(candidate: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    candidate_labels = labels(candidate)
    review_labels = labels(review)
    candidate_intents = intents(candidate)
    review_intents = intents(review)
    shared_labels = sorted(candidate_labels & review_labels)
    shared_intents = sorted(candidate_intents & review_intents)
    candidate_tokens = common_prefixes(candidate_labels | candidate_intents | {str(candidate.get("kind") or "")})
    review_tokens = common_prefixes(review_labels | review_intents | {str(review.get("kind") or "")})
    shared_tokens = sorted(candidate_tokens & review_tokens)
    return {
        "candidate_labels": sorted(candidate_labels),
        "review_labels": sorted(review_labels),
        "candidate_intents": sorted(candidate_intents),
        "review_intents": sorted(review_intents),
        "shared_labels": shared_labels,
        "shared_intents": shared_intents,
        "shared_tokens": shared_tokens,
        "candidate_only_labels": sorted(candidate_labels - review_labels),
        "review_only_labels": sorted(review_labels - candidate_labels),
        "candidate_only_intents": sorted(candidate_intents - review_intents),
        "review_only_intents": sorted(review_intents - candidate_intents),
        "support_delta": support(candidate) - support(review),
        "source_log_delta": source_logs(candidate) - source_logs(review),
    }


def recommended_action(candidate: dict[str, Any], review: dict[str, Any], features: dict[str, Any]) -> str:
    kind = str(candidate.get("kind") or "")
    review_labels = set(features["review_labels"])
    if kind == "ogcf_bridge_behavior_candidate" and "ogcf_false_positive" in review_labels:
        return "train_or_calibrate_bridge_intent_separator_before_promotion"
    if features["shared_intents"] and features["review_only_labels"]:
        return "build_holdout_for_same_intent_positive_vs_negative_labels"
    if features["review_only_intents"]:
        return "separate_candidate_and_review_by_intent_before_promotion"
    return "manual_review_of_related_negative_evidence"


def build_report(proposals_path: Path, guard_path: Path) -> dict[str, Any]:
    proposals_artifact = read_json(proposals_path)
    guard = read_json(guard_path)
    proposals = proposal_by_id(proposals_artifact)
    guard_rows = guard_rows_by_id(guard)
    analyses = []
    for guard_row in guard_rows.values():
        if guard_row.get("readiness_tier") != "evidence_ready_blocked_by_related_review":
            continue
        candidate = proposals.get(str(guard_row.get("id")))
        if not candidate:
            continue
        for review_id in guard_row.get("related_review_item_ids") or []:
            review = proposals.get(str(review_id))
            if not review:
                continue
            features = separation_features(candidate, review)
            analyses.append(
                {
                    "candidate_id": candidate.get("id"),
                    "candidate_kind": candidate.get("kind"),
                    "candidate_support": support(candidate),
                    "candidate_source_log_count": source_logs(candidate),
                    "review_id": review.get("id"),
                    "review_kind": review.get("kind"),
                    "review_support": support(review),
                    "review_source_log_count": source_logs(review),
                    "features": features,
                    "recommended_action": recommended_action(candidate, review, features),
                    "report_only": True,
                    "mutates_runtime": False,
                    "mutates_config": False,
                }
            )
    action_counts: dict[str, int] = {}
    for item in analyses:
        action = str(item.get("recommended_action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "schema": "controller_packet_review_separation/v1",
        "description": "Report-only analysis of evidence-ready calibration candidates blocked by related review evidence.",
        "ok": bool(analyses),
        "source_proposals": str(proposals_path),
        "source_guard": str(guard_path),
        "analysis_count": len(analyses),
        "action_counts": dict(sorted(action_counts.items())),
        "analyses": analyses,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Review Separation",
        "",
        "This report is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Analyses: `{report['analysis_count']}`",
        "",
        "## Action Counts",
        "",
        "```json",
        json.dumps(report["action_counts"], indent=2),
        "```",
        "",
        "| candidate | review | action | candidate-only labels | review-only labels | candidate intents | review intents |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["analyses"]:
        features = item["features"]
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                item["candidate_id"],
                item["review_id"],
                clean_cell(item["recommended_action"]),
                clean_cell(", ".join(features["candidate_only_labels"])),
                clean_cell(", ".join(features["review_only_labels"])),
                clean_cell(", ".join(features["candidate_intents"])),
                clean_cell(", ".join(features["review_intents"])),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze candidate-vs-related-review separation needs.")
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--guard", type=Path, default=DEFAULT_GUARD)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.proposals, args.guard)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "analysis_count": report["analysis_count"],
                "action_counts": report["action_counts"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
