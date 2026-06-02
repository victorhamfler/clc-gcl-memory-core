from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.controller_packet_calibration import (  # noqa: E402
    normalize_bridge_loso_policy,
    normalize_bridge_scorer_policy,
    normalize_controller_packet_calibration_policy,
    normalize_real_log_readiness_policy,
)


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_config_regression_report.md"


def build_report() -> dict[str, Any]:
    config = load_config(ROOT)
    default_scorer = normalize_bridge_scorer_policy(config)
    default_loso = normalize_bridge_loso_policy(config)
    default_readiness = normalize_real_log_readiness_policy(config)
    default_policy = normalize_controller_packet_calibration_policy(config)
    override_config = {
        "controller_packet_calibration": {
            "bridge_scorer": {
                "min_test_samples_for_candidate": 9,
                "require_zero_false_positives": False,
                "require_zero_false_negatives": False,
                "require_not_worse_than_symbolic": False,
            },
            "bridge_leave_one_source_out": {
                "min_sources_for_candidate": 5,
                "min_samples_for_candidate": 80,
            },
            "real_log_readiness": {
                "min_packets_for_runtime_collection": 20,
                "min_sources_for_runtime_collection": 4,
                "min_packets_for_learned_scorer_evaluation": 90,
                "min_sources_for_learned_scorer_evaluation": 6,
                "require_full_evidence_context_feature_coverage": False,
                "block_on_review_items": False,
            },
        }
    }
    override_scorer = normalize_bridge_scorer_policy(override_config)
    override_loso = normalize_bridge_loso_policy(override_config)
    override_readiness = normalize_real_log_readiness_policy(override_config)
    cli_scorer = normalize_bridge_scorer_policy(override_config, min_test_samples=3)
    cli_loso = normalize_bridge_loso_policy(override_config, min_sources=2, min_samples=10)
    checks = {
        "config_section_present": isinstance(config.get("controller_packet_calibration"), dict),
        "default_scorer_policy": default_scorer["schema"] == "controller_packet_bridge_scorer_policy/v1"
        and default_scorer["min_test_samples_for_candidate"] == 4
        and default_scorer["require_zero_false_positives"] is True
        and default_scorer["require_zero_false_negatives"] is True
        and default_scorer["require_not_worse_than_symbolic"] is True,
        "default_loso_policy": default_loso["schema"] == "controller_packet_bridge_loso_policy/v1"
        and default_loso["min_sources_for_candidate"] == 3
        and default_loso["min_samples_for_candidate"] == 30,
        "default_readiness_policy": default_readiness["schema"] == "controller_packet_real_log_readiness_policy/v1"
        and default_readiness["min_packets_for_runtime_collection"] == 12
        and default_readiness["min_sources_for_runtime_collection"] == 2
        and default_readiness["min_packets_for_learned_scorer_evaluation"] == 30
        and default_readiness["min_sources_for_learned_scorer_evaluation"] == 3
        and default_readiness["require_full_evidence_context_feature_coverage"] is True
        and default_readiness["block_on_review_items"] is True,
        "combined_policy_view": default_policy["schema"] == "controller_packet_calibration_policy/v1"
        and default_policy["bridge_scorer"] == default_scorer
        and default_policy["bridge_leave_one_source_out"] == default_loso
        and default_policy["real_log_readiness"] == default_readiness,
        "override_scorer_policy": override_scorer["min_test_samples_for_candidate"] == 9
        and override_scorer["require_zero_false_positives"] is False
        and override_scorer["require_zero_false_negatives"] is False
        and override_scorer["require_not_worse_than_symbolic"] is False,
        "override_loso_policy": override_loso["min_sources_for_candidate"] == 5
        and override_loso["min_samples_for_candidate"] == 80,
        "override_readiness_policy": override_readiness["min_packets_for_runtime_collection"] == 20
        and override_readiness["min_sources_for_runtime_collection"] == 4
        and override_readiness["min_packets_for_learned_scorer_evaluation"] == 90
        and override_readiness["min_sources_for_learned_scorer_evaluation"] == 6
        and override_readiness["require_full_evidence_context_feature_coverage"] is False
        and override_readiness["block_on_review_items"] is False,
        "cli_overrides_are_explicit": cli_scorer["min_test_samples_for_candidate"] == 3
        and cli_scorer["source"] == "config_with_cli_overrides"
        and cli_loso["min_sources_for_candidate"] == 2
        and cli_loso["min_samples_for_candidate"] == 10
        and cli_loso["source"] == "config_with_cli_overrides",
        "report_only": default_scorer["report_only"] is True
        and default_loso["report_only"] is True
        and default_readiness["report_only"] is True
        and default_scorer["mutates_runtime"] is False
        and default_loso["mutates_runtime"] is False
        and default_readiness["mutates_runtime"] is False
        and default_scorer["mutates_config"] is False
        and default_loso["mutates_config"] is False
        and default_readiness["mutates_config"] is False,
    }
    return {
        "schema": "controller_packet_calibration_config_regression/v1",
        "description": "Config-view guard for controller packet calibration policies.",
        "ok": all(checks.values()),
        "checks": checks,
        "config_view": {
            **default_policy,
        },
        "override_view": {
            "bridge_scorer": override_scorer,
            "bridge_leave_one_source_out": override_loso,
            "real_log_readiness": override_readiness,
        },
        "cli_override_view": {
            "bridge_scorer": cli_scorer,
            "bridge_leave_one_source_out": cli_loso,
        },
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Config Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Config View",
            "",
            "```json",
            json.dumps(report["config_view"], indent=2),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "checks": report["checks"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
