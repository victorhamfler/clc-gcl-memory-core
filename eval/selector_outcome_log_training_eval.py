from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCPolicyFeatures,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from core.config import load_config, resolve_project_path  # noqa: E402


DEFAULT_OUT_JSON = REPO_ROOT / "experiments" / "selector_outcome_log_training_eval_results.json"
DEFAULT_OUT_MD = REPO_ROOT / "experiments" / "selector_outcome_log_training_eval_report.md"
POLICIES = {POLICY_PERIODIC, POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}
POSITIVE_LABELS = {"accepted", "correct", "good", "helpful", "useful"}
NEGATIVE_LABELS = {"bad", "incomplete", "incorrect", "stale", "wrong"}


def default_log_path() -> Path:
    config = load_config(ROOT)
    cfg = config.get("outcome_log") if isinstance(config.get("outcome_log"), dict) else {}
    return resolve_project_path(ROOT, cfg.get("path"), "logs/memory_outcomes.jsonl")


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            events.append(
                {
                    "schema_version": 0,
                    "operation_id": f"parse_error_{line_no}",
                    "event_type": "parse_error",
                    "payload": {"line_no": line_no, "error": str(exc)},
                }
            )
            continue
        events.append(row)
    return events


def selector_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if event.get("event_type") == "ask":
        return payload.get("selector_snapshot") if isinstance(payload.get("selector_snapshot"), dict) else {}
    if event.get("event_type") == "selector_explain":
        explanation = payload.get("explanation") if isinstance(payload.get("explanation"), dict) else {}
        context = payload.get("selector_context") if isinstance(payload.get("selector_context"), dict) else {}
        return {
            "ok": True,
            "decision": explanation.get("decision") or {},
            "diagnostics": context.get("diagnostics") or {},
            "features": explanation.get("features") or {},
        }
    return {}


