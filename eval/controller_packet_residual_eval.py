from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "adaptive_residual_shadow_benefit_opportunity_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_residual_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_residual_eval_report.md"

POSITIVE_ANSWER_LABELS = {
    "answer_correct",
    "answer_good_citation",
    "answer_bridge_warning_useful",
}
NEGATIVE_ANSWER_LABELS = {
    "answer_missing_support",
    "answer_stale",
    "answer_wrong_scope",
    "answer_overconfident",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_noise",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def answer_labels(packet: dict[str, Any]) -> list[str]:
    labels = []
    for item in packet.get("feedback") or []:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "").lower()
        label = str(item.get("label") or "").lower()
        if scope == "answer" and label:
            labels.append(label)
    return labels


def expected_advisory(packet: dict[str, Any], label: str, family: str) -> str:
    evidence_count = int((packet.get("answer") or {}).get("evidence_count") or 0)
    stale_count = int((packet.get("answer") or {}).get("stale_context_count") or 0)
    state_summary = ((packet.get("evidence") or {}).get("state_summary") or {})
    has_stale = bool(state_summary.get("has_stale")) or stale_count > 0 or "stale" in label

    if family == "supported_evidence":
        if evidence_count <= 0:
            return "likely_harmful"
        if label in POSITIVE_ANSWER_LABELS:
            return "likely_helpful"
        if label in NEGATIVE_ANSWER_LABELS:
            return "likely_harmful"
    if family == "missing_support":
        if evidence_count <= 0 and label in {"answer_correct", "answer_missing_support"}:
            return "likely_helpful"
        if evidence_count > 0 and label in POSITIVE_ANSWER_LABELS:
            return "uncertain_keep_symbolic"
        if label in {"answer_missing_support", "answer_overconfident"}:
            return "likely_helpful"
    if family == "stale_conflict":
        if has_stale or label in {"answer_stale", "answer_conflict_not_disclosed"}:
            return "likely_helpful"
        return "uncertain_keep_symbolic"
    if family == "wrong_scope":
        if label == "answer_wrong_scope":
            return "likely_helpful"
        return "uncertain_keep_symbolic"
    if family == "ogcf_bridge_warning":
        if label == "answer_bridge_warning_useful":
            return "likely_helpful"
        if label == "answer_bridge_warning_noise":
            return "likely_harmful"
    return "uncertain_keep_symbolic"


def family_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        family = str(row.get("behavior_family") or "unknown")
        counters[family]["total"] += 1
        counters[family][f"expected:{row.get('expected_advisory')}"] += 1
        counters[family][f"report_only:{row.get('report_only_advisory')}"] += 1
        counters[family]["would_override"] += int(bool(row.get("would_override")))
        counters[family]["helpful_override"] += int(row.get("override_outcome") == "helpful")
        counters[family]["harmful_override"] += int(row.get("override_outcome") == "harmful")
        counters[family]["neutral_wrong_override"] += int(row.get("override_outcome") == "neutral_wrong")
    return {family: dict(sorted(counter.items())) for family, counter in sorted(counters.items())}


def compact_examples(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {
            "query": row.get("query"),
            "feedback_label": row.get("feedback_label"),
            "behavior_family": row.get("behavior_family"),
            "expected_advisory": row.get("expected_advisory"),
            "symbolic_advisory": row.get("symbolic_advisory"),
            "report_only_advisory": row.get("report_only_advisory"),
            "would_override": row.get("would_override"),
            "override_outcome": row.get("override_outcome"),
        }
        for row in rows[:limit]
    ]


