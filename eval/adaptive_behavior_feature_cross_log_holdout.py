from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_feature_scorer_eval import (  # noqa: E402
    FEATURE_KEYS,
    accuracy,
    collect_samples,
    family_summary,
)
from eval.adaptive_behavior_feature_scorer_hybrid_eval import (  # noqa: E402
    family_predict,
    residual_predict,
    summarize_residual,
    train_family_models,
    train_residual_model,
)


DEFAULT_TRAIN_LOGS = [
    REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_outcomes.jsonl",
    REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_outcomes.jsonl",
]
DEFAULT_TEST_LOG = Path(r"\\wsl.localhost\Ubuntu\home\victo\experiments_hermes\hermes_feature_residual_real_outcomes.jsonl")
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_cross_log_holdout_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_cross_log_holdout_report.md"


def read_logs(paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    samples = []
    counts = {}
    for path in paths:
        rows = collect_samples(path) if path.exists() else []
        counts[str(path)] = len(rows)
        for row in rows:
            samples.append({**row, "source_log": str(path)})
    return samples, counts


def evaluate_threshold(
    test_samples: list[dict[str, Any]],
    family_models: dict[str, dict[str, Any]],
    residual_model: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    rows = []
    for sample in test_samples:
        family_advisory, family_confidence, family_source = family_predict(family_models, sample)
        residual_label, residual_confidence = residual_predict(residual_model, sample)
        hybrid_advisory = sample["symbolic_advisory"]
        hybrid_source = "symbolic"
        if (
            residual_label == "symbolic_wrong"
            and residual_confidence >= threshold
            and family_source == "family_model"
        ):
            hybrid_advisory = family_advisory
            hybrid_source = "family_override"
        rows.append(
            {
                **sample,
                "family_advisory": family_advisory,
                "family_confidence": family_confidence,
                "family_source": family_source,
                "residual_prediction": residual_label,
                "residual_confidence": residual_confidence,
                "hybrid_advisory": hybrid_advisory,
                "hybrid_source": hybrid_source,
            }
        )
    override_rows = [row for row in rows if row.get("hybrid_source") == "family_override"]
    helpful = sum(1 for row in override_rows if row.get("hybrid_advisory") == row.get("expected_advisory"))
    harmful = sum(
        1
        for row in override_rows
        if row.get("symbolic_advisory") == row.get("expected_advisory")
        and row.get("hybrid_advisory") != row.get("expected_advisory")
    )
    neutral_wrong = sum(
        1
        for row in override_rows
        if row.get("symbolic_advisory") != row.get("expected_advisory")
        and row.get("hybrid_advisory") != row.get("expected_advisory")
    )
    symbolic_rate = accuracy(rows, "symbolic_advisory")
    hybrid_rate = accuracy(rows, "hybrid_advisory")
    return {
        "threshold": threshold,
        "symbolic_match_rate": symbolic_rate,
        "hybrid_match_rate": hybrid_rate,
        "hybrid_delta_vs_symbolic": round(hybrid_rate - symbolic_rate, 6),
        "override_count": len(override_rows),
        "helpful_override_count": helpful,
        "harmful_override_count": harmful,
        "neutral_wrong_override_count": neutral_wrong,
        "residual_summary": summarize_residual(rows),
        "family_summary_hybrid": family_summary(rows, "hybrid_advisory"),
        "override_examples": [
            {
                "query": row.get("query"),
                "behavior_family": row.get("behavior_family"),
                "expected_advisory": row.get("expected_advisory"),
                "symbolic_advisory": row.get("symbolic_advisory"),
                "family_advisory": row.get("family_advisory"),
                "hybrid_advisory": row.get("hybrid_advisory"),
                "residual_confidence": row.get("residual_confidence"),
            }
            for row in override_rows
        ][:20],
    }


def best_zero_harm(threshold_reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in threshold_reports if int(row.get("harmful_override_count") or 0) == 0]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            float(row.get("hybrid_delta_vs_symbolic") or 0.0),
            int(row.get("helpful_override_count") or 0),
            -int(row.get("override_count") or 0),
        ),
    )


