from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_ogcf_bridge_scorer import build_report  # noqa: E402


PACKETS_JSONL = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_packets.jsonl"
SEPARATOR_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_regression_report.md"


def packet(idx: int, *, positive: bool) -> dict:
    if positive:
        label = "answer_bridge_warning_useful"
        intent = "bridge_geometry_query"
        query = f"How does bridge geometry connect domain cluster {idx} with loop overload?"
        text = "Bridge geometry evidence shows cross-domain memory clusters connect through a shared loop topology."
        overload = 0.86
        affected = 0.72
        support = 4
        duplicate = 0.05
        score = 0.82
        claim = 0.78
        text_match = 0.74
    else:
        label = "ogcf_false_positive"
        intent = "ordinary_context"
        query = f"What is the ordinary status lookup for single topic note {idx}?"
        text = "Ordinary single-topic status note with unrelated lookup details and no cross-domain bridge."
        overload = 0.18
        affected = 0.12
        support = 1
        duplicate = 0.42
        score = 0.34
        claim = 0.22
        text_match = 0.25
    return {
        "schema": "controller_evidence_packet/v1",
        "operation_id": f"op_ogcf_bridge_feature_{idx:02d}",
        "request": {"query": query, "namespace": "feature-fixture", "agent_id": "fixture"},
        "answer": {"confidence": 0.72 if positive else 0.46, "conflict": False, "evidence_count": 2},
        "evidence": {
            "selected": [
                {
                    "memory_id": f"mem_{idx}_a",
                    "rank": 1,
                    "score": score,
                    "claim_scope_score": claim,
                    "text_match_score": text_match,
                    "memory_state": "current",
                    "text_preview": text,
                },
                {
                    "memory_id": f"mem_{idx}_b",
                    "rank": 2,
                    "score": max(0.01, score - 0.08),
                    "claim_scope_score": max(0.0, claim - 0.1),
                    "text_match_score": max(0.0, text_match - 0.12),
                    "memory_state": "current",
                    "text_preview": text,
                },
            ],
            "retrieval_context": [],
            "state_summary": {
                "counts": {"current": 2},
                "has_current": True,
                "has_stale": False,
                "has_disputed": False,
                "has_summary": False,
            },
        },
        "canonical": {
            "max_support_count": support,
            "supported_rows": 2 if positive else 0,
            "nonkeeper_rows": 0 if positive else 1,
            "duplicate_pressure": duplicate,
        },
        "ogcf": {
            "meta_present": True,
            "intent": intent,
            "bridge_overload_score": overload,
            "effective_affected_memory_ratio": affected,
            "maintenance_pressure": 0.15 if positive else 0.55,
        },
        "feedback_summary": {"count": 1, "labels": {label: 1}, "scopes": {"answer": 1}},
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_fixtures() -> None:
    rows = []
    for idx in range(10):
        rows.append(packet(idx, positive=True))
        rows.append(packet(idx + 20, positive=False))
    PACKETS_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    separator = {
        "schema": "controller_packet_bridge_separator/v1",
        "separators": [
            {
                "id": "fixture_bridge_separator",
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
    tiny_policy = {
        "controller_packet_calibration": {
            "bridge_scorer": {
                "min_test_samples_for_candidate": 99,
                "require_zero_false_positives": True,
                "require_zero_false_negatives": True,
                "require_not_worse_than_symbolic": True,
            }
        }
    }
    blocked_report = build_report([PACKETS_JSONL], SEPARATOR_JSON, policy_config=tiny_policy)
    checks = {
        "report_ok": report["ok"] is True,
        "sample_count": report["sample_count"] == 20,
        "has_enriched_features": "query_bridge_term_score" in report["feature_keys"]
        and "canonical_support_count" in report["feature_keys"],
        "learned_scores_test": report["test_learned"]["scored_count"] == report["test_count"],
        "learned_clean": report["test_learned"]["match_rate"] == 1.0
        and report["test_learned"]["false_positive_count"] == 0
        and report["test_learned"]["false_negative_count"] == 0,
        "learned_candidate": report["learned_scorer_candidate"] is True,
        "config_policy_recorded": report["policy"]["min_test_samples_for_candidate"] == 4
        and report["policy"]["require_zero_false_positives"] is True
        and report["policy"]["require_zero_false_negatives"] is True,
        "strict_config_blocks_candidate": blocked_report["learned_scorer_candidate"] is False
        and any("test_count_below_minimum" in item for item in blocked_report["readiness_blockers"]),
        "promotion_blocked": report["promotion_ready"] is False,
        "report_only": report["report_only"] is True
        and report["mutates_runtime"] is False
        and report["mutates_config"] is False,
    }
    result = {
        "schema": "controller_packet_ogcf_bridge_scorer_feature_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
        "blocked_report": blocked_report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Scorer Feature Regression",
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
