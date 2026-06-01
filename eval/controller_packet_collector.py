from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.controller_packet import SCHEMA, build_controller_evidence_packet  # noqa: E402


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_benefit_opportunity_outcomes.jsonl"
OUT_JSONL = REPO_ROOT / "experiments" / "controller_evidence_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_collector_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_collector_report.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def linked_operation_id(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    feedback = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    return str(
        event.get("linked_operation_id")
        or feedback.get("linked_operation_id")
        or request.get("linked_operation_id")
        or request.get("operation_id")
        or ""
    )


def embedded_packet(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    packet = payload.get("controller_evidence_packet")
    if isinstance(packet, dict) and packet.get("schema") == SCHEMA:
        return dict(packet)
    return None


def collect_packets(log_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packets = []
    skipped = []
    for log_path in log_paths:
        rows = read_jsonl(log_path)
        asks = [
            row
            for row in rows
            if row.get("event_type") == "ask" and row.get("operation_id")
        ]
        feedback_by_link: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("event_type") != "feedback":
                continue
            linked = linked_operation_id(row)
            if linked:
                feedback_by_link[linked].append(row)
        if not asks:
            skipped.append({"log": str(log_path), "reason": "no_ask_events"})
            continue
        for ask in asks:
            op_id = str(ask.get("operation_id") or "")
            linked_feedback = feedback_by_link.get(op_id, [])
            if linked_feedback:
                packet = build_controller_evidence_packet(ask, linked_feedback)
            else:
                packet = embedded_packet(ask) or build_controller_evidence_packet(ask, [])
            packet["source_log"] = str(log_path)
            packets.append(packet)
    return packets, skipped


def summarize(packets: list[dict[str, Any]], skipped: list[dict[str, Any]], log_paths: list[Path]) -> dict[str, Any]:
    answer_feedback = sum(1 for packet in packets if packet.get("feedback_summary", {}).get("has_answer_feedback"))
    memory_feedback = sum(1 for packet in packets if packet.get("feedback_summary", {}).get("has_memory_feedback"))
    residual_present = sum(1 for packet in packets if packet.get("adaptive_residual_shadow", {}).get("present"))
    would_overrides = sum(int(packet.get("adaptive_residual_shadow", {}).get("would_override_count") or 0) for packet in packets)
    ogcf_present = sum(1 for packet in packets if packet.get("ogcf", {}).get("meta_present"))
    evidence_positive = sum(1 for packet in packets if int(packet.get("answer", {}).get("evidence_count") or 0) > 0)
    return {
        "schema": "controller_packet_collector/v1",
        "ok": bool(packets),
        "logs": [str(path) for path in log_paths],
        "packet_count": len(packets),
        "answer_feedback_packets": answer_feedback,
        "memory_feedback_packets": memory_feedback,
        "residual_shadow_packets": residual_present,
        "residual_would_override_count": would_overrides,
        "ogcf_meta_packets": ogcf_present,
        "evidence_positive_packets": evidence_positive,
        "skipped": skipped[:20],
    }


def write_outputs(packets: list[dict[str, Any]], report: dict[str, Any], out_jsonl: Path, out_json: Path, out_md: Path) -> None:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.write_text(
        "\n".join(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) for packet in packets)
        + ("\n" if packets else ""),
        encoding="utf-8",
    )
    out_json.write_text(json.dumps({**report, "packet_jsonl": str(out_jsonl)}, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Collector",
        "",
        f"Passed: **{report['ok']}**",
        f"Packets: `{report['packet_count']}`",
        f"Evidence-positive packets: `{report['evidence_positive_packets']}`",
        f"Answer-feedback packets: `{report['answer_feedback_packets']}`",
        f"Memory-feedback packets: `{report['memory_feedback_packets']}`",
        f"Residual-shadow packets: `{report['residual_shadow_packets']}`",
        f"Residual would-overrides: `{report['residual_would_override_count']}`",
        f"Output JSONL: `{out_jsonl}`",
        "",
        "## Logs",
        "",
    ]
    for path in report["logs"]:
        lines.append(f"- `{path}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_paths(values: list[str] | None) -> list[Path]:
    if not values:
        return [DEFAULT_LOG]
    return [Path(value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect controller_evidence_packet/v1 rows from outcome logs.")
    parser.add_argument("--log", action="append", help="Outcome JSONL log. Can be passed multiple times.")
    parser.add_argument("--out-jsonl", type=Path, default=OUT_JSONL)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    log_paths = parse_paths(args.log)
    packets, skipped = collect_packets(log_paths)
    report = summarize(packets, skipped, log_paths)
    write_outputs(packets, report, args.out_jsonl, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "packet_count": report["packet_count"], "jsonl": str(args.out_jsonl)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
