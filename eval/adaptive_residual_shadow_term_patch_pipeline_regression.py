from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy  # noqa: E402
from eval.adaptive_residual_shadow_term_candidate_miner import mine_reports  # noqa: E402
from eval.adaptive_residual_shadow_term_miner_regression import SYNTHETIC_REPORTS  # noqa: E402
from eval.adaptive_residual_shadow_term_patch_proposal import build_proposal_from_miner  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_pipeline_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_patch_pipeline_regression_report.md"


def build_report() -> dict[str, object]:
    before = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    mined = mine_reports(SYNTHETIC_REPORTS, load_policy(ROOT))
    after_mining = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    proposal = build_proposal_from_miner(mined, before_config=before, after_config=after_mining)
    grouped = proposal.get("proposed_term_groups") if isinstance(proposal.get("proposed_term_groups"), dict) else {}
    configured = proposal.get("already_configured") if isinstance(proposal.get("already_configured"), dict) else {}
    sensitive = set(grouped.get("sensitive_private") or [])
    unsupported = set(grouped.get("unsupported_proof") or [])
    namespace = set(grouped.get("ordinary_namespace_profile") or [])
    configured_sensitive = set(configured.get("sensitive_private") or [])
    configured_unsupported = set(configured.get("unsupported_proof") or [])
    final = (ROOT / "config.yaml").read_text(encoding="utf-8") if (ROOT / "config.yaml").exists() else ""
    checks = {
        "miner_has_candidates": bool(mined.get("candidates")),
        "proposal_ok": bool(proposal.get("ok")),
        "groups_sensitive_private_new_terms": bool(sensitive & {"hidden deployment key", "deployment key retrieve"}),
        "groups_sensitive_private_existing_terms": bool(configured_sensitive & {"deployment key"}),
        "groups_unsupported_proof_new_terms": bool(unsupported & {"changed live", "residual changed live"}),
        "groups_unsupported_proof_existing_terms": bool(configured_unsupported & {"changed live answers"}),
        "groups_namespace_profile": bool(namespace & {"justify cross-namespace", "profile preference", "profile preference justify"}),
        "deduplicates_existing_terms": bool((proposal.get("checks") or {}).get("deduplicates_existing_terms")),
        "config_unchanged": before == final,
        "proposal_review_only": proposal.get("mutates_config") is False and proposal.get("mutates_runtime") is False,
    }
    return {
        "schema": "adaptive_residual_shadow_term_patch_pipeline_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "mined_candidate_count": len(mined.get("candidates") or []),
        "proposal": proposal,
        "promotion_ready": False,
    }


def write_report(report: dict[str, object]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Term Patch Pipeline Regression\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Mined candidates: `{report['mined_candidate_count']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Patch Preview\n\n```json\n"
        + json.dumps(report["proposal"]["config_patch_preview"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "mined_candidates": report["mined_candidate_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
