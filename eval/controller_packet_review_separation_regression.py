from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_guard import build_report as build_guard  # noqa: E402
from eval.controller_packet_calibration_proposals import build_report as build_proposals  # noqa: E402
from eval.controller_packet_calibration_proposals_regression import BANK_JSON  # noqa: E402
from eval.controller_packet_memory_bank import build_report as build_bank  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL, packet  # noqa: E402
from eval.controller_packet_review_separation import build_report  # noqa: E402


PROPOSALS_JSON = REPO_ROOT / "experiments" / "controller_packet_review_separation_regression_proposals.json"
GUARD_JSON = REPO_ROOT / "experiments" / "controller_packet_review_separation_regression_guard.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_review_separation_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_review_separation_regression_report.md"


def main() -> int:
    rows = [
        packet(0, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(1, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(2, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(3, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=True),
        packet(4, label="ogcf_false_positive", rating=-0.75, would_override=False, ogcf_present=True),
        packet(5, label="ogcf_false_positive", rating=-0.75, would_override=False, ogcf_present=True),
        packet(6, label="ogcf_false_positive", rating=-0.75, would_override=False, ogcf_present=True),
        packet(7, label="ogcf_false_positive", rating=-0.75, would_override=False, ogcf_present=True),
    ]
    for idx, row in enumerate(rows):
        row["source_log"] = f"review_separation_fixture_{idx % 2}.jsonl"
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    bank = build_bank([PACKETS_JSONL], ready_support=2, ready_logs=1)
    BANK_JSON.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    proposals = build_proposals(BANK_JSON)
    PROPOSALS_JSON.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
    guard = build_guard(PROPOSALS_JSON, min_support=4, min_source_logs=2)
    GUARD_JSON.write_text(json.dumps(guard, indent=2), encoding="utf-8")
    report = build_report(PROPOSALS_JSON, GUARD_JSON)
    actions = report.get("action_counts") if isinstance(report.get("action_counts"), dict) else {}
    first = report["analyses"][0] if report.get("analyses") else {}
    features = first.get("features") if isinstance(first.get("features"), dict) else {}
    checks = {
        "report_ok": report["ok"] is True,
        "analysis_count": report["analysis_count"] == 1,
        "bridge_action_present": actions.get("train_or_calibrate_bridge_intent_separator_before_promotion") == 1,
        "candidate_is_ogcf_bridge": first.get("candidate_kind") == "ogcf_bridge_behavior_candidate",
        "review_is_negative": first.get("review_kind") == "negative_feedback_review",
        "review_only_label": "ogcf_false_positive" in features.get("review_only_labels", []),
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_review_separation_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Review Separation Regression",
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
