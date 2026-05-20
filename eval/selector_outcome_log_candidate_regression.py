from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import POLICY_LONG_SEVERE, POLICY_PERIODIC  # noqa: E402
from selector_outcome_log_training_eval import build_report  # noqa: E402


def ask_event(
    operation_id: str,
    *,
    policy: str,
    hard: bool,
    stale_current_conflict: float,
    memory_bad_rate: float,
    probe_drop: float,
    csd_ratio: float,
) -> dict:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": None,
        "event_type": "ask",
        "created_at": "2026-05-20T00:00:00+00:00",
        "payload": {
            "request": {
                "query": f"Regression query for {operation_id}",
                "condition_name": "hard_budget144",
                "label_cost": 0.0002,
                "budget_pressure": 0.2,
            },
            "response": {"answer": "Regression answer."},
            "selector_snapshot": {
                "ok": True,
                "decision": {
                    "policy": policy,
                    "action": "PROTECT_PERIODIC" if policy == POLICY_PERIODIC else "LONG_SEVERE_VERIFIED_REFRESH",
                    "reason": "regression_fixture",
                    "confidence": 0.9,
                },
                "diagnostics": {
                    "hard": hard,
                    "stale_current_conflict": stale_current_conflict,
                    "contradiction_peak": 0.0,
                    "memory_bad_rate": memory_bad_rate,
                    "probe_drop": probe_drop,
                    "csd_ratio": csd_ratio,
                },
            },
        },
    }


def feedback_event(operation_id: str, linked_operation_id: str, *, label: str, rating: float) -> dict:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": linked_operation_id,
        "event_type": "feedback",
        "created_at": "2026-05-20T00:01:00+00:00",
        "payload": {
            "request": {
                "label": label,
                "rating": rating,
                "linked_operation_id": linked_operation_id,
            },
            "feedback": {
                "label": label,
                "rating": rating,
                "metadata": {"linked_operation_id": linked_operation_id},
            },
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="selector_outcome_candidate_") as raw_tmp:
        tmp = Path(raw_tmp)
        log_path = tmp / "memory_outcomes.jsonl"
        rows = [
            ask_event(
                "op_positive_periodic",
                policy=POLICY_PERIODIC,
                hard=False,
                stale_current_conflict=0.0,
                memory_bad_rate=0.18,
                probe_drop=0.04,
                csd_ratio=0.75,
            ),
            feedback_event("op_feedback_positive", "op_positive_periodic", label="useful", rating=1.0),
            ask_event(
                "op_negative_hard",
                policy=POLICY_PERIODIC,
                hard=True,
                stale_current_conflict=1.0,
                memory_bad_rate=0.91,
                probe_drop=0.41,
                csd_ratio=1.6,
            ),
            feedback_event("op_feedback_negative", "op_negative_hard", label="wrong", rating=-1.0),
            ask_event(
                "op_conflict_positive",
                policy=POLICY_PERIODIC,
                hard=True,
                stale_current_conflict=1.0,
                memory_bad_rate=0.91,
                probe_drop=0.41,
                csd_ratio=1.6,
            ),
            feedback_event("op_feedback_conflict", "op_conflict_positive", label="useful", rating=1.0),
            feedback_event("op_feedback_orphan", "op_missing", label="useful", rating=1.0),
        ]
        log_path.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")
        report = build_report(log_path)

    eligible_policies = [row["policy"] for row in report["eligible_candidates"]]
    checks = {
        "events_loaded": report["event_count"] == 7,
        "observations_loaded": report["observation_count"] == 3,
        "three_candidates_seen": report["candidate_count"] == 3,
        "positive_periodic_eligible": POLICY_PERIODIC in eligible_policies,
        "hard_negative_conflict_blocked": report["conflicting_signature_count"] == 1,
        "orphan_feedback_rejected": any(row.get("reason") == "missing_linked_operation" for row in report["rejected_candidates"]),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "eligible_candidates": report["eligible_candidates"],
        "rejected_candidates": report["rejected_candidates"],
        "conflicting_signatures": report["conflicting_signatures"],
    }
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
