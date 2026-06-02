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

from eval.controller_packet_bridge_separator_holdout import expected_label  # noqa: E402
from eval.controller_packet_memory_bank import read_jsonl  # noqa: E402
from eval.controller_packet_ogcf_bridge_scorer import FEATURE_KEYS, vector_for  # noqa: E402


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "controller_packet_bridge_two_log_separator_holdout_packets.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_feature_audit_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_feature_audit_report.md"

REQUIRED_FEATURES = (
    "ogcf_meta_present",
    "bridge_overload_score",
    "affected_memory_ratio",
    "canonical_support_count",
    "canonical_duplicate_pressure",
    "top_retrieval_score",
    "avg_claim_scope_score",
    "avg_text_match_score",
    "query_bridge_term_score",
    "query_geometry_term_score",
    "evidence_bridge_term_score",
    "evidence_geometry_term_score",
    "evidence_noise_term_score",
)


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths or [DEFAULT_PACKETS]


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def feature_map(packet: dict[str, Any]) -> dict[str, float]:
    return {key: float(value) for key, value in zip(FEATURE_KEYS, vector_for(packet))}


def has_signal(features: dict[str, float], key: str) -> bool:
    return abs(float(features.get(key, 0.0))) > 1e-9


def build_report(packet_paths: list[Path]) -> dict[str, Any]:
    rows = []
    for path in packet_paths:
        for packet in read_jsonl(path):
            label = expected_label(packet)
            if label not in {"positive", "negative"}:
                continue
            features = feature_map(packet)
            present = [key for key in REQUIRED_FEATURES if has_signal(features, key)]
            missing = [key for key in REQUIRED_FEATURES if key not in present]
            rows.append(
                {
                    "source_packet_path": str(path),
                    "operation_id": packet.get("operation_id"),
                    "expected": label,
                    "feature_presence_count": len(present),
                    "present_features": present,
                    "missing_features": missing,
                    "features": {key: features.get(key, 0.0) for key in REQUIRED_FEATURES},
                }
            )
    labels = Counter(str(row["expected"]) for row in rows)
    coverage = {}
    for key in REQUIRED_FEATURES:
        values = [1 for row in rows if key in row["present_features"]]
        coverage[key] = {
            "present_count": len(values),
            "coverage_rate": round(len(values) / len(rows), 6) if rows else 0.0,
        }
    positive_rows = [row for row in rows if row["expected"] == "positive"]
    negative_rows = [row for row in rows if row["expected"] == "negative"]
    separability = {}
    for key in REQUIRED_FEATURES:
        pos_avg = sum(float(row["features"].get(key) or 0.0) for row in positive_rows) / len(positive_rows) if positive_rows else 0.0
        neg_avg = sum(float(row["features"].get(key) or 0.0) for row in negative_rows) / len(negative_rows) if negative_rows else 0.0
        separability[key] = {
            "positive_avg": round(pos_avg, 6),
            "negative_avg": round(neg_avg, 6),
            "absolute_gap": round(abs(pos_avg - neg_avg), 6),
        }
    strong_gaps = [key for key, item in separability.items() if float(item["absolute_gap"]) >= 0.2]
    metadata_ready = coverage.get("ogcf_meta_present", {}).get("coverage_rate") == 1.0
    enough_labels = labels.get("positive", 0) > 0 and labels.get("negative", 0) > 0
    feature_ready = bool(metadata_ready and enough_labels and len(strong_gaps) >= 2)
    blockers = []
    if not metadata_ready:
        blockers.append("ogcf_metadata_not_present_on_all_bridge_packets")
    if not enough_labels:
        blockers.append("needs_both_positive_and_negative_bridge_labels")
    if len(strong_gaps) < 2:
        blockers.append("insufficient_non_label_feature_separation")
    return {
        "schema": "controller_packet_ogcf_bridge_feature_audit/v1",
        "description": "Report-only audit of whether OGCF bridge packets preserve enough non-label context for learned scoring.",
        "ok": bool(rows),
        "packet_paths": [str(path) for path in packet_paths],
        "bridge_packet_count": len(rows),
        "label_counts": dict(sorted(labels.items())),
        "required_features": list(REQUIRED_FEATURES),
        "coverage": coverage,
        "separability": separability,
        "strong_gap_features": strong_gaps,
        "feature_ready_for_learned_scorer": feature_ready,
        "blockers": blockers,
        "examples": rows[:12],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Feature Audit",
        "",
        "This audit is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Bridge packets: `{report['bridge_packet_count']}`",
        f"Feature-ready for learned scorer: `{report['feature_ready_for_learned_scorer']}`",
        f"Strong gap features: `{', '.join(report['strong_gap_features'])}`",
        "",
        "## Blockers",
        "",
        "```json",
        json.dumps(report["blockers"], indent=2),
        "```",
        "",
        "## Coverage",
        "",
        "| feature | coverage |",
        "| --- | ---: |",
    ]
    for key, item in report["coverage"].items():
        lines.append(f"| `{key}` | `{item['coverage_rate']}` |")
    lines.extend(["", "## Separability", "", "| feature | positive avg | negative avg | gap |", "| --- | ---: | ---: | ---: |"])
    for key, item in report["separability"].items():
        lines.append(f"| `{key}` | `{item['positive_avg']}` | `{item['negative_avg']}` | `{item['absolute_gap']}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit enriched OGCF bridge packet features for learned scorer readiness.")
    parser.add_argument("--packets", action="append", help="Controller packet JSONL path. May repeat or be comma-separated.")
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(parse_paths(args.packets))
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "bridge_packet_count": report["bridge_packet_count"],
                "feature_ready_for_learned_scorer": report["feature_ready_for_learned_scorer"],
                "blockers": report["blockers"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
