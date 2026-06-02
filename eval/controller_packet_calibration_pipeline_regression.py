from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_calibration_pipeline import build_pipeline  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL, packet  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_regression_report.md"
OUT_PREFIX = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_regression"
LOG_JSONL = REPO_ROOT / "experiments" / "controller_packet_calibration_pipeline_regression_log.jsonl"


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


def main() -> int:
    rows = [
        packet(0, label="answer_correct", rating=1.0, would_override=True),
        packet(1, label="answer_correct", rating=1.0, would_override=True),
        packet(2, label="answer_missing_support", rating=-0.75, would_override=False),
        packet(3, label="answer_stale", rating=-0.75, would_override=False),
    ]
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    LOG_JSONL.write_text(
        "\n".join(json.dumps(ask_event(row), separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    report = build_pipeline([LOG_JSONL], out_prefix=OUT_PREFIX, ready_support=2, ready_logs=1, min_support=4, min_source_logs=2)
    checks = {
        "pipeline_ok": report["ok"] is True,
        "packet_count": report["summary"]["packet_count"] == 4,
        "cluster_count": report["summary"]["cluster_count"] == 3,
        "proposal_count": report["summary"]["proposal_count"] == 3,
        "promotion_candidate_count": report["summary"]["promotion_candidate_count"] == 1,
        "guard_blocks_all": report["summary"]["guard_ready_count"] == 0 and report["summary"]["guard_blocked_count"] == 3,
        "artifacts_written": all(Path(path).exists() for path in report["artifacts"].values()),
        "evidence_context_feature_diagnostics_present": isinstance(report.get("diagnostics"), dict)
        and "evidence_context_features_present" in report["diagnostics"],
        "review_separation_present": bool(report.get("review_separation_action_counts") is not None),
        "bridge_separator_present": report.get("bridge_separator_count") == 0,
        "bridge_holdout_present": isinstance(report.get("bridge_separator_holdout"), dict),
        "bridge_loso_present": isinstance(report.get("bridge_leave_one_source_out"), dict)
        and report["bridge_leave_one_source_out"].get("source_count") is not None
        and isinstance(report["bridge_leave_one_source_out"].get("readiness_blockers"), list),
        "bridge_loso_config_policy_honored": report["bridge_leave_one_source_out"].get("minimum_sources_for_candidate") == 3
        and report["bridge_leave_one_source_out"].get("minimum_samples_for_candidate") == 30,
        "calibration_manifest_present": (report.get("calibration_system") or {}).get("schema")
        == "controller_packet_calibration_system_manifest/v1",
        "calibration_manifest_report_only": (report.get("calibration_system") or {}).get("report_only") is True
        and (report.get("calibration_system") or {}).get("mutates_runtime") is False
        and (report.get("calibration_system") or {}).get("mutates_config") is False,
        "real_log_readiness_present": (report.get("real_log_readiness") or {}).get("schema")
        == "controller_packet_real_log_readiness/v1",
        "real_log_readiness_blocks_small_fixture": (report.get("real_log_readiness") or {}).get("readiness")
        == "analysis_only"
        and "packet_count_below_runtime_collection_target" in ((report.get("real_log_readiness") or {}).get("blockers") or [])
        and "single_source_log_only" in ((report.get("real_log_readiness") or {}).get("blockers") or []),
        "real_log_readiness_report_only": (report.get("real_log_readiness") or {}).get("report_only") is True
        and (report.get("real_log_readiness") or {}).get("mutates_runtime") is False
        and (report.get("real_log_readiness") or {}).get("mutates_config") is False,
        "real_log_readiness_policy_present": ((report.get("real_log_readiness") or {}).get("policy") or {}).get("schema")
        == "controller_packet_real_log_readiness_policy/v1"
        and ((report.get("real_log_readiness") or {}).get("policy") or {}).get("min_packets_for_runtime_collection") == 12
        and ((report.get("real_log_readiness") or {}).get("policy") or {}).get("min_sources_for_runtime_collection") == 2,
        "report_only": report["report_only"] is True and report["mutates_runtime"] is False and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_calibration_pipeline_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "pipeline": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Pipeline Regression",
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
