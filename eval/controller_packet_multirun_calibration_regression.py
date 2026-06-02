from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_pipeline import build_pipeline, write_pipeline_report  # noqa: E402
from eval.controller_packet_memory_bank_regression import packet  # noqa: E402
from eval.controller_packet_multirun_calibration import build_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_report.md"
RUN_A_LOG = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_a.jsonl"
RUN_B_LOG = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_b.jsonl"
RUN_A_PREFIX = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_a"
RUN_B_PREFIX = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_b"
RUN_A_JSON = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_a_results.json"
RUN_A_MD = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_a_report.md"
RUN_B_JSON = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_b_results.json"
RUN_B_MD = REPO_ROOT / "experiments" / "controller_packet_multirun_calibration_regression_run_b_report.md"


def ask_event(packet_row: dict) -> dict:
    return {
        "schema_version": 1,
        "operation_id": packet_row["operation_id"],
        "event_type": "ask",
        "payload": {
            "controller_evidence_packet": packet_row,
            "request": {"query": packet_row["request"]["query"]},
            "response": {"confidence": packet_row["answer"]["confidence"], "conflict": packet_row["answer"]["conflict"]},
        },
    }


def write_log(path: Path, *, offset: int) -> None:
    rows = [
        packet(offset + 0, label="answer_correct", rating=1.0, would_override=True),
        packet(offset + 1, label="answer_correct", rating=1.0, would_override=True),
        packet(offset + 2, label="answer_missing_support", rating=-0.75, would_override=False),
        packet(offset + 3, label="answer_stale", rating=-0.75, would_override=False),
    ]
    path.write_text(
        "\n".join(json.dumps(ask_event(row), separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    write_log(RUN_A_LOG, offset=100)
    write_log(RUN_B_LOG, offset=200)
    run_a = build_pipeline([RUN_A_LOG], out_prefix=RUN_A_PREFIX, ready_support=2, ready_logs=1, min_support=4, min_source_logs=2)
    run_b = build_pipeline([RUN_B_LOG], out_prefix=RUN_B_PREFIX, ready_support=2, ready_logs=1, min_support=4, min_source_logs=2)
    write_pipeline_report(run_a, RUN_A_JSON, RUN_A_MD)
    write_pipeline_report(run_b, RUN_B_JSON, RUN_B_MD)
    report = build_report([RUN_A_JSON, RUN_B_JSON], min_runs=2)
    recurring = [item for item in report["clusters"] if item["recurring"]]
    checks = {
        "report_ok": report["ok"] is True,
        "run_count": report["run_count"] == 2,
        "recurring_clusters": report["recurring_cluster_count"] >= 3,
        "has_positive_recurring": any("resolver_residual_benefit_candidate" in item["key"] for item in recurring),
        "has_missing_review_recurring": any("missing_support_review" in item["key"] for item in recurring),
        "has_stale_review_recurring": any("stale_answer_review" in item["key"] for item in recurring),
        "bridge_loso_summary_present": isinstance(report.get("bridge_leave_one_source_out"), dict)
        and report["bridge_leave_one_source_out"].get("observed_run_count") == 2
        and report["bridge_leave_one_source_out"].get("candidate_run_count") == 0,
        "next_target": report["next_development_target"] == "collect_more_independent_bridge_sources_for_loso",
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_multirun_calibration_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "multirun": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Multi-Run Calibration Regression",
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