def build_report(train_logs: list[Path], test_log: Path, thresholds: list[float]) -> dict[str, Any]:
    train_samples, train_counts = read_logs(train_logs)
    test_samples, test_counts = read_logs([test_log])
    family_models = train_family_models(train_samples)
    residual_model = train_residual_model(train_samples)
    threshold_reports = [
        evaluate_threshold(test_samples, family_models, residual_model, threshold)
        for threshold in thresholds
    ]
    symbolic_rate = threshold_reports[0]["symbolic_match_rate"] if threshold_reports else 0.0
    best_any = max(threshold_reports, key=lambda row: float(row.get("hybrid_delta_vs_symbolic") or 0.0), default=None)
    best_safe = best_zero_harm(threshold_reports)
    return {
        "schema": "adaptive_behavior_feature_cross_log_holdout/v1",
        "description": "Report-only leave-log-out feature residual evaluation with threshold sweep.",
        "ok": bool(train_samples and test_samples and threshold_reports),
        "train_logs": [str(path) for path in train_logs],
        "test_log": str(test_log),
        "train_sample_count": len(train_samples),
        "test_sample_count": len(test_samples),
        "train_counts_by_log": train_counts,
        "test_counts_by_log": test_counts,
        "feature_keys": list(FEATURE_KEYS),
        "family_model_count": len(family_models),
        "family_model_train_counts": {family: model["train_count"] for family, model in sorted(family_models.items())},
        "symbolic_match_rate": symbolic_rate,
        "threshold_reports": threshold_reports,
        "best_any_threshold": best_any,
        "best_zero_harm_threshold": best_safe,
        "zero_harm_beats_symbolic": bool(best_safe and float(best_safe.get("hybrid_delta_vs_symbolic") or 0.0) > 0.0),
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
        "promotion_blocker": "requires repeated independent real-log zero-harm improvement before runtime promotion",
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    best_safe = report.get("best_zero_harm_threshold") or {}
    best_any = report.get("best_any_threshold") or {}
    lines = [
        "# Adaptive Behavior Feature Cross-Log Holdout",
        "",
        f"Passed: **{report['ok']}**",
        f"Train samples: `{report['train_sample_count']}`",
        f"Test samples: `{report['test_sample_count']}`",
        f"Symbolic match rate: `{report['symbolic_match_rate']}`",
        f"Best any threshold delta: `{best_any.get('hybrid_delta_vs_symbolic')}` at `{best_any.get('threshold')}`",
        f"Best zero-harm delta: `{best_safe.get('hybrid_delta_vs_symbolic')}` at `{best_safe.get('threshold')}`",
        f"Zero-harm beats symbolic: `{report['zero_harm_beats_symbolic']}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Train Logs",
        "",
    ]
    for path in report.get("train_logs") or []:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Test Log",
            "",
            f"`{report['test_log']}`",
            "",
            "## Threshold Sweep",
            "",
            "| threshold | hybrid | delta | overrides | helpful | harmful | neutral wrong |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report.get("threshold_reports") or []:
        lines.append(
            f"| `{row.get('threshold')}` | `{row.get('hybrid_match_rate')}` | "
            f"`{row.get('hybrid_delta_vs_symbolic')}` | `{row.get('override_count')}` | "
            f"`{row.get('helpful_override_count')}` | `{row.get('harmful_override_count')}` | "
            f"`{row.get('neutral_wrong_override_count')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_thresholds(raw: str) -> list[float]:
    values = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        values.append(round(float(item), 6))
    return values or [0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cross-log holdout for EvidenceContextFeatures residual scorer.")
    parser.add_argument("--train-log", action="append", type=Path, default=None)
    parser.add_argument("--test-log", type=Path, default=DEFAULT_TEST_LOG)
    parser.add_argument("--thresholds", default="0.50,0.60,0.70,0.80,0.90,0.95,0.97,0.98,0.99,0.995,0.999")
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    train_logs = args.train_log or DEFAULT_TRAIN_LOGS
    report = build_report(train_logs, args.test_log, parse_thresholds(args.thresholds))
    write_report(report, args.out_json, args.out_md)
    best_safe = report.get("best_zero_harm_threshold") or {}
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "symbolic_match_rate": report["symbolic_match_rate"],
                "zero_harm_beats_symbolic": report["zero_harm_beats_symbolic"],
                "best_zero_harm_delta": best_safe.get("hybrid_delta_vs_symbolic"),
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