def features_from_event(event: dict[str, Any]) -> CLCPolicyFeatures | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    selector = selector_payload(event)
    diagnostics = selector.get("diagnostics") if isinstance(selector.get("diagnostics"), dict) else {}
    explanation_features = selector.get("features") if isinstance(selector.get("features"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    condition_name = str(request.get("condition_name") or explanation_features.get("condition_name") or "hard_budget144")
    if explanation_features:
        try:
            return CLCPolicyFeatures(
                budget_units=float(explanation_features.get("budget_units", 144.0) or 144.0),
                cycles=float(explanation_features.get("cycles", 1.0) or 1.0),
                hard=bool(explanation_features.get("hard", False)),
                long_stream=bool(explanation_features.get("long_stream", False)),
                csd_ratio=float(explanation_features.get("csd_ratio", 0.0) or 0.0),
                probe_drop=float(explanation_features.get("probe_drop", 0.0) or 0.0),
                label_cost=float(explanation_features.get("label_cost", 0.0002) or 0.0002),
                budget_pressure=float(explanation_features.get("budget_pressure", 0.0) or 0.0),
                recent_return_mean=float(explanation_features.get("recent_return_mean", 0.0) or 0.0),
                memory_bad_rate=float(explanation_features.get("memory_bad_rate", 0.0) or 0.0),
            )
        except (TypeError, ValueError):
            return None
    if not diagnostics:
        return None
    try:
        condition_l = condition_name.lower()
        long_stream = "long" in condition_l or "long2" in condition_l
        return CLCPolicyFeatures(
            budget_units=288.0 if long_stream else 144.0,
            cycles=2.0 if long_stream else 1.0,
            hard=bool(diagnostics.get("hard", False)),
            long_stream=long_stream,
            memory_bad_rate=float(diagnostics.get("memory_bad_rate", 0.0) or 0.0),
            probe_drop=float(diagnostics.get("probe_drop", 0.0) or 0.0),
            csd_ratio=float(diagnostics.get("csd_ratio", 0.0) or 0.0),
            label_cost=float(request.get("label_cost", 0.0002) or 0.0002),
            budget_pressure=float(request.get("budget_pressure", 0.2) or 0.2),
            recent_return_mean=0.0,
        )
    except (TypeError, ValueError):
        return None


def decision_policy(event: dict[str, Any]) -> str | None:
    selector = selector_payload(event)
    decision = selector.get("decision") if isinstance(selector.get("decision"), dict) else {}
    policy = str(decision.get("policy") or "").strip()
    return policy if policy in POLICIES else None


def memory_state_for_feedback(source_event: dict[str, Any], memory_id: str | None) -> str:
    if not memory_id:
        return "unknown"
    payload = source_event.get("payload") if isinstance(source_event.get("payload"), dict) else {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    for section in ("evidence", "stale_context", "raw_results", "source_context"):
        for row in response.get(section) or []:
            if str(row.get("memory_id") or "") != memory_id:
                continue
            state = str(row.get("authority_state") or row.get("memory_state") or "").lower()
            if state:
                return state
    return "unknown"


def feedback_signal(event: dict[str, Any], source_event: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    feedback = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else {}
    label = str(request.get("label") or feedback.get("label") or "").strip().lower()
    memory_id = str(request.get("memory_id") or feedback.get("memory_id") or "").strip() or None
    try:
        rating = float(request.get("rating", feedback.get("rating", 0.0)) or 0.0)
    except (TypeError, ValueError):
        rating = 0.0
    memory_state = memory_state_for_feedback(source_event, memory_id) if source_event else "unknown"
    if label == "stale" and memory_state in {"stale", "superseded"}:
        return {"kind": "evidence_stale_annotation", "label": label, "rating": rating, "memory_id": memory_id}
    if label in POSITIVE_LABELS or rating >= 0.5:
        return {"kind": "positive", "label": label, "rating": rating, "memory_id": memory_id}
    if label in NEGATIVE_LABELS or rating <= -0.5:
        return {"kind": "negative", "label": label, "rating": rating, "memory_id": memory_id}
    return {"kind": "unclear", "label": label, "rating": rating, "memory_id": memory_id}


def suggested_policy(source_event: dict[str, Any], feedback: dict[str, Any]) -> tuple[str | None, str]:
    observed_policy = decision_policy(source_event)
    if feedback["kind"] == "positive":
        return observed_policy, "positive_feedback_keep_observed_policy"
    if feedback["kind"] == "evidence_stale_annotation":
        return None, "evidence_stale_annotation_not_selector_label"
    if feedback["kind"] != "negative":
        return None, "unclear_feedback"
    selector = selector_payload(source_event)
    diagnostics = selector.get("diagnostics") if isinstance(selector.get("diagnostics"), dict) else {}
    if bool(diagnostics.get("hard")) or float(diagnostics.get("stale_current_conflict") or 0.0) >= 0.8:
        return POLICY_LONG_SEVERE, "negative_feedback_hard_or_stale_conflict"
    if float(diagnostics.get("contradiction_peak") or 0.0) >= 0.5:
        return POLICY_LONG_SEVERE, "negative_feedback_contradiction"
    return None, "negative_feedback_without_selector_signal"


def feature_signature(features: CLCPolicyFeatures) -> str:
    values = asdict(features)
    rounded = {
        key: (round(float(value), 3) if isinstance(value, (float, int)) and not isinstance(value, bool) else value)
        for key, value in values.items()
    }
    return json.dumps(rounded, sort_keys=True, separators=(",", ":"))


def observation_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    features = features_from_event(event)
    if features is None:
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    selector = selector_payload(event)
    return {
        "operation_id": event.get("operation_id"),
        "event_type": event.get("event_type"),
        "query": request.get("query"),
        "policy": decision_policy(event),
        "features": asdict(features),
        "diagnostics": selector.get("diagnostics") or {},
    }


def build_report(log_path: Path) -> dict[str, Any]:
    events = load_events(log_path)
    by_operation = {str(event.get("operation_id")): event for event in events if event.get("operation_id")}
    feedback_events = [event for event in events if event.get("event_type") == "feedback"]
    observations = [item for event in events if (item := observation_from_event(event)) is not None]
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for feedback_event in feedback_events:
        linked_id = str(feedback_event.get("linked_operation_id") or "").strip()
        source_event = by_operation.get(linked_id)
        if source_event is None:
            signal = feedback_signal(feedback_event)
            rejected.append(
                {
                    "feedback_operation_id": feedback_event.get("operation_id"),
                    "linked_operation_id": linked_id or None,
                    "reason": "missing_linked_operation",
                    "feedback": signal,
                }
            )
            continue
        signal = feedback_signal(feedback_event, source_event)
        features = features_from_event(source_event)
        policy, reason = suggested_policy(source_event, signal)
        if features is None or policy is None:
            rejected.append(
                {
                    "feedback_operation_id": feedback_event.get("operation_id"),
                    "linked_operation_id": linked_id,
                    "reason": reason if policy is None else "missing_features",
                    "feedback": signal,
                }
            )
            continue
        candidates.append(
            {
                "source_operation_id": linked_id,
                "feedback_operation_id": feedback_event.get("operation_id"),
                "event_type": source_event.get("event_type"),
                "policy": policy,
                "reason": reason,
                "feedback": signal,
                "features": asdict(features),
                "signature": feature_signature(features),
            }
        )

    policies_by_signature: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        policies_by_signature[candidate["signature"]].add(candidate["policy"])
    conflicts = {
        signature: sorted(policies)
        for signature, policies in policies_by_signature.items()
        if len(policies) > 1
    }
    eligible = [
        candidate
        for candidate in candidates
        if candidate["signature"] not in conflicts
    ]
    return {
        "ok": True,
        "purpose": "Dry-run parser for real memory outcome logs into selector training candidates.",
        "log_path": str(log_path),
        "event_count": len(events),
        "event_type_counts": dict(sorted({kind: sum(1 for event in events if event.get("event_type") == kind) for kind in {event.get("event_type") for event in events}}.items())),
        "observation_count": len(observations),
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "rejected_count": len(rejected),
        "conflicting_signature_count": len(conflicts),
        "observations": observations[:50],
        "eligible_candidates": eligible,
        "rejected_candidates": rejected,
        "conflicting_signatures": conflicts,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Outcome Log Training Eval",
        "",
        f"Log path: `{report['log_path']}`",
        f"Events: **{report['event_count']}**",
        f"Observations: **{report['observation_count']}**",
        f"Candidates: **{report['candidate_count']}**",
        f"Eligible candidates: **{report['eligible_candidate_count']}**",
        f"Rejected candidates: **{report['rejected_count']}**",
        f"Conflicting signatures: **{report['conflicting_signature_count']}**",
        "",
        "## Event Counts",
        "",
    ]
    if not report["event_type_counts"]:
        lines.append("- No events found.")
    for event_type, count in report["event_type_counts"].items():
        lines.append(f"- `{event_type}`: {count}")
    lines.extend(["", "## Eligible Candidates", ""])
    if not report["eligible_candidates"]:
        lines.append("- None yet. This is expected until linked feedback accumulates.")
    for candidate in report["eligible_candidates"]:
        lines.append(
            f"- `{candidate['policy']}` from `{candidate['source_operation_id']}` "
            f"via `{candidate['feedback']['label']}` rating `{candidate['feedback']['rating']}`."
        )
    lines.extend(["", "## Rejections", ""])
    if not report["rejected_candidates"]:
        lines.append("- None")
    for candidate in report["rejected_candidates"][:20]:
        lines.append(
            f"- `{candidate.get('feedback_operation_id')}` rejected: `{candidate.get('reason')}`."
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run selector training candidate builder from memory outcome logs.")
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    log_path = args.log_path or default_log_path()
    report = build_report(log_path)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "log_path": report["log_path"],
                "event_count": report["event_count"],
                "observation_count": report["observation_count"],
                "candidate_count": report["candidate_count"],
                "eligible_candidate_count": report["eligible_candidate_count"],
                "rejected_count": report["rejected_count"],
                "conflicting_signature_count": report["conflicting_signature_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
