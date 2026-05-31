from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy  # noqa: E402
from eval.adaptive_residual_shadow_term_candidate_miner import build_report as build_miner_report  # noqa: E402
from eval.adaptive_residual_shadow_multi_log_eval import discover_logs  # noqa: E402


DEFAULT_LOG_GLOB = "adaptive_residual_shadow_*_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_proposal_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_proposal_report.md"


def classify_term(term: str) -> str:
    low = term.lower()
    if any(marker in low for marker in ("deployment key", "credential", "secret", "token", "password")):
        return "sensitive_private"
    if any(marker in low for marker in ("changed live", "already natural", "result proves", "unsupported")):
        return "unsupported_proof"
    if any(marker in low for marker in ("cross-namespace", "profile preference", "profile lookup")):
        return "ordinary_namespace_profile"
    if any(marker in low for marker in ("previous", "old", "still valid")):
        return "stale_previous"
    return "review_required"


def build_proposal_from_miner(miner: dict[str, Any], *, before_config: str, after_config: str) -> dict[str, Any]:
    configured_terms = load_policy(ROOT).get("terms")
    configured_terms = configured_terms if isinstance(configured_terms, dict) else {}
    grouped: dict[str, list[str]] = {}
    already_configured: dict[str, list[str]] = {}
    review_required = []
    for row in miner.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        term = str(row.get("term") or "").strip()
        if not term:
            continue
        group = classify_term(term)
        if group == "review_required":
            review_required.append(row)
            continue
        existing = {str(item).strip().lower() for item in configured_terms.get(group, [])}
        if term.lower() in existing:
            already_configured.setdefault(group, [])
            if term not in already_configured[group]:
                already_configured[group].append(term)
            continue
        grouped.setdefault(group, [])
        if term not in grouped[group]:
            grouped[group].append(term)
    checks = {
        "miner_ok_or_review_candidates": bool(miner.get("ok")) or bool(miner.get("candidates")),
        "report_only": True,
        "config_unchanged": before_config == after_config,
        "no_runtime_mutation": True,
        "review_required_for_ambiguous_terms": bool(review_required) or not miner.get("candidates"),
        "deduplicates_existing_terms": all(
            term.lower() not in {str(item).strip().lower() for item in configured_terms.get(group, [])}
            for group, terms in grouped.items()
            for term in terms
        ),
    }
    return {
        "schema": "adaptive_residual_shadow_term_patch_proposal/v1",
        "description": "Review-only proposal converting mined suppressor terms into config patch groups.",
        "ok": all(checks.values()),
        "checks": checks,
        "miner_recommendation": miner.get("recommendation"),
        "candidate_count": len(miner.get("candidates") or []),
        "proposed_term_groups": grouped,
        "already_configured": already_configured,
        "review_required": review_required,
        "config_patch_preview": {
            "path": "config.yaml",
            "section": "adaptive_residual_shadow.terms",
            "append_terms": grouped,
            "already_configured": already_configured,
        },
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
        "promotion_ready": False,
    }


def build_proposal(logs: list[Path]) -> dict[str, Any]:
    before_config = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    miner = build_miner_report(logs)
    after_config = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    return build_proposal_from_miner(miner, before_config=before_config, after_config=after_config)


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Residual Shadow Term Patch Proposal\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Miner recommendation: `{report['miner_recommendation']}`\n"
        + f"Candidates: `{report['candidate_count']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Patch Preview\n\n```json\n"
        + json.dumps(report["config_patch_preview"], indent=2)
        + "\n```\n\n"
        + "## Review Required\n\n```json\n"
        + json.dumps(report["review_required"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a review-only residual suppressor config patch proposal.")
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--log-glob", default=DEFAULT_LOG_GLOB)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    logs = [Path(item) for item in args.log] if args.log else discover_logs(args.log_glob)
    logs = [log for log in logs if log.exists() and log.is_file()]
    report = build_proposal(logs)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "candidates": report["candidate_count"],
                "mutates_config": report["mutates_config"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
