from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_ogcf_bridge_leave_one_source_out import build_report  # noqa: E402
from eval.controller_packet_ogcf_bridge_source_holdout_regression import packet  # noqa: E402


PACKETS_JSONL = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_packets.jsonl"
UNDERPOWERED_PACKETS_JSONL = (
    REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_underpowered_packets.jsonl"
)
SEPARATOR_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_regression_report.md"


def write_fixtures() -> None:
    rows = []
    variants = ("alpha_source", "beta_source", "gamma_source")
    for source_idx, variant in enumerate(variants):
        for idx in range(6):
            rows.append(packet(idx + source_idx * 20, positive=True, variant=variant))
            rows.append(packet(idx + source_idx * 20, positive=False, variant=variant))
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    underpowered_rows = []
    for source_idx, variant in enumerate(("tiny_alpha_source", "tiny_beta_source")):
        underpowered_rows.append(packet(source_idx * 20, positive=True, variant=variant))
        underpowered_rows.append(packet(source_idx * 20, positive=False, variant=variant))
    UNDERPOWERED_PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in underpowered_rows) + "\n",
        encoding="utf-8",
    )
    separator = {
        "schema": "controller_packet_bridge_separator/v1",
        "separators": [
            {
                "id": "leave_one_source_separator",
                "rule": {
                    "positive_when": {
                        "ogcf_meta_present": True,
                        "intent_in": ["bridge_geometry_query"],
                        "feedback_label_in": ["answer_bridge_warning_useful", "bridge_relevant"],
                    },
                    "negative_when": {
                        "ogcf_meta_present": True,
                        "intent_in": ["ordinary_context"],
                        "feedback_label_in": ["answer_bridge_warning_noise", "ogcf_false_positive"],
                    },
                },
            }
        ],
    }
    SEPARATOR_JSON.write_text(json.dumps(separator, indent=2), encoding="utf-8")


def main() -> int:
    write_fixtures()
    report = build_report([PACKETS_JSONL], SEPARATOR_JSON)
    underpowered_report = build_report([UNDERPOWERED_PACKETS_JSONL], SEPARATOR_JSON)
    permissive_policy = {
        "controller_packet_calibration": {
            "bridge_leave_one_source_out": {
                "min_sources_for_candidate": 2,
                "min_samples_for_candidate": 4,
            }
        }
    }
    underpowered_permissive_report = build_report(
        [UNDERPOWERED_PACKETS_JSONL],
        SEPARATOR_JSON,
        policy_config=permissive_policy,
    )
    checks = {
        "report_ok": report["ok"] is True,
        "source_count": report["source_count"] == 3,
        "sample_count": report["sample_count"] == 36,
        "candidate_thresholds_recorded": report["minimum_sources_for_candidate"] == 3
        and report["minimum_samples_for_candidate"] == 30,
        "fold_count": len(report["folds"]) == 3,
        "all_folds_clean": all(
            fold["test_learned"]["match_rate"] == 1.0
            and fold["test_learned"]["false_positive_count"] == 0
            and fold["test_learned"]["false_negative_count"] == 0
            for fold in report["folds"]
        ),
        "learned_candidate": report["learned_scorer_candidate"] is True,
        "candidate_has_no_readiness_blockers": report["readiness_blockers"] == [],
        "underpowered_artifact_blocked": underpowered_report["ok"] is True
        and underpowered_report["learned_scorer_candidate"] is False
        and any("source_count_below_minimum" in item for item in underpowered_report["readiness_blockers"])
        and any("sample_count_below_minimum" in item for item in underpowered_report["readiness_blockers"]),
        "config_threshold_override_honored": underpowered_permissive_report["ok"] is True
        and underpowered_permissive_report["minimum_sources_for_candidate"] == 2
        and underpowered_permissive_report["minimum_samples_for_candidate"] == 4
        and underpowered_permissive_report["learned_scorer_candidate"] is True
        and underpowered_permissive_report["policy"]["source"] == "config_or_defaults",
        "promotion_blocked": report["promotion_ready"] is False,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_ogcf_bridge_leave_one_source_out_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
        "underpowered_report": underpowered_report,
        "underpowered_permissive_report": underpowered_permissive_report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Leave-One-Source-Out Regression",
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
