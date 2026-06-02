from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.controller_packet_calibration import normalize_bridge_scorer_policy  # noqa: E402
from eval.controller_packet_ogcf_bridge_scorer import (  # noqa: E402
    FEATURE_KEYS,
    bridge_samples,
    learned_prediction,
    read_json,
    score_rows,
    scorer_candidate_decision,
    symbolic_prediction,
    train_logistic,
)


DEFAULT_TRAIN = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_packets_train.jsonl"
DEFAULT_TEST = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_packets_test.jsonl"
DEFAULT_SEPARATOR = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_feature_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_source_holdout_report.md"


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def rows_for_samples(
    samples: list[dict[str, Any]],
    *,
    split: str,
    weights: list[float],
    separator: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for sample in samples:
        learned, probability = learned_prediction(weights, sample)
        symbolic = symbolic_prediction(separator, sample) if separator else "not_available"
        rows.append(
            {
                "split": split,
                "source_packet_path": sample.get("source_packet_path"),
                "operation_id": sample.get("operation_id"),
                "expected": sample.get("expected"),
                "learned_prediction": learned,
                "learned_positive_probability": probability,
                "symbolic_prediction": symbolic,
            }
        )
    return rows


def build_report(
    train_paths: list[Path],
    test_paths: list[Path],
    separator_path: Path | None = None,
    *,
    policy_config: dict[str, Any] | None = None,
    min_test_samples: int | None = None,
) -> dict[str, Any]:
    policy = normalize_bridge_scorer_policy(policy_config, min_test_samples=min_test_samples)
    train_samples = bridge_samples(train_paths)
    test_samples = bridge_samples(test_paths)
    weights = train_logistic(train_samples)
    separator = read_json(separator_path) if separator_path else {}
    train_rows = rows_for_samples(train_samples, split="train", weights=weights, separator=separator)
    test_rows = rows_for_samples(test_samples, split="source_holdout", weights=weights, separator=separator)
    learned_test = score_rows(test_rows, "learned_prediction")
    symbolic_test = score_rows(test_rows, "symbolic_prediction") if separator else {"scored_count": 0, "match_rate": 0.0}
    learned_candidate, readiness_blockers = scorer_candidate_decision(
        learned=learned_test,
        symbolic=symbolic_test,
        test_count=len(test_rows),
        policy=policy,
    )
    return {
        "schema": "controller_packet_ogcf_bridge_source_holdout/v1",
        "description": "Report-only source-log holdout for the OGCF useful-vs-noisy bridge scorer.",
        "ok": bool(train_rows and test_rows),
        "train_packet_paths": [str(path) for path in train_paths],
        "test_packet_paths": [str(path) for path in test_paths],
        "separator_path": str(separator_path) if separator_path else None,
        "train_count": len(train_rows),
        "test_count": len(test_rows),
        "policy": policy,
        "feature_keys": list(FEATURE_KEYS),
        "weights": {key: round(weight, 6) for key, weight in zip(FEATURE_KEYS, weights)},
        "train_learned": score_rows(train_rows, "learned_prediction"),
        "test_learned": learned_test,
        "test_symbolic": symbolic_test,
        "learned_scorer_candidate": learned_candidate,
        "learned_scorer_candidate_reason": "source-holdout learned scorer satisfied candidate policy"
        if learned_candidate
        else "source-holdout learned scorer failed candidate policy",
        "readiness_blockers": readiness_blockers,
        "promotion_ready": False,
        "promotion_blocker": "report-only source-log holdout; requires broader real independent logs and manual approval",
        "examples": test_rows[:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Source Holdout",
        "",
        "This source-log holdout is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Train/test: `{report['train_count']}` / `{report['test_count']}`",
        f"Learned scorer candidate: `{report['learned_scorer_candidate']}`",
        f"Candidate reason: `{report['learned_scorer_candidate_reason']}`",
        f"Readiness blockers: `{json.dumps(report['readiness_blockers'])}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Test Learned",
        "",
        "```json",
        json.dumps(report["test_learned"], indent=2),
        "```",
        "",
        "## Test Symbolic",
        "",
        "```json",
        json.dumps(report["test_symbolic"], indent=2),
        "```",
        "",
        "## Holdout Examples",
        "",
        "| expected | learned | symbolic | probability | operation |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in report["examples"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("expected"),
                row.get("learned_prediction"),
                row.get("symbolic_prediction"),
                row.get("learned_positive_probability"),
                clean_cell(row.get("operation_id")),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run source-log holdout for the OGCF bridge scorer.")
    parser.add_argument("--train-packets", type=Path, action="append", default=None)
    parser.add_argument("--test-packets", type=Path, action="append", default=None)
    parser.add_argument("--separator", type=Path, default=DEFAULT_SEPARATOR)
    parser.add_argument("--min-test-samples", type=int, default=None)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(
        args.train_packets or [DEFAULT_TRAIN],
        args.test_packets or [DEFAULT_TEST],
        args.separator,
        policy_config=load_config(ROOT),
        min_test_samples=args.min_test_samples,
    )
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "train_count": report["train_count"],
                "test_count": report["test_count"],
                "test_learned": report["test_learned"],
                "test_symbolic": report["test_symbolic"],
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
