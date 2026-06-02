from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_bridge_separator import build_report as build_separator  # noqa: E402
from eval.controller_packet_bridge_separator_regression import REVIEW_JSON, main as generate_separator_fixture  # noqa: E402
from eval.controller_packet_memory_bank_regression import PACKETS_JSONL  # noqa: E402
from eval.controller_packet_ogcf_bridge_scorer import build_report  # noqa: E402


SEPARATOR_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_regression_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_regression_report.md"


def main() -> int:
    generated = generate_separator_fixture()
    if generated != 0:
        return generated
    separator = build_separator(REVIEW_JSON)
    SEPARATOR_JSON.write_text(json.dumps(separator, indent=2), encoding="utf-8")
    report = build_report([PACKETS_JSONL], SEPARATOR_JSON)
    checks = {
        "report_ok": report["ok"] is True,
        "sample_count": report["sample_count"] == 8,
        "has_train_and_test": report["train_count"] > 0 and report["test_count"] > 0,
        "learned_scores_test": report["test_learned"]["scored_count"] == report["test_count"],
        "symbolic_scores_test": report["test_symbolic"]["scored_count"] == report["test_count"],
        "demotes_when_worse_than_symbolic": (
            report["test_learned"]["match_rate"] < report["test_symbolic"]["match_rate"]
            and report["learned_scorer_candidate"] is False
        )
        or report["test_learned"]["match_rate"] >= report["test_symbolic"]["match_rate"],
        "promotion_blocked": report["promotion_ready"] is False,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_ogcf_bridge_scorer_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Scorer Regression",
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
