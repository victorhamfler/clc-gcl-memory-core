from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.resolver_shadow_outcome_collector import collect_dataset


OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_outcome_context_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_outcome_context_regression_report.md"


def selector_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "ogcf_meta_present": True,
        "decision": {
            "policy": "long_severe_r16_overwrite",
            "action": "LONG_SEVERE_VERIFIED_REFRESH",
            "reason": "fixture",
            "confidence": 0.74,
        },
        "diagnostics": {
            "ogcf_bridge_overload_score": 0.96,
            "ogcf_effective_affected_memory_ratio": 0.71,
            "ogcf_intent": "cross_domain_bridge_synthesis",
            "stale_current_conflict": 0.0,
        },
    }


def ask_event(operation_id: str, *, adaptive: bool) -> dict[str, Any]:
    snapshot = selector_snapshot()
    payload = {
        "request": {
            "query": "Should the OGCF bridge synthesis warning be disclosed?",
        },
        "response": {
            "answer": "The answer uses selected evidence and should disclose bridge pressure.",
            "confidence": 0.72,
            "conflict": False,
            "evidence": [
                {
                    "memory_id": "mem_bridge_context",
                    "text": "OGCF bridge synthesis has cross-domain pressure.",
                    "memory_state": "current",
                }
            ],
            "stale_context": [],
        },
    }
    if adaptive:
        payload["adaptive_memory_context"] = {
            "schema": "adaptive_memory_context/v1",
            "ok": True,
            "selector_snapshot": snapshot,
            "features": {
                "memory_bad_rate": 0.31,
                "probe_drop": 0.12,
                "csd_ratio": 1.2,
            },
            "diagnostics": dict(snapshot["diagnostics"]),
            "retrieval_context": [
                {
                    "memory_id": "mem_bridge_context",
                    "score": 0.91,
                    "text": "OGCF bridge synthesis has cross-domain pressure.",
                }
            ],
            "ogcf_meta_present": True,
        }
    else:
        payload["selector_snapshot"] = snapshot
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": None,
        "event_type": "ask",
        "payload": payload,
    }


def feedback_event(operation_id: str, linked_operation_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": linked_operation_id,
        "event_type": "feedback",
        "payload": {
            "request": {
                "feedback_scope": "answer",
                "label": "answer_bridge_warning_useful",
                "rating": 1.0,
                "linked_operation_id": linked_operation_id,
                "selected_memory_ids": ["mem_bridge_context"],
            },
            "feedback": {
                "feedback_scope": "answer",
                "label": "answer_bridge_warning_useful",
                "rating": 1.0,
                "selected_memory_ids": ["mem_bridge_context"],
            },
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def comparable(example: dict[str, Any]) -> dict[str, Any]:
    return {
        key: example.get(key)
        for key in (
            "label",
            "selected_evidence_count",
            "ogcf_meta_present",
            "ogcf_bridge_overload_score",
            "ogcf_effective_affected_memory_ratio",
            "ogcf_intent",
            "ordinary_fact_lookup",
            "stale_conflict",
            "shadow_actions",
            "expected_actions",
            "forbidden_actions",
            "outcome_bucket",
            "passed",
        )
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="resolver_shadow_context_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        legacy_log = tmp / "legacy.jsonl"
        adaptive_log = tmp / "adaptive.jsonl"
        write_jsonl(legacy_log, [ask_event("op_legacy_ask", adaptive=False), feedback_event("op_legacy_feedback", "op_legacy_ask")])
        write_jsonl(adaptive_log, [ask_event("op_adaptive_ask", adaptive=True), feedback_event("op_adaptive_feedback", "op_adaptive_ask")])
        legacy_examples, legacy_skipped, _legacy_sources = collect_dataset([legacy_log], 0.70, 0.50)
        adaptive_examples, adaptive_skipped, adaptive_sources = collect_dataset([adaptive_log], 0.70, 0.50)

    legacy_example = legacy_examples[0] if legacy_examples else {}
    adaptive_example = adaptive_examples[0] if adaptive_examples else {}
    checks = {
        "legacy_collected": len(legacy_examples) == 1 and not legacy_skipped,
        "adaptive_collected": len(adaptive_examples) == 1 and not adaptive_skipped,
        "adaptive_context_source": adaptive_example.get("context_source") == "adaptive_memory_context",
        "legacy_context_source": legacy_example.get("context_source") == "selector_snapshot",
        "same_semantic_fields": comparable(legacy_example) == comparable(adaptive_example),
        "adaptive_source_counted": (adaptive_sources[0].get("context_source_counts") or {}).get("adaptive_memory_context") == 1,
    }
    report = {
        "schema": "resolver_shadow_outcome_context_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "legacy_example": legacy_example,
        "adaptive_example": adaptive_example,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Outcome Context Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
