from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "neural_symbolic_outcome_holdout_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_answer_feedback_eval_report.md"

POSITIVE_ANSWER_LABELS = {
    "answer_correct",
    "answer_good_citation",
    "answer_bridge_warning_useful",
}
NEGATIVE_ANSWER_LABELS = {
    "answer_stale",
    "answer_wrong_scope",
    "answer_missing_support",
    "answer_overconfident",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_noise",
}
BRIDGE_WARNING_LABELS = {
    "answer_bridge_warning_useful",
    "answer_bridge_warning_noise",
}
MISSING_SUPPORT_LABELS = {
    "answer_missing_support",
    "answer_overconfident",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def family_for_label(label: str) -> str:
    if label in BRIDGE_WARNING_LABELS:
        return "bridge_warning_quality"
    if label in MISSING_SUPPORT_LABELS:
        return "missing_support_refusal"
    if label in {"answer_stale", "answer_conflict_not_disclosed"}:
        return "stale_conflict_disclosure"
    if label in {"answer_wrong_scope"}:
        return "scope_control"
    if label in {"answer_good_citation", "answer_bad_citation"}:
        return "citation_quality"
    return "answer_quality"


def recommendation_for(label: str, rating: float, packet: dict[str, Any]) -> str:
    if label not in POSITIVE_ANSWER_LABELS and label not in NEGATIVE_ANSWER_LABELS:
        return "hold_unknown_label"
    if label in BRIDGE_WARNING_LABELS:
        ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
        if not ogcf.get("meta_present") and not any(value is not None for key, value in ogcf.items() if str(key) != "meta_present"):
            return "hold_bridge_without_ogcf"
    if label in MISSING_SUPPORT_LABELS and rating < 0.0:
        return "holdout_ready"
    if rating > 0.0:
        return "holdout_ready"
    if rating < 0.0:
        return "holdout_ready"
    return "hold_neutral"


def selected_rows(packet: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(ids)
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), dict) else {}
    rows = []
    for section in ("selected", "retrieval_context"):
        for row in evidence.get(section) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("memory_id") or "") in wanted:
                rows.append(row)
    seen = set()
    unique = []
    for row in rows:
        memory_id = str(row.get("memory_id") or "")
        if memory_id in seen:
            continue
        seen.add(memory_id)
        unique.append(row)
    return unique


def signal_from_packet_feedback(packet: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    label = str(feedback.get("label") or "").strip().lower()
    try:
        rating = float(feedback.get("rating") or 0.0)
    except (TypeError, ValueError):
        rating = 0.0
    memory_ids = [str(value) for value in feedback.get("selected_memory_ids") or [] if str(value or "").strip()]
    selector = packet.get("selector") if isinstance(packet.get("selector"), dict) else {}
    decision = selector.get("decision") if isinstance(selector.get("decision"), dict) else {}
    diagnostics = selector.get("diagnostics") if isinstance(selector.get("diagnostics"), dict) else {}
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    return {
        "id": f"answer_signal_{feedback.get('operation_id')}",
        "family": family_for_label(label),
        "label": label,
        "rating": rating,
        "recommendation": recommendation_for(label, rating, packet),
        "feedback_operation_id": feedback.get("operation_id"),
        "linked_operation_id": feedback.get("linked_operation_id") or packet.get("operation_id"),
        "query": (packet.get("request") or {}).get("query"),
        "answer_preview": "",
        "selected_memory_ids": memory_ids,
        "selected_rows": selected_rows(packet, memory_ids),
        "selector_policy": decision.get("policy"),
        "selector_action": decision.get("action"),
        "ogcf_meta_present": bool(ogcf.get("meta_present")),
        "ogcf_diagnostics": {
            "ogcf_bridge_overload_score": ogcf.get("bridge_overload_score"),
            "ogcf_effective_affected_memory_ratio": ogcf.get("effective_affected_memory_ratio"),
            "ogcf_intent": ogcf.get("intent"),
            "ogcf_maintenance_pressure": ogcf.get("maintenance_pressure"),
        },
        "diagnostic_summary": {
            key: diagnostics.get(key)
            for key in (
                "memory_bad_rate",
                "probe_drop",
                "csd_ratio",
                "stale_current_conflict",
                "contradiction_peak",
                "canonical_confidence_signal",
                "canonical_duplicate_pressure",
                "ogcf_bridge_overload_score",
                "ogcf_effective_affected_memory_ratio",
                "ogcf_intent",
                "ogcf_intent_score",
            )
            if key in diagnostics
        },
    }


def build_report(packet_path: Path) -> dict[str, Any]:
    packets = [row for row in read_jsonl(packet_path) if row.get("schema") == "controller_evidence_packet/v1"]
    signals = []
    for packet in packets:
        for feedback in packet.get("feedback") or []:
            if not isinstance(feedback, dict):
                continue
            label = str(feedback.get("label") or "").strip().lower()
            scope = str(feedback.get("scope") or "").strip().lower()
            if scope == "answer" or label.startswith("answer_"):
                signals.append(signal_from_packet_feedback(packet, feedback))
    label_counts = Counter(signal["label"] for signal in signals)
    family_counts = Counter(signal["family"] for signal in signals)
    recommendation_counts = Counter(signal["recommendation"] for signal in signals)
    checks = {
        "packets_exist": bool(packets),
        "has_answer_feedback": bool(signals),
        "all_answer_feedback_linked": all(signal.get("linked_operation_id") for signal in signals),
        "has_positive_answer_signal": any(float(signal.get("rating") or 0.0) > 0.0 for signal in signals),
        "has_negative_answer_signal": any(float(signal.get("rating") or 0.0) < 0.0 for signal in signals),
        "bridge_signal_has_ogcf": any(
            signal["family"] == "bridge_warning_quality" and signal["ogcf_meta_present"] and signal["ogcf_diagnostics"]
            for signal in signals
        ),
        "missing_support_signal_present": any(signal["family"] == "missing_support_refusal" for signal in signals),
    }
    return {
        "schema": "answer_feedback_controller_signals/v1",
        "description": "Report-only answer-level feedback signals collected from controller evidence packets.",
        "ok": all(checks.values()),
        "source_packets": str(packet_path),
        "packet_count": len(packets),
        "answer_feedback_count": len(signals),
        "signal_count": len(signals),
        "checks": checks,
        "label_counts": dict(sorted(label_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "signals": signals,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Controller Packet Answer Feedback Eval\n\n"
        + "This report is advisory only. It does not promote runtime config or learned policy artifacts.\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Source packets: `{report['source_packets']}`\n"
        + f"Answer feedback events: `{report['answer_feedback_count']}`\n"
        + f"Signals: `{report['signal_count']}`\n\n"
        + "## Counts\n\n```json\n"
        + json.dumps(
            {
                "labels": report["label_counts"],
                "families": report["family_counts"],
                "recommendations": report["recommendation_counts"],
            },
            indent=2,
        )
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse packet answer-level feedback into report-only controller signals.")
    parser.add_argument("--packets", type=Path, default=DEFAULT_PACKETS)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.packets)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "answer_feedback_count": report["answer_feedback_count"],
                "signal_count": report["signal_count"],
                "family_counts": report["family_counts"],
                "recommendation_counts": report["recommendation_counts"],
                "json": str(args.out_json),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
