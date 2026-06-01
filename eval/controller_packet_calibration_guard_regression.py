from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_guard import build_report  # noqa: E402
from eval.controller_packet_calibration_proposals_regression import BANK_JSON  # noqa: E402
from eval.controller_packet_calibration_proposals import build_report as build_proposals  # noqa: E402
from eval.controller_packet_memory_bank import build_report as build_bank  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL, packet  # noqa: E402


PROPOSALS_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_regression_proposals.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_guard_regression_report.md"


def main() -> int:
    rows = [
        packet(0, label="answer_correct", rating=1.0, would_override=True),
        packet(1, label="answer_correct", rating=1.0, would_override=True),
        packet(2, label="answer_missing_support", rating=-0.75, would_override=False),
        packet(3, label="answer_stale", rating=-0.75, would_override=False),
        packet(4, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=False),
        packet(5, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(6, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(7, label="ogcf_false_positive", rating=-0.75, would_override=False, ogcf_present=True),
    ]
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    bank = build_bank([PACKETS_JSONL], ready_support=2, ready_logs=1)
    BANK_JSON.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    proposals = build_proposals(BANK_JSON)
    PROPOSALS_JSON.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
    report = build_report(PROPOSALS_JSON, min_support=4, min_source_logs=2)
    blocked_reasons = {
        reason
        for proposal in report["guarded_proposals"]
        for reason in proposal.get("blocked_reasons") or []
    }
    checks = {
        "guard_ok": report["ok"] is True,
        "has_proposals": report["proposal_count"] == 6,
        "no_ready_promotions": report["ready_count"] == 0,
        "blocked_all": report["blocked_count"] == 6,
        "review_items_block_candidate": "review_items_present" in blocked_reasons,
        "requires_multiple_logs": "insufficient_source_logs" in blocked_reasons,
        "requires_more_support": "insufficient_support" in blocked_reasons,
        "blocks_bridge_gap": "bridge_label_without_ogcf" in blocked_reasons,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_calibration_guard_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "guard": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Guard Regression",
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
