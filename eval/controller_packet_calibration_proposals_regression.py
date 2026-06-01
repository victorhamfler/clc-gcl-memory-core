from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_proposals import build_report  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL, packet  # noqa: E402
from eval.controller_packet_memory_bank import build_report as build_bank  # noqa: E402


BANK_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_regression_bank.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_regression_report.md"


def main() -> int:
    PACKETS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        packet(0, label="answer_correct", rating=1.0, would_override=True),
        packet(1, label="answer_correct", rating=1.0, would_override=True),
        packet(2, label="answer_missing_support", rating=-0.75, would_override=False),
        packet(3, label="answer_stale", rating=-0.75, would_override=False),
        packet(4, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=False),
    ]
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    bank = build_bank([PACKETS_JSONL], ready_support=2, ready_logs=1)
    BANK_JSON.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    report = build_report(BANK_JSON)
    kinds = {item["kind"] for item in report["proposals"]}
    checks = {
        "report_ok": report["ok"] is True,
        "proposal_count": report["proposal_count"] == 4,
        "promotion_candidate_count": report["promotion_candidate_count"] == 1,
        "review_item_count": report["review_item_count"] == 3,
        "benefit_candidate_present": "resolver_residual_benefit_candidate" in kinds,
        "missing_support_review_present": "missing_support_review" in kinds,
        "stale_review_present": "stale_answer_review" in kinds,
        "bridge_gap_review_present": "bridge_metadata_gap_review" in kinds,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_calibration_proposals_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "proposal_kinds": sorted(kinds),
        "report": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Proposals Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
