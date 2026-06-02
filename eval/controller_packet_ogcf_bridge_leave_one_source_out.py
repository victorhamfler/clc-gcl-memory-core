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
from eval.controller_packet_ogcf_bridge_scorer import (  # noqa: E402
    FEATURE_KEYS,
    bridge_samples,
    read_json,
    score_rows,
    train_logistic,
)
from eval.controller_packet_ogcf_bridge_source_holdout import rows_for_samples  # noqa: E402
from core.config import load_config  # noqa: E402
from core.controller_packet_calibration import normalize_bridge_loso_policy  # noqa: E402


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "controller_packet_bridge_two_log_separator_holdout_packets.jsonl"
DEFAULT_SEPARATOR = REPO_ROOT / "experiments" / "controller_packet_bridge_two_log_separator_holdout_bridge_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_leave_one_source_out_report.md"


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def source_key(sample: dict[str, Any]) -> str:
    packet = sample.get("packet") if isinstance(sample.get("packet"), dict) else {}
    return str(packet.get("source_log") or sample.get("source_packet_path") or "unknown")


def write_source_packet_files(packet_paths: list[Path], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in packet_paths:
        for packet in read_jsonl(path):
            key = str(packet.get("source_log") or path)
            grouped.setdefault(key, []).append(packet)
    source_paths: dict[str, Path] = {}
    for idx, (key, packets) in enumerate(sorted(grouped.items()), start=1):
        out_path = out_dir / f"source_{idx:03d}.jsonl"
        out_path.write_text(
            "\n".join(json.dumps(packet, separators=(",", ":")) for packet in packets) + "\n",
            encoding="utf-8",
        )
        source_paths[key] = out_path
    return source_paths


def build_report(
    packet_paths: list[Path],
    separator_path: Path | None = None,
    *,
    temp_dir: Path | None = None,
    min_sources: int | None = None,
    min_samples: int | None = None,
    policy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = normalize_bridge_loso_policy(policy_config, min_sources=min_sources, min_samples=min_samples)
    min_sources = int(policy["min_sources_for_candidate"])
    min_samples = int(policy["min_samples_for_candidate"])
    samples = bridge_samples(packet_paths)
    source_counts: dict[str, int] = {}
    for sample in samples:
        source_counts[source_key(sample)] = source_counts.get(source_key(sample), 0) + 1
    sources = sorted(source_counts)
    separator = read_json(separator_path) if separator_path else {}
    folds = []
    all_rows = []
    for held_out in sources:
        train_samples = [sample for sample in samples if source_key(sample) != held_out]
        test_samples = [sample for sample in samples if source_key(sample) == held_out]
        weights = train_logistic(train_samples)
        test_rows = rows_for_samples(test_samples, split="leave_one_source_out", weights=weights, separator=separator)
        learned = score_rows(test_rows, "learned_prediction")
        symbolic = score_rows(test_rows, "symbolic_prediction") if separator else {"scored_count": 0, "match_rate": 0.0}
        folds.append(
            {
                "held_out_source": held_out,
                "train_count": len(train_samples),
                "test_count": len(test_samples),
                "test_learned": learned,
                "test_symbolic": symbolic,
                "learned_not_worse_than_symbolic": learned["match_rate"] >= symbolic.get("match_rate", 0.0),
            }
        )
        all_rows.extend(test_rows)
    learned_all = score_rows(all_rows, "learned_prediction")
    symbolic_all = score_rows(all_rows, "symbolic_prediction") if separator else {"scored_count": 0, "match_rate": 0.0}
    fold_ok = bool(folds) and all(fold["learned_not_worse_than_symbolic"] for fold in folds)
    readiness_blockers = []
    if len(sources) < min_sources:
        readiness_blockers.append(f"source_count_below_minimum:{len(sources)}<{min_sources}")
    if len(samples) < min_samples:
        readiness_blockers.append(f"sample_count_below_minimum:{len(samples)}<{min_samples}")
    if not fold_ok:
        readiness_blockers.append("one_or_more_source_folds_underperformed_symbolic")
    if learned_all["match_rate"] < symbolic_all.get("match_rate", 0.0):
        readiness_blockers.append("combined_learned_match_rate_below_symbolic")
    candidate = not readiness_blockers
    source_packet_files = {}
    if temp_dir:
        source_packet_files = {key: str(path) for key, path in write_source_packet_files(packet_paths, temp_dir).items()}
    return {
        "schema": "controller_packet_ogcf_bridge_leave_one_source_out/v1",
        "description": "Report-only leave-one-source-out evaluation for the learned OGCF bridge scorer.",
        "ok": bool(samples) and len(sources) >= 2 and bool(folds),
        "packet_paths": [str(path) for path in packet_paths],
        "separator_path": str(separator_path) if separator_path else None,
        "source_count": len(sources),
        "source_counts": dict(sorted(source_counts.items())),
        "source_packet_files": source_packet_files,
        "sample_count": len(samples),
        "minimum_sources_for_candidate": min_sources,
        "minimum_samples_for_candidate": min_samples,
        "policy": policy,
        "feature_keys": list(FEATURE_KEYS),
        "folds": folds,
        "combined_test_learned": learned_all,
        "combined_test_symbolic": symbolic_all,
        "learned_scorer_candidate": candidate,
        "learned_scorer_candidate_reason": "learned scorer matched or exceeded symbolic separator with enough independent source evidence"
        if candidate
        else "learned scorer lacks enough independent source evidence or underperformed symbolic separator",
        "readiness_blockers": readiness_blockers,
        "promotion_ready": False,
        "promotion_blocker": "report-only leave-one-source-out evaluation; requires broader real logs and manual approval",
        "examples": all_rows[:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Leave-One-Source-Out",
        "",
        "This evaluation is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Sources: `{report['source_count']}`",
        f"Samples: `{report['sample_count']}`",
        f"Minimum sources for candidate: `{report['minimum_sources_for_candidate']}`",
        f"Minimum samples for candidate: `{report['minimum_samples_for_candidate']}`",
        f"Learned scorer candidate: `{report['learned_scorer_candidate']}`",
        f"Candidate reason: `{report['learned_scorer_candidate_reason']}`",
        f"Readiness blockers: `{json.dumps(report['readiness_blockers'])}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Combined Learned",
        "",
        "```json",
        json.dumps(report["combined_test_learned"], indent=2),
        "```",
        "",
        "## Combined Symbolic",
        "",
        "```json",
        json.dumps(report["combined_test_symbolic"], indent=2),
        "```",
        "",
        "## Folds",
        "",
        "| held out source | train | test | learned match | symbolic match | learned >= symbolic |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for fold in report["folds"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | `{}` | `{}` |".format(
                clean_cell(fold["held_out_source"]),
                fold["train_count"],
                fold["test_count"],
                fold["test_learned"]["match_rate"],
                fold["test_symbolic"]["match_rate"],
                fold["learned_not_worse_than_symbolic"],
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run leave-one-source-out evaluation for OGCF bridge scorer.")
    parser.add_argument("--packets", type=Path, action="append", default=None)
    parser.add_argument("--separator", type=Path, default=DEFAULT_SEPARATOR)
    parser.add_argument("--source-packet-dir", type=Path, default=None)
    parser.add_argument("--min-sources", type=int, default=None)
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(
        args.packets or [DEFAULT_PACKETS],
        args.separator,
        temp_dir=args.source_packet_dir,
        min_sources=args.min_sources,
        min_samples=args.min_samples,
        policy_config=load_config(ROOT),
    )
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "source_count": report["source_count"],
                "sample_count": report["sample_count"],
                "combined_test_learned": report["combined_test_learned"],
                "combined_test_symbolic": report["combined_test_symbolic"],
                "learned_scorer_candidate": report["learned_scorer_candidate"],
                "readiness_blockers": report["readiness_blockers"],
                "json": str(args.out_json),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
