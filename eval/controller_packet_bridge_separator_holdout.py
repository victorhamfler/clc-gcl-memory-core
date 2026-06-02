from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.controller_packet_memory_bank import read_jsonl  # noqa: E402


DEFAULT_SEPARATOR = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_results.json"
DEFAULT_PACKETS = REPO_ROOT / "experiments" / "controller_evidence_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_holdout_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return loaded


def labels(packet: dict[str, Any]) -> set[str]:
    summary = packet.get("feedback_summary") if isinstance(packet.get("feedback_summary"), dict) else {}
    raw = summary.get("labels") if isinstance(summary.get("labels"), dict) else {}
    return {str(label).strip().lower() for label in raw if str(label).strip()}


def intent(packet: dict[str, Any]) -> str:
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    return str(ogcf.get("intent") or "unknown").strip().lower() or "unknown"


def has_ogcf(packet: dict[str, Any]) -> bool:
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    return bool(ogcf.get("meta_present"))


def expected_label(packet: dict[str, Any]) -> str | None:
    packet_labels = labels(packet)
    if "answer_bridge_warning_useful" in packet_labels or "bridge_relevant" in packet_labels:
        return "positive"
    if "answer_bridge_warning_noise" in packet_labels or "ogcf_false_positive" in packet_labels:
        return "negative"
    return None


def rule_prediction(separator: dict[str, Any], packet: dict[str, Any]) -> str:
    rule = separator.get("rule") if isinstance(separator.get("rule"), dict) else {}
    positive = rule.get("positive_when") if isinstance(rule.get("positive_when"), dict) else {}
    negative = rule.get("negative_when") if isinstance(rule.get("negative_when"), dict) else {}
    packet_intent = intent(packet)
    packet_labels = labels(packet)
    if positive.get("ogcf_meta_present") and not has_ogcf(packet):
        return "abstain"
    if negative.get("ogcf_meta_present") and not has_ogcf(packet):
        return "abstain"
    positive_intents = {str(item).lower() for item in positive.get("intent_in") or []}
    negative_intents = {str(item).lower() for item in negative.get("intent_in") or []}
    positive_labels = {str(item).lower() for item in positive.get("feedback_label_in") or []}
    negative_labels = {str(item).lower() for item in negative.get("feedback_label_in") or []}
    positive_match = (not positive_intents or packet_intent in positive_intents) and bool(packet_labels & positive_labels)
    negative_match = (not negative_intents or packet_intent in negative_intents) and bool(packet_labels & negative_labels)
    if positive_match and not negative_match:
        return "positive"
    if negative_match and not positive_match:
        return "negative"
    if positive_match and negative_match:
        return "conflict"
    return "abstain"


def build_report(separator_path: Path, packet_paths: list[Path]) -> dict[str, Any]:
    separator_artifact = read_json(separator_path)
    separators = [item for item in separator_artifact.get("separators") or [] if isinstance(item, dict)]
    packets = []
    for path in packet_paths:
        packets.extend(read_jsonl(path))
    bridge_packets = [packet for packet in packets if expected_label(packet)]
    rows = []
    for separator in separators:
        for packet in bridge_packets:
            expected = expected_label(packet)
            predicted = rule_prediction(separator, packet)
            rows.append(
                {
                    "separator_id": separator.get("id"),
                    "operation_id": packet.get("operation_id"),
                    "intent": intent(packet),
                    "labels": sorted(labels(packet)),
                    "expected": expected,
                    "predicted": predicted,
                    "match": predicted == expected,
                }
            )
    scored = [row for row in rows if row["predicted"] in {"positive", "negative"}]
    false_positive = [row for row in scored if row["expected"] == "negative" and row["predicted"] == "positive"]
    false_negative = [row for row in scored if row["expected"] == "positive" and row["predicted"] == "negative"]
    match_count = sum(1 for row in scored if row["match"])
    match_rate = round(match_count / len(scored), 6) if scored else 0.0
    return {
        "schema": "controller_packet_bridge_separator_holdout/v1",
        "description": "Report-only replay of OGCF bridge separator candidates against packet holdout data.",
        "ok": bool(separators) and bool(scored) and not false_positive and not false_negative,
        "source_separator": str(separator_path),
        "packet_paths": [str(path) for path in packet_paths],
        "separator_count": len(separators),
        "packet_count": len(packets),
        "bridge_packet_count": len(bridge_packets),
        "scored_count": len(scored),
        "abstain_count": len(rows) - len(scored),
        "match_rate": match_rate,
        "false_positive_count": len(false_positive),
        "false_negative_count": len(false_negative),
        "promotion_ready": False,
        "promotion_blocker": "report-only holdout replay; requires broader unseen real logs before runtime use",
        "examples": rows[:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Bridge Separator Holdout",
        "",
        "This replay is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Bridge packets: `{report['bridge_packet_count']}`",
        f"Scored packets: `{report['scored_count']}`",
        f"Match rate: `{report['match_rate']}`",
        f"False positives: `{report['false_positive_count']}`",
        f"False negatives: `{report['false_negative_count']}`",
        f"Promotion ready: `{report['promotion_ready']}`",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay bridge separator candidates on packet holdout data.")
    parser.add_argument("--separator", type=Path, default=DEFAULT_SEPARATOR)
    parser.add_argument("--packets", type=Path, action="append", default=None)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.separator, args.packets or [DEFAULT_PACKETS])
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "bridge_packet_count": report["bridge_packet_count"],
                "scored_count": report["scored_count"],
                "match_rate": report["match_rate"],
                "json": str(args.out_json),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
