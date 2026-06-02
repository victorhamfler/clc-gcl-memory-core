from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_ogcf_bridge_source_holdout import build_report  # noqa: E402


TRAIN_JSONL = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_train.jsonl"
TEST_JSONL = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_test.jsonl"
SEPARATOR_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_regression_report.md"


def packet(idx: int, *, positive: bool, variant: str) -> dict:
    if positive:
        label = "answer_bridge_warning_useful"
        intent = "bridge_geometry_query"
        query = f"{variant}: map the bridge geometry between planning cluster {idx} and retrieval loop pressure"
        text = (
            f"{variant} evidence: bridge topology links two memory domains through shared geometry, "
            "loop pressure, and cross-domain support."
        )
        overload = 0.78 + (idx % 3) * 0.03
        affected = 0.62 + (idx % 4) * 0.04
        support = 3 + (idx % 2)
        duplicate = 0.04 + (idx % 2) * 0.03
        score = 0.72 + (idx % 4) * 0.03
        claim = 0.68 + (idx % 3) * 0.04
        text_match = 0.64 + (idx % 2) * 0.05
    else:
        label = "ogcf_false_positive"
        intent = "ordinary_context"
        query = f"{variant}: ordinary status lookup for single topic preference note {idx}"
        text = (
            f"{variant} evidence: ordinary single-topic lookup with unrelated status details, "
            "duplicate clutter, and no useful geometry bridge."
        )
        overload = 0.12 + (idx % 3) * 0.03
        affected = 0.08 + (idx % 4) * 0.02
        support = 1
        duplicate = 0.35 + (idx % 2) * 0.08
        score = 0.26 + (idx % 4) * 0.03
        claim = 0.18 + (idx % 3) * 0.04
        text_match = 0.2 + (idx % 2) * 0.05
    return {
        "schema": "controller_evidence_packet/v1",
        "operation_id": f"op_source_holdout_{variant}_{idx}_{'pos' if positive else 'neg'}",
        "source_log": f"{variant}.jsonl",
        "request": {"query": query, "namespace": f"source-holdout-{variant}", "agent_id": "fixture"},
        "answer": {"confidence": 0.7 if positive else 0.45, "conflict": False, "evidence_count": 2},
        "evidence": {
            "selected": [
                {
                    "memory_id": f"mem_{variant}_{idx}_a",
                    "rank": 1,
                    "score": score,
                    "claim_scope_score": claim,
                    "text_match_score": text_match,
                    "memory_state": "current",
                    "text_preview": text,
                },
                {
                    "memory_id": f"mem_{variant}_{idx}_b",
                    "rank": 2,
                    "score": max(0.01, score - 0.06),
                    "claim_scope_score": max(0.0, claim - 0.08),
                    "text_match_score": max(0.0, text_match - 0.1),
                    "memory_state": "current",
                    "text_preview": text,
                },
            ],
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
            "maintenance_pressure": 0.18 if positive else 0.56,
        },
        "feedback_summary": {"count": 1, "labels": {label: 1}, "scopes": {"answer": 1}},
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_fixtures() -> None:
    train_rows = []
    test_rows = []
    for idx in range(8):
        train_rows.append(packet(idx, positive=True, variant="train_a"))
        train_rows.append(packet(idx, positive=False, variant="train_a"))
        test_rows.append(packet(idx + 20, positive=True, variant="holdout_b"))
        test_rows.append(packet(idx + 20, positive=False, variant="holdout_b"))
    TRAIN_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in train_rows) + "\n",
        encoding="utf-8",
    )
    TEST_JSONL.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in test_rows) + "\n",
        encoding="utf-8",
    )
    separator = {
        "schema": "controller_packet_bridge_separator/v1",
        "separators": [
            {
                "id": "source_holdout_separator",
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
    report = build_report([TRAIN_JSONL], [TEST_JSONL], SEPARATOR_JSON)
    strict_policy = {
        "controller_packet_calibration": {
            "bridge_scorer": {
                "min_test_samples_for_candidate": 99,
                "require_zero_false_positives": True,
                "require_zero_false_negatives": True,
                "require_not_worse_than_symbolic": True,
            }
        }
    }
    blocked_report = build_report([TRAIN_JSONL], [TEST_JSONL], SEPARATOR_JSON, policy_config=strict_policy)
    checks = {
        "report_ok": report["ok"] is True,
        "train_count": report["train_count"] == 16,
        "test_count": report["test_count"] == 16,
        "learned_clean": report["test_learned"]["match_rate"] == 1.0
        and report["test_learned"]["false_positive_count"] == 0
        and report["test_learned"]["false_negative_count"] == 0,
        "symbolic_clean": report["test_symbolic"]["match_rate"] == 1.0,
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
        "schema": "controller_packet_ogcf_bridge_source_holdout_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "report": report,
        "blocked_report": blocked_report,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Source Holdout Regression",
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
