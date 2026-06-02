from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_ogcf_bridge_feature_audit import build_report  # noqa: E402
from eval.controller_packet_ogcf_bridge_scorer_feature_regression import PACKETS_JSONL, write_fixtures  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_feature_audit_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_feature_audit_regression_report.md"


def main() -> int:
    write_fixtures()
    report = build_report([PACKETS_JSONL])
    checks = {
        "report_ok": report["ok"] is True,
        "bridge_packet_count": report["bridge_packet_count"] == 20,
        "has_both_labels": report["label_counts"].get("positive") == 10
        and report["label_counts"].get("negative") == 10,
        "feature_ready": report["feature_ready_for_learned_scorer"] is True,
        "has_strong_gaps": len(report["strong_gap_features"]) >= 2,
        "no_blockers": report["blockers"] == [],
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_ogcf_bridge_feature_audit_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "audit": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Feature Audit Regression",
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
