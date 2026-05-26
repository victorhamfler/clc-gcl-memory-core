from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

DEFAULT_CALIBRATION = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_calibration_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_report.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def family_summary(calibration: dict[str, Any]) -> dict[str, Any]:
    replayed = calibration.get("replayed_current_runtime_logic")
    if not isinstance(replayed, dict):
        replayed = calibration.get("logged_runtime_shadow")
    summary = (replayed or {}).get("family_summary")
    return summary if isinstance(summary, dict) else {}


def mismatch_examples(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    replayed = calibration.get("replayed_current_runtime_logic")
    if not isinstance(replayed, dict):
        replayed = calibration.get("logged_runtime_shadow")
    rows = (replayed or {}).get("mismatch_examples")
    return [row for row in rows or [] if isinstance(row, dict)]


def evidence_counter(rows: list[dict[str, Any]], *, family: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        if row.get("behavior_family") != family:
            continue
        for reason in row.get("reasons") or []:
            counter[str(reason)] += 1
    return counter


def proposal(
    *,
    proposal_id: str,
    family: str,
    status: str,
    rationale: str,
    evidence: dict[str, Any],
    suggested_profile_delta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "behavior_family": family,
        "status": status,
        "rationale": rationale,
        "evidence": evidence,
        "suggested_profile_delta": suggested_profile_delta,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
        "requires_guard_before_promotion": True,
    }


def build_profile(calibration_path: Path) -> dict[str, Any]:
    calibration = read_json(calibration_path)
    summaries = family_summary(calibration)
    mismatches = mismatch_examples(calibration)
    proposals: list[dict[str, Any]] = []

    def rate(family: str) -> float:
        try:
            return float((summaries.get(family) or {}).get("match_rate") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    missing_mismatch = [row for row in mismatches if row.get("behavior_family") == "missing_support"]
    stale_mismatch = [row for row in mismatches if row.get("behavior_family") == "stale_conflict"]
    supported_mismatch = [row for row in mismatches if row.get("behavior_family") == "supported_evidence"]

    if rate("missing_support") < 0.90:
        reasons = evidence_counter(missing_mismatch, family="missing_support")
        proposals.append(
            proposal(
                proposal_id="missing_support_sensitive_lookup_boost",
                family="missing_support",
                status="candidate",
                rationale=(
                    "Missing-support advisories still under-fire on unsupported sensitive/private lookups, "
                    "especially when weak selected evidence is present."
                ),
                evidence={
                    "family_match_rate": rate("missing_support"),
                    "mismatch_count": len(missing_mismatch),
                    "top_mismatch_reasons": dict(reasons.most_common(5)),
                },
                suggested_profile_delta={
                    "shadow.sensitive_support_terms": "mine_or_extend_from_calibration",
                    "missing_support.selected_sensitive_probability_floor": 0.76,
                    "promotion_rule": "only promote if linked answer feedback confirms missing-support/refusal behavior",
                },
            )
        )

    if rate("stale_conflict") < 0.90:
        reasons = evidence_counter(stale_mismatch, family="stale_conflict")
        proposals.append(
            proposal(
                proposal_id="stale_conflict_explicit_signal_gate",
                family="stale_conflict",
                status="candidate",
                rationale=(
                    "Stale-conflict advisories should require explicit stale/current conflict pressure or stale-shaped "
                    "queries, instead of firing from incidental stale context alone."
                ),
                evidence={
                    "family_match_rate": rate("stale_conflict"),
                    "mismatch_count": len(stale_mismatch),
                    "top_mismatch_reasons": dict(reasons.most_common(5)),
                },
                suggested_profile_delta={
                    "shadow.stale_support_terms": "mine_or_extend_from_calibration",
                    "shadow.current_support_terms": "mine_or_extend_from_calibration",
                    "stale_conflict.requires_explicit_stale_signal": True,
                    "promotion_rule": "ordinary current-answer feedback must not receive likely_helpful stale advisories",
                },
            )
        )

    if rate("supported_evidence") < 0.90:
        reasons = evidence_counter(supported_mismatch, family="supported_evidence")
        proposals.append(
            proposal(
                proposal_id="supported_evidence_low_support_review",
                family="supported_evidence",
                status="hold",
                rationale=(
                    "Supported-evidence behavior improved substantially, but low retrieval-score positives remain. "
                    "Hold this for more real logs before relaxing the low-support cap."
                ),
                evidence={
                    "family_match_rate": rate("supported_evidence"),
                    "mismatch_count": len(supported_mismatch),
                    "top_mismatch_reasons": dict(reasons.most_common(5)),
                },
                suggested_profile_delta={
                    "supported_evidence.low_support_positive_handling": "collect_more_evidence",
                    "promotion_rule": "do not weaken sensitive/stale risk caps from one local rerun",
                },
            )
        )

    return {
        "schema": "adaptive_behavior_candidate_profile/v1",
        "description": "Report-only candidate profile distilled from adaptive behavior shadow calibration.",
        "source_calibration": str(calibration_path),
        "source_calibration_schema": calibration.get("schema"),
        "source_match_rate": (calibration.get("improvement") or {}).get("replayed_match_rate"),
        "family_summary": summaries,
        "proposal_count": len(proposals),
        "proposals": proposals,
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
        "requires_guard_before_promotion": True,
    }


def write_profile(profile: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Candidate Profile",
        "",
        f"Schema: `{profile['schema']}`",
        f"Source match rate: `{profile.get('source_match_rate')}`",
        f"Proposal count: `{profile['proposal_count']}`",
        f"Report only: `{profile['report_only']}`",
        "",
        "## Proposals",
        "",
        "| id | family | status | match rate | rationale |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in profile.get("proposals") or []:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        rationale = str(item.get("rationale") or "").replace("|", "\\|")
        lines.append(
            f"| `{item.get('id')}` | `{item.get('behavior_family')}` | `{item.get('status')}` | "
            f"`{evidence.get('family_match_rate')}` | {rationale} |"
        )
    lines.extend(["", "## Raw Profile", "", "```json", json.dumps(profile, indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build report-only adaptive behavior candidate profile from calibration.")
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    profile = build_profile(args.calibration)
    write_profile(profile, args.out_json, args.out_md)
    print(json.dumps({"ok": True, "proposal_count": profile["proposal_count"], "json": str(args.out_json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
