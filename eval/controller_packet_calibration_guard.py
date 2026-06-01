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
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_report.md"

PROMOTION_KINDS = {"resolver_residual_benefit_candidate", "positive_behavior_candidate"}
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
        if review_items and not allow_review_items and str(proposal.get("kind") or "") in PROMOTION_KINDS:
            is_ready = False
            reasons = [*reasons, "review_items_present"]
        row = {
            "id": proposal.get("id"),
            "kind": proposal.get("kind"),
            "support": proposal.get("support"),
            "source_log_count": proposal.get("source_log_count"),
            "ready": is_ready,
            "blocked_reasons": reasons,
            "next_test": proposal.get("next_test"),
        }
        guarded.append(row)
        if is_ready:
            ready.append(row)
        else:
            blocked.append(row)
    return {
        "schema": "controller_packet_calibration_guard/v1",
        "description": "Guard for report-only calibration proposals. This does not promote config.",
        "ok": bool(proposals) and not ready,
        "source_proposals": str(proposals_path),
        "proposal_count": len(proposals),
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "review_item_count": len(review_items),
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
        "",
        "| id | kind | ready | blocked reasons | next test |",
        "| --- | --- | --- | --- | --- |",
    ]
    for proposal in report["guarded_proposals"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | {} |".format(
                proposal.get("id"),
                proposal.get("kind"),
                proposal.get("ready"),
                ", ".join(proposal.get("blocked_reasons") or []),
                str(proposal.get("next_test") or "").replace("|", "\\|"),
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
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
