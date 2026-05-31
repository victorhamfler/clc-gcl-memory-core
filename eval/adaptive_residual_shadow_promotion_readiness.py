from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_shadow_external_failure_replay import build_report as build_failure_replay_report  # noqa: E402
from eval.adaptive_residual_shadow_multi_log_eval import (  # noqa: E402
    PROCESSED_FAILURE_LOG_NAMES,
    build_multi_log_report,
    discover_logs,
    filter_logs,
)


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_promotion_readiness_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_promotion_readiness_report.md"
MIN_CLEAN_LOCAL_LOGS = 7


def log_kind(path: str) -> str:
    name = Path(path).name.lower()
    if "hermes" in name or "external" in name or "multi_day" in name or "multiday" in name:
        return "external_or_agent"
    if "natural" in name:
        return "local_natural_style"
    return "local_holdout"


def build_report() -> dict[str, Any]:
    logs = discover_logs("adaptive_residual_shadow_*_outcomes.jsonl")
    replay = build_failure_replay_report()
    processed_failure_logs = set(PROCESSED_FAILURE_LOG_NAMES) if replay.get("ok") else set()
    clean_logs = filter_logs(logs, processed_failure_logs)
    multi = build_multi_log_report(clean_logs, min_logs=MIN_CLEAN_LOCAL_LOGS)
    log_rows = []
    external_count = 0
    for row in multi.get("logs") or []:
        if not isinstance(row, dict):
            continue
        kind = log_kind(str(row.get("log_path") or ""))
        external_count += int(kind == "external_or_agent")
        enriched = dict(row)
        enriched["kind"] = kind
        log_rows.append(enriched)
    totals = multi.get("totals") if isinstance(multi.get("totals"), dict) else {}
    checks = {
        "clean_local_log_gate_passed": bool(multi.get("ok")),
        "has_min_clean_local_logs": int(totals.get("usable_log_count") or 0) >= MIN_CLEAN_LOCAL_LOGS,
        "processed_failure_replay_passed": bool(replay.get("ok")),
        "zero_harmful_overrides": int(totals.get("harmful_override_count") or 0) == 0,
        "zero_neutral_wrong_overrides": int(totals.get("neutral_wrong_override_count") or 0) == 0,
        "has_helpful_overrides": int(totals.get("helpful_override_count") or 0) > 0,
        "has_external_or_agent_log": external_count > 0,
        "report_only": True,
        "no_runtime_mutation": True,
    }
    promotion_ready = (
        checks["clean_local_log_gate_passed"]
        and checks["has_min_clean_local_logs"]
        and checks["zero_harmful_overrides"]
        and checks["zero_neutral_wrong_overrides"]
        and checks["has_helpful_overrides"]
        and checks["has_external_or_agent_log"]
    )
    return {
        "schema": "adaptive_residual_shadow_promotion_readiness/v1",
        "ok": checks["clean_local_log_gate_passed"] and checks["has_min_clean_local_logs"] and not promotion_ready,
        "min_clean_local_logs": MIN_CLEAN_LOCAL_LOGS,
        "checks": checks,
        "promotion_ready": promotion_ready,
        "blocked_reason": None if promotion_ready else "external_or_agent_residual_log_required",
        "recommendation": "collect_external_or_agent_residual_log" if not promotion_ready else "eligible_for_manual_promotion_review",
        "totals": totals,
        "logs": log_rows,
        "processed_failure_logs": sorted(processed_failure_logs),
        "processed_failure_replay": {
            "ok": replay.get("ok"),
            "source_eval": replay.get("source_eval"),
            "replayed": len(replay.get("replay_rows") or []),
        },
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow Promotion Readiness\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n"
        + f"Blocked reason: `{report['blocked_reason']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Totals\n\n```json\n"
        + json.dumps(report["totals"], indent=2)
        + "\n```\n\n"
        + "## Logs\n\n```json\n"
        + json.dumps(report["logs"], indent=2)
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
                "promotion_ready": report["promotion_ready"],
                "blocked_reason": report["blocked_reason"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
