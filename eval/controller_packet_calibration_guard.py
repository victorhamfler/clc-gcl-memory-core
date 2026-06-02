from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_PROPOSALS = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_report.md"

PROMOTION_KINDS = {
    "resolver_residual_benefit_candidate",
    "positive_behavior_candidate",
    "ogcf_bridge_behavior_candidate",
}
BLOCKING_KINDS = {
    "missing_support_review",
    "stale_answer_review",
    "negative_feedback_review",
    "mixed_feedback_holdout",
    "bridge_metadata_gap_review",
}


def read_proposals(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read calibration proposals {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Calibration proposals must be a JSON object: {path}")
    if value.get("schema") != "controller_packet_calibration_proposals/v1":
        raise ValueError(f"Unsupported calibration proposals schema: {value.get('schema')}")
    return value


def proposal_family(proposal: dict[str, Any]) -> str:
    kind = str(proposal.get("kind") or "")
    labels = proposal.get("feedback_labels") if isinstance(proposal.get("feedback_labels"), dict) else {}
    label_text = " ".join(str(label) for label in labels)
    ogcf = proposal.get("ogcf_intents") if isinstance(proposal.get("ogcf_intents"), dict) else {}
    ogcf_text = " ".join(str(value) for value in ogcf)
    if "ogcf" in kind or "bridge" in kind or "bridge" in label_text or "ogcf" in label_text or "bridge" in ogcf_text:
        return "ogcf_bridge"
    if "missing" in kind or "missing" in label_text or "wrong_domain" in label_text:
        return "missing_support"
    if "stale" in kind or "stale" in label_text or "conflict" in label_text:
        return "stale_conflict"
    if "citation" in kind or "citation" in label_text:
        return "citation"
    return "general_answer"


def related_review_items(proposal: dict[str, Any], review_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    family = proposal_family(proposal)
    return [item for item in review_items if proposal_family(item) == family]


def readiness_tier(proposal: dict[str, Any], *, evidence_ready: bool, ready: bool, reasons: list[str]) -> str:
    kind = str(proposal.get("kind") or "")
    if ready:
        return "guard_ready"
    if "bridge_label_without_ogcf" in reasons:
        return "metadata_gap"
    if kind not in PROMOTION_KINDS:
        return "review_evidence"
    if evidence_ready and "related_review_items_present" in reasons:
        return "evidence_ready_blocked_by_related_review"
    if evidence_ready and "review_items_present" in reasons:
        return "evidence_ready_blocked_by_global_review"
    if "insufficient_source_logs" in reasons or "insufficient_support" in reasons:
        return "collect_more"
    return "blocked"


def recommended_action(tier: str, proposal: dict[str, Any], related_reviews: list[dict[str, Any]]) -> str:
    if tier == "guard_ready":
        return "prepare_report_only_promotion_candidate_for_manual_review"
    if tier == "evidence_ready_blocked_by_related_review":
        families = ", ".join(str(item.get("id")) for item in related_reviews) or "related_review_items"
        return f"resolve_or_model_related_review_items_before_promotion: {families}"
    if tier == "evidence_ready_blocked_by_global_review":
        return "separate_unrelated_review_families_before_considering_promotion"
    if tier == "collect_more":
        return "collect_more_independent_logs_or_supporting_packets"
    if tier == "metadata_gap":
        return "rerun_with_explicit_metadata_before_calibration"
    if tier == "review_evidence":
        return "keep_as_guard_review_evidence"
    return "manual_review_required"


def proposal_ready(
    proposal: dict[str, Any],
    *,
    min_support: int,
    min_source_logs: int,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    kind = str(proposal.get("kind") or "")
    if kind not in PROMOTION_KINDS:
        reasons.append("not_a_promotion_kind")
    if int(proposal.get("support") or 0) < min_support:
        reasons.append("insufficient_support")
    if int(proposal.get("source_log_count") or 0) < min_source_logs:
        reasons.append("insufficient_source_logs")
    if proposal.get("report_only") is not True:
        reasons.append("not_report_only")
    if proposal.get("bridge_label_without_ogcf"):
        reasons.append("bridge_label_without_ogcf")
    if proposal.get("mutates_runtime") is not False or proposal.get("mutates_config") is not False:
        reasons.append("mutation_flag_present")
    labels = proposal.get("feedback_labels") if isinstance(proposal.get("feedback_labels"), dict) else {}
    if any(any(term in str(label) for term in ("wrong", "bad", "stale", "missing", "overconfident", "noise", "irrelevant")) for label in labels):
        reasons.append("negative_feedback_label_present")
    return not reasons, reasons


def build_report(
    proposals_path: Path,
    *,
    min_support: int = 4,
    min_source_logs: int = 2,
    allow_review_items: bool = False,
) -> dict[str, Any]:
    artifact = read_proposals(proposals_path)
    proposals = [item for item in artifact.get("proposals") or [] if isinstance(item, dict)]
    guarded = []
    ready = []
    blocked = []
    review_items = [item for item in proposals if str(item.get("kind") or "") in BLOCKING_KINDS]
    for proposal in proposals:
        is_ready, reasons = proposal_ready(
            proposal,
            min_support=max(1, int(min_support)),
            min_source_logs=max(1, int(min_source_logs)),
        )
        related_reviews = related_review_items(proposal, review_items) if str(proposal.get("kind") or "") in PROMOTION_KINDS else []
        evidence_ready = is_ready
        if review_items and not allow_review_items and str(proposal.get("kind") or "") in PROMOTION_KINDS:
            is_ready = False
            reasons = [*reasons, "review_items_present"]
            if related_reviews:
                reasons = [*reasons, "related_review_items_present"]
        tier = readiness_tier(proposal, evidence_ready=evidence_ready, ready=is_ready, reasons=reasons)
        row = {
            "id": proposal.get("id"),
            "kind": proposal.get("kind"),
            "family": proposal_family(proposal),
            "support": proposal.get("support"),
            "source_log_count": proposal.get("source_log_count"),
            "evidence_ready": evidence_ready,
            "ready": is_ready,
            "readiness_tier": tier,
            "blocked_reasons": reasons,
            "related_review_item_ids": [item.get("id") for item in related_reviews],
            "recommended_action": recommended_action(tier, proposal, related_reviews),
            "next_test": proposal.get("next_test"),
        }
        guarded.append(row)
        if is_ready:
            ready.append(row)
        else:
            blocked.append(row)
    tier_counts = Counter(str(item.get("readiness_tier") or "unknown") for item in guarded)
    evidence_ready_blocked = [
        item
        for item in guarded
        if str(item.get("readiness_tier") or "").startswith("evidence_ready_blocked")
    ]
    return {
        "schema": "controller_packet_calibration_guard/v1",
        "description": "Guard for report-only calibration proposals. This does not promote config.",
        "ok": bool(proposals) and not ready,
        "source_proposals": str(proposals_path),
        "proposal_count": len(proposals),
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "review_item_count": len(review_items),
        "evidence_ready_blocked_count": len(evidence_ready_blocked),
        "readiness_tier_counts": dict(sorted(tier_counts.items())),
        "next_actions": [
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "family": item.get("family"),
                "readiness_tier": item.get("readiness_tier"),
                "recommended_action": item.get("recommended_action"),
                "related_review_item_ids": item.get("related_review_item_ids"),
            }
            for item in guarded
            if item.get("readiness_tier") in {"evidence_ready_blocked_by_related_review", "guard_ready", "metadata_gap"}
        ],
        "thresholds": {
            "min_support": max(1, int(min_support)),
            "min_source_logs": max(1, int(min_source_logs)),
            "allow_review_items": bool(allow_review_items),
        },
        "guarded_proposals": guarded,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Guard",
        "",
        "This guard is conservative: by default it passes only when proposals exist but none are ready for promotion yet.",
        "",
        f"Passed: **{report['ok']}**",
        f"Proposals: `{report['proposal_count']}`",
        f"Ready: `{report['ready_count']}`",
        f"Blocked: `{report['blocked_count']}`",
        f"Review items: `{report['review_item_count']}`",
        f"Evidence-ready but blocked: `{report['evidence_ready_blocked_count']}`",
        "",
        "## Readiness Tiers",
        "",
        "```json",
        json.dumps(report["readiness_tier_counts"], indent=2),
        "```",
        "",
        "## Next Actions",
        "",
        "```json",
        json.dumps(report["next_actions"], indent=2),
        "```",
        "",
        "| id | kind | family | tier | evidence ready | ready | blocked reasons | related reviews | action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for proposal in report["guarded_proposals"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | {} |".format(
                proposal.get("id"),
                proposal.get("kind"),
                proposal.get("family"),
                proposal.get("readiness_tier"),
                proposal.get("evidence_ready"),
                proposal.get("ready"),
                ", ".join(proposal.get("blocked_reasons") or []),
                ", ".join(str(item) for item in proposal.get("related_review_item_ids") or []),
                str(proposal.get("recommended_action") or "").replace("|", "\\|"),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard controller packet calibration proposals before promotion.")
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--min-support", type=int, default=4)
    parser.add_argument("--min-source-logs", type=int, default=2)
    parser.add_argument("--allow-review-items", action="store_true")
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(
        args.proposals,
        min_support=args.min_support,
        min_source_logs=args.min_source_logs,
        allow_review_items=args.allow_review_items,
    )
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "proposal_count": report["proposal_count"],
                "ready_count": report["ready_count"],
                "blocked_count": report["blocked_count"],
                "evidence_ready_blocked_count": report["evidence_ready_blocked_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
