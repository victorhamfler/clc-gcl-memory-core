from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_memory_bank import build_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_memory_bank_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_memory_bank_regression_report.md"
PACKETS_JSONL = REPO_ROOT / "experiments" / "controller_packet_memory_bank_regression_packets.jsonl"


def packet(idx: int, *, label: str, rating: float, would_override: bool = False, ogcf_present: bool = True) -> dict:
    return {
        "schema": "controller_evidence_packet/v1",
        "operation_id": f"op_packet_bank_{idx}",
        "source_log": f"fixture_log_{idx % 2}.jsonl",
        "request": {
            "query": "Should the selector keep policy mutation report-only?",
            "namespace": "global",
            "agent_id": "packet-bank-fixture",
        },
        "answer": {
            "confidence": 0.72,
            "conflict": False,
            "evidence_count": 1,
        },
        "selector": {
            "decision": {
                "policy": "periodic_baseline",
                "action": "PROTECT_PERIODIC",
            }
        },
        "ogcf": {
            "meta_present": ogcf_present,
            "intent": "cross_domain_bridge_synthesis" if ogcf_present else None,
            "bridge_overload_score": 0.8 if ogcf_present else None,
        },
        "resolver_shadow": {
            "present": True,
            "actions": ["require_evidence_backed_answer"],
        },
        "adaptive_residual_shadow": {
            "present": True,
            "would_override_count": 1 if would_override else 0,
            "decisions": [
                {
                    "behavior_family": "supported_evidence",
                    "would_override": would_override,
                }
            ],
        },
        "feedback_summary": {
            "count": 1,
            "labels": {label: 1},
            "scopes": {"answer": 1},
            "has_answer_feedback": True,
            "has_memory_feedback": False,
        },
        "feedback": [
            {
                "scope": "answer",
                "label": label,
                "rating": rating,
            }
        ],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def main() -> int:
    PACKETS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        packet(0, label="answer_correct", rating=1.0, would_override=True),
        packet(1, label="answer_correct", rating=1.0, would_override=True),
        packet(2, label="answer_wrong_scope", rating=-0.75, would_override=False),
        packet(3, label="answer_bridge_warning_useful", rating=1.0, would_override=False, ogcf_present=False),
    ]
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    report = build_report([PACKETS_JSONL], ready_support=2, ready_logs=1)
    ready_clusters = [item for item in report["clusters"] if item["readiness"] == "calibration_candidate"]
    negative_clusters = [item for item in report["clusters"] if item["readiness"] == "review_negative_feedback"]
    checks = {
        "report_ok": report["ok"] is True,
        "packet_count": report["packet_count"] == 4,
        "cluster_count": report["cluster_count"] == 3,
        "ready_cluster_found": len(ready_clusters) == 1 and ready_clusters[0]["support"] == 2,
        "negative_cluster_found": len(negative_clusters) == 1 and negative_clusters[0]["support"] == 1,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
        "tracks_residual_packets": report["residual_packet_count"] == 4,
        "tracks_ogcf_packets": report["ogcf_packet_count"] == 3,
        "tracks_bridge_gap": report["bridge_feedback_without_ogcf_count"] == 1
        and report["diagnostics"]["bridge_feedback_has_ogcf_coverage"] is False,
    }
    result = {
        "schema": "controller_packet_memory_bank_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "bank": report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Memory Bank Regression",
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
