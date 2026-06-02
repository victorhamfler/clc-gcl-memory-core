from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.controller_packet_calibration import normalize_controller_packet_calibration_policy  # noqa: E402
from serve import MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_runtime_view_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_runtime_view_regression_report.md"


def local_runtime_config() -> dict:
    config = load_config(ROOT)
    config["embedding"] = {
        "backend": "hash",
        "dim": int(config.get("embedding_dim") or 768),
    }
    return config


def main() -> int:
    base_config = local_runtime_config()
    override_config = dict(base_config)
    override_config["controller_packet_calibration"] = {
        "bridge_scorer": {
            "min_test_samples_for_candidate": 11,
            "require_zero_false_positives": False,
            "require_zero_false_negatives": True,
            "require_not_worse_than_symbolic": False,
        },
        "bridge_leave_one_source_out": {
            "min_sources_for_candidate": 6,
            "min_samples_for_candidate": 77,
        },
    }
    expected_policy = normalize_controller_packet_calibration_policy(override_config)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "controller_packet_calibration_runtime_view.db"
        api = MemoryApi(ROOT, db_path=db_path, config_override=override_config)
        try:
            view = api.config()
        finally:
            api.close()

    runtime_policy = view.get("controller_packet_calibration")
    bridge_scorer = runtime_policy.get("bridge_scorer") if isinstance(runtime_policy, dict) else {}
    bridge_loso = runtime_policy.get("bridge_leave_one_source_out") if isinstance(runtime_policy, dict) else {}
    checks = {
        "config_view_has_controller_packet_calibration": isinstance(runtime_policy, dict),
        "runtime_view_matches_normalized_override": runtime_policy == expected_policy,
        "bridge_scorer_override_visible": bridge_scorer.get("min_test_samples_for_candidate") == 11
        and bridge_scorer.get("require_zero_false_positives") is False
        and bridge_scorer.get("require_zero_false_negatives") is True
        and bridge_scorer.get("require_not_worse_than_symbolic") is False,
        "loso_override_visible": bridge_loso.get("min_sources_for_candidate") == 6
        and bridge_loso.get("min_samples_for_candidate") == 77,
        "report_only_and_non_mutating": runtime_policy.get("report_only") is True
        and runtime_policy.get("mutates_runtime") is False
        and runtime_policy.get("mutates_config") is False
        and bridge_scorer.get("mutates_runtime") is False
        and bridge_loso.get("mutates_runtime") is False,
    }
    report = {
        "schema": "controller_packet_calibration_runtime_view_regression/v1",
        "description": "Runtime config-view guard for controller packet calibration policy exposure.",
        "ok": all(checks.values()),
        "checks": checks,
        "runtime_policy": runtime_policy,
        "expected_policy": expected_policy,
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Runtime View Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Runtime Policy",
            "",
            "```json",
            json.dumps(runtime_policy, indent=2),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