def build_report(packet_path: Path) -> dict[str, Any]:
    packets = [row for row in read_jsonl(packet_path) if row.get("schema") == "controller_evidence_packet/v1"]
    rows = []
    skipped = []
    for packet in packets:
        labels = answer_labels(packet)
        if not labels:
            skipped.append({"operation_id": packet.get("operation_id"), "reason": "missing_answer_feedback"})
            continue
        residual = packet.get("adaptive_residual_shadow") if isinstance(packet.get("adaptive_residual_shadow"), dict) else {}
        decisions = [item for item in residual.get("decisions") or [] if isinstance(item, dict)]
        if not decisions:
            skipped.append({"operation_id": packet.get("operation_id"), "reason": "missing_residual_decisions"})
            continue
        for label in labels:
            for decision in decisions:
                family = str(decision.get("behavior_family") or "")
                expected = expected_advisory(packet, label, family)
                symbolic = str(decision.get("symbolic_advisory") or "")
                report_only = str(decision.get("report_only_advisory") or "")
                would = bool(decision.get("would_override"))
                outcome = "not_overridden"
                if would and report_only == expected:
                    outcome = "helpful"
                elif would and symbolic == expected and report_only != expected:
                    outcome = "harmful"
                elif would:
                    outcome = "neutral_wrong"
                rows.append(
                    {
                        "operation_id": packet.get("operation_id"),
                        "query": (packet.get("request") or {}).get("query"),
                        "feedback_label": label,
                        "behavior_family": family,
                        "expected_advisory": expected,
                        "symbolic_advisory": symbolic,
                        "report_only_advisory": report_only,
                        "would_override": would,
                        "override_outcome": outcome,
                    }
                )

    override_rows = [row for row in rows if row.get("would_override")]
    helpful = [row for row in override_rows if row.get("override_outcome") == "helpful"]
    harmful = [row for row in override_rows if row.get("override_outcome") == "harmful"]
    neutral_wrong = [row for row in override_rows if row.get("override_outcome") == "neutral_wrong"]
    mutation_flags = [
        packet.get("operation_id")
        for packet in packets
        if packet.get("mutates_runtime")
        or packet.get("mutates_config")
        or (packet.get("adaptive_residual_shadow") or {}).get("mutates_answer")
        or (packet.get("adaptive_residual_shadow") or {}).get("mutates_selector_policy")
        or (packet.get("adaptive_residual_shadow") or {}).get("mutates_memory")
        or (packet.get("adaptive_residual_shadow") or {}).get("mutates_config")
    ]
    checks = {
        "has_packets": bool(packets),
        "has_answer_feedback": any(answer_labels(packet) for packet in packets),
        "has_residual_decisions": bool(rows),
        "has_overrides": bool(override_rows),
        "has_helpful_overrides": bool(helpful),
        "zero_harmful_overrides": not harmful,
        "zero_neutral_wrong_overrides": not neutral_wrong,
        "report_only": not mutation_flags,
    }
    return {
        "schema": "controller_packet_residual_eval/v1",
        "ok": all(checks.values()),
        "packet_path": str(packet_path),
        "checks": checks,
        "packet_count": len(packets),
        "decision_count": len(rows),
        "override_count": len(override_rows),
        "helpful_override_count": len(helpful),
        "harmful_override_count": len(harmful),
        "neutral_wrong_override_count": len(neutral_wrong),
        "family_summary": family_summary(rows),
        "helpful_examples": compact_examples(helpful),
        "harmful_examples": compact_examples(harmful),
        "neutral_wrong_examples": compact_examples(neutral_wrong),
        "skipped": skipped[:20],
        "mutation_flags": mutation_flags[:20],
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Controller Packet Residual Eval\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Packet count: `{report['packet_count']}`\n"
        + f"Decision count: `{report['decision_count']}`\n"
        + f"Overrides: `{report['override_count']}` helpful `{report['helpful_override_count']}` harmful `{report['harmful_override_count']}` neutral-wrong `{report['neutral_wrong_override_count']}`\n\n"
        + "## Family Summary\n\n```json\n"
        + json.dumps(report["family_summary"], indent=2)
        + "\n```\n\n"
        + "## Helpful Examples\n\n```json\n"
        + json.dumps(report["helpful_examples"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate adaptive residual decisions from controller packets.")
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
                "packets": report["packet_count"],
                "overrides": report["override_count"],
                "helpful": report["helpful_override_count"],
                "harmful": report["harmful_override_count"],
                "json": str(args.out_json),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
