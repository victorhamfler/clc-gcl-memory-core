from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_bridge_separator import build_report  # noqa: E402
from eval.controller_packet_review_separation_regression import GUARD_JSON, PROPOSALS_JSON, main as generate_review_fixture  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_regression_report.md"
REVIEW_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_regression_review_separation.json"


def main() -> int:
    generated = generate_review_fixture()
    if generated != 0:
        return generated
    from eval.controller_packet_review_separation import build_report as build_review_report

    review_report = build_review_report(PROPOSALS_JSON, GUARD_JSON)
    REVIEW_JSON.write_text(json.dumps(review_report, indent=2), encoding="utf-8")
    report = build_report(REVIEW_JSON)
    first = report["separators"][0] if report.get("separators") else {}
    checks = {
        "report_ok": report["ok"] is True,
        "separator_count": report["separator_count"] == 1,
        "positive_intent": "cross_domain_bridge_synthesis" in first.get("positive_intents", []),
        "negative_label": "ogcf_false_positive" in first.get("negative_labels", []),
        "holdout_ready": first.get("readiness") == "holdout_ready",
        "promotion_blocked": first.get("promotion_ready") is False,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_bridge_separator_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Bridge Separator Regression",
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
