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

from core.controller_packet import SCHEMA  # noqa: E402


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "controller_evidence_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_memory_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_memory_bank_report.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            packet = value.get("controller_evidence_packet")
            if isinstance(packet, dict):
                value = packet
            if value.get("schema") == SCHEMA:
                rows.append(value)
    return rows


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths or [DEFAULT_PACKETS]


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split()) or "unknown"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def packet_key(packet: dict[str, Any]) -> str:
    selector = packet.get("selector") if isinstance(packet.get("selector"), dict) else {}
    decision = selector.get("decision") if isinstance(selector.get("decision"), dict) else {}
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    answer = packet.get("answer") if isinstance(packet.get("answer"), dict) else {}
    feedback = packet.get("feedback_summary") if isinstance(packet.get("feedback_summary"), dict) else {}
    residual = packet.get("adaptive_residual_shadow") if isinstance(packet.get("adaptive_residual_shadow"), dict) else {}
    labels = feedback.get("labels") if isinstance(feedback.get("labels"), dict) else {}
    label_key = ",".join(sorted(norm(key) for key in labels)) or "unlabeled"
    return "|".join(
        [
            f"selector={norm(decision.get('policy') or decision.get('action'))}",
            f"ogcf={norm(ogcf.get('intent'))}",
            f"conflict={bool(answer.get('conflict'))}",
            f"residual={int(residual.get('would_override_count') or 0)}",
            f"labels={label_key}",
        ]
    )


def readiness_for_cluster(packets: list[dict[str, Any]], *, ready_support: int, ready_logs: int) -> str:
    labels = Counter()
    for packet in packets:
        summary = packet.get("feedback_summary") if isinstance(packet.get("feedback_summary"), dict) else {}
        packet_labels = summary.get("labels") if isinstance(summary.get("labels"), dict) else {}
        labels.update({norm(label): int(count or 0) for label, count in packet_labels.items()})
    negative = sum(
        count
        for label, count in labels.items()
        if any(
            term in label
            for term in (
                "wrong",
                "bad",
                "stale",
                "missing",
                "overconfident",
                "noise",
                "irrelevant",
                "false_positive",
            )
        )
    )
    positive = sum(count for label, count in labels.items() if count > 0) - negative
    source_logs = {str(packet.get("source_log") or "") for packet in packets if packet.get("source_log")}
    if negative and positive:
        return "review_mixed_feedback"
    if negative:
        return "review_negative_feedback"
    if len(packets) >= ready_support and len(source_logs) >= ready_logs:
        return "calibration_candidate"
    return "hold_collect_more"


def has_bridge_label(labels: Counter[str]) -> bool:
    return any("bridge" in str(label) for label in labels)


def has_ogcf_metadata(packet: dict[str, Any]) -> bool:
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    return bool(ogcf.get("meta_present"))


def evidence_context_features(packet: dict[str, Any]) -> dict[str, Any]:
    context = packet.get("evidence_context") if isinstance(packet.get("evidence_context"), dict) else {}
    features = context.get("features") if isinstance(context.get("features"), dict) else {}
    return features


def freeze_cluster(key: str, packets: list[dict[str, Any]], *, ready_support: int, ready_logs: int) -> dict[str, Any]:
    selector_policies = Counter()
    ogcf_intents = Counter()
    labels = Counter()
    resolver_actions = Counter()
    residual_families = Counter()
    source_logs = set()
    examples = []
    ogcf_meta_count = 0
    evidence_context_feature_count = 0
    evidence_context_feature_keys = Counter()
    for packet in packets:
        source_logs.add(str(packet.get("source_log") or "runtime_packet"))
        selector = packet.get("selector") if isinstance(packet.get("selector"), dict) else {}
        decision = selector.get("decision") if isinstance(selector.get("decision"), dict) else {}
        selector_policies[norm(decision.get("policy") or decision.get("action"))] += 1
        ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
        if has_ogcf_metadata(packet):
            ogcf_meta_count += 1
        features = evidence_context_features(packet)
        if features:
            evidence_context_feature_count += 1
            evidence_context_feature_keys.update(str(key) for key in features)
        ogcf_intents[norm(ogcf.get("intent"))] += 1
        feedback = packet.get("feedback_summary") if isinstance(packet.get("feedback_summary"), dict) else {}
        packet_labels = feedback.get("labels") if isinstance(feedback.get("labels"), dict) else {}
        labels.update({norm(label): int(count or 0) for label, count in packet_labels.items()})
        resolver = packet.get("resolver_shadow") if isinstance(packet.get("resolver_shadow"), dict) else {}
        resolver_actions.update(norm(action) for action in resolver.get("actions") or [])
        residual = packet.get("adaptive_residual_shadow") if isinstance(packet.get("adaptive_residual_shadow"), dict) else {}
        for decision_item in residual.get("decisions") or []:
            if isinstance(decision_item, dict):
                residual_families[norm(decision_item.get("behavior_family"))] += 1
        if len(examples) < 5:
            request = packet.get("request") if isinstance(packet.get("request"), dict) else {}
            answer = packet.get("answer") if isinstance(packet.get("answer"), dict) else {}
            examples.append(
                {
                    "operation_id": packet.get("operation_id"),
                    "query": request.get("query"),
                    "confidence": answer.get("confidence"),
                    "conflict": answer.get("conflict"),
                    "evidence_count": answer.get("evidence_count"),
                }
            )
    return {
        "key": key,
        "support": len(packets),
        "source_log_count": len(source_logs),
        "readiness": readiness_for_cluster(packets, ready_support=ready_support, ready_logs=ready_logs),
        "selector_policies": dict(sorted(selector_policies.items())),
        "ogcf_intents": dict(sorted(ogcf_intents.items())),
        "feedback_labels": dict(sorted(labels.items())),
        "bridge_label_without_ogcf": has_bridge_label(labels) and ogcf_meta_count == 0,
        "ogcf_meta_count": ogcf_meta_count,
        "evidence_context_feature_count": evidence_context_feature_count,
        "evidence_context_feature_coverage": round(evidence_context_feature_count / max(1, len(packets)), 6),
        "evidence_context_feature_keys": sorted(evidence_context_feature_keys),
        "resolver_actions": dict(sorted(resolver_actions.items())),
        "residual_families": dict(sorted(residual_families.items())),
        "examples": examples,
    }


