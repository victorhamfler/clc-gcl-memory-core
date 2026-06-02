from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_bridge_separator import build_report as build_separator  # noqa: E402
from eval.controller_packet_bridge_separator_regression import REVIEW_JSON, main as generate_separator_fixture  # noqa: E402
from eval.controller_packet_bridge_separator_holdout import build_report  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL  # noqa: E402


SEPARATOR_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_holdout_regression_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_holdout_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_holdout_regression_report.md"


def main() -> int:
    generated = generate_separator_fixture()
    if generated != 0:
        return generated
    separator = build_separator(REVIEW_JSON)
    SEPARATOR_JSON.write_text(json.dumps(separator, indent=2), encoding="utf-8")
    report = build_report(SEPARATOR_JSON, [PACKETS_JSONL])
    checks = {
        "report_ok": report["ok"] is True,
        "has_bridge_packets": report["bridge_packet_count"] == 8,
        "scores_all_bridge_packets": report["scored_count"] == 8,
        "perfect_match": report["match_rate"] == 1.0,
        "no_false_positive": report["false_positive_count"] == 0,
        "no_false_negative": report["false_negative_count"] == 0,
        "promotion_blocked": report["promotion_ready"] is False,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_bridge_separator_holdout_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Bridge Separator Holdout Regression",
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