def build_report(packet_paths: list[Path], *, ready_support: int = 2, ready_logs: int = 1) -> dict[str, Any]:
    packets: list[dict[str, Any]] = []
    artifacts = []
    for path in packet_paths:
        rows = read_jsonl(path)
        artifacts.append({"path": str(path), "packet_count": len(rows)})
        for row in rows:
            item = dict(row)
            item.setdefault("source_log", str(path))
            packets.append(item)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for packet in packets:
        grouped[packet_key(packet)].append(packet)
    clusters = [
        freeze_cluster(key, rows, ready_support=max(1, ready_support), ready_logs=max(1, ready_logs))
        for key, rows in sorted(grouped.items())
    ]
    readiness = Counter(cluster["readiness"] for cluster in clusters)
    feedback_packets = sum(1 for packet in packets if (packet.get("feedback_summary") or {}).get("count"))
    residual_packets = sum(1 for packet in packets if (packet.get("adaptive_residual_shadow") or {}).get("present"))
    ogcf_packets = sum(1 for packet in packets if (packet.get("ogcf") or {}).get("meta_present"))
    evidence_context_feature_packets = sum(1 for packet in packets if evidence_context_features(packet))
    evidence_context_feature_keys = sorted(
        {
            str(key)
            for packet in packets
            for key in evidence_context_features(packet)
        }
    )
    bridge_feedback_packets = 0
    bridge_feedback_without_ogcf = 0
    for packet in packets:
        summary = packet.get("feedback_summary") if isinstance(packet.get("feedback_summary"), dict) else {}
        labels = summary.get("labels") if isinstance(summary.get("labels"), dict) else {}
        if any("bridge" in norm(label) for label in labels):
            bridge_feedback_packets += 1
            if not has_ogcf_metadata(packet):
                bridge_feedback_without_ogcf += 1
    return {
        "schema": "controller_packet_memory_bank/v1",
        "description": "Report-only aggregation of controller evidence packets for calibration candidate discovery.",
        "ok": bool(packets) and bool(clusters),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "packet_count": len(packets),
        "cluster_count": len(clusters),
        "feedback_packet_count": feedback_packets,
        "residual_packet_count": residual_packets,
        "ogcf_packet_count": ogcf_packets,
        "evidence_context_feature_packet_count": evidence_context_feature_packets,
        "evidence_context_feature_coverage": round(evidence_context_feature_packets / max(1, len(packets)), 6),
        "evidence_context_feature_keys": evidence_context_feature_keys,
        "bridge_feedback_packet_count": bridge_feedback_packets,
        "bridge_feedback_without_ogcf_count": bridge_feedback_without_ogcf,
        "diagnostics": {
            "bridge_feedback_without_ogcf": bridge_feedback_without_ogcf,
            "bridge_feedback_has_ogcf_coverage": bridge_feedback_packets == 0 or bridge_feedback_without_ogcf == 0,
            "evidence_context_features_present": evidence_context_feature_packets > 0,
            "evidence_context_features_full_coverage": evidence_context_feature_packets == len(packets),
        },
        "ready_thresholds": {"support": max(1, ready_support), "source_logs": max(1, ready_logs)},
        "readiness_counts": dict(sorted(readiness.items())),
        "clusters": clusters,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Memory Bank",
        "",
        "This report is advisory only. It does not mutate memory, selector policy, resolver policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Packets: `{report['packet_count']}`",
        f"Clusters: `{report['cluster_count']}`",
        "",
        "## Readiness Counts",
        "",
        "```json",
        json.dumps(report["readiness_counts"], indent=2),
        "```",
        "",
        "## Clusters",
        "",
        "| readiness | support | logs | labels | selector | ogcf | examples |",
        "| --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for cluster in report["clusters"]:
        examples = "; ".join(str(item.get("query") or "") for item in cluster["examples"][:2])
        lines.append(
            "| `{}` | {} | {} | `{}` | `{}` | `{}` | {} |".format(
                cluster["readiness"],
                cluster["support"],
                cluster["source_log_count"],
                clean_cell(", ".join(cluster["feedback_labels"].keys())),
                clean_cell(", ".join(cluster["selector_policies"].keys())),
                clean_cell(", ".join(cluster["ogcf_intents"].keys())),
                clean_cell(examples),
            )
        )
    lines.extend(["", "## Artifacts", ""])
    for artifact in report["artifacts"]:
        lines.append(f"- `{artifact['path']}`: `{artifact['packet_count']}` packets")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate controller_evidence_packet/v1 JSONL files.")
    parser.add_argument("--packets", action="append", help="Controller packet JSONL path. May repeat.")
    parser.add_argument("--ready-support", type=int, default=2)
    parser.add_argument("--ready-logs", type=int, default=1)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    paths = parse_paths(args.packets)
    report = build_report(paths, ready_support=args.ready_support, ready_logs=args.ready_logs)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "packet_count": report["packet_count"],
                "cluster_count": report["cluster_count"],
                "readiness_counts": report["readiness_counts"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
