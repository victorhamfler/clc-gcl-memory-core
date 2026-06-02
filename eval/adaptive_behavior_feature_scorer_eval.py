from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_behavior_shadow_real_log_calibration import (  # noqa: E402
    answer_has_refusal,
    expected_advisory,
    feedback_label,
    feedback_scope,
    linked_operation_id,
    payload,
    read_jsonl,
    request,
    response,
    shadow,
)


DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_eval_report.md"

FEATURE_KEYS = (
    "retrieval_count",
    "selected_count",
    "stale_context_count",
    "top_score",
    "claim_scope_score",
    "answer_type_score",
    "scope_deflection_penalty",
    "selected_top_score",
    "selected_claim_scope_score",
    "selected_answer_type_score",
    "selected_text_match_score",
    "selected_intent_match_score",
    "memory_bad_rate",
    "stale_current_conflict",
    "contradiction_peak",
    "ogcf_bridge_overload_score",
    "ogcf_effective_affected_memory_ratio",
    "ogcf_structural_pressure",
)
FAMILIES = (
    "supported_evidence",
    "missing_support",
    "stale_conflict",
    "wrong_scope",
    "ogcf_bridge_warning",
)
LABELS = ("likely_harmful", "uncertain_keep_symbolic", "likely_helpful")


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def feature_payload(shadow_payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = shadow_payload.get("diagnostics") if isinstance(shadow_payload.get("diagnostics"), dict) else {}
    features = diagnostics.get("evidence_context_features")
    return features if isinstance(features, dict) else {}


def one_hot(value: str, choices: tuple[str, ...]) -> list[float]:
    return [1.0 if value == choice else 0.0 for choice in choices]


def vector_for(sample: dict[str, Any]) -> list[float]:
    features = sample["evidence_context_features"]
    vector = [float_value(features.get(key), 0.0) for key in FEATURE_KEYS]
    vector.extend(one_hot(str(sample.get("behavior_family") or ""), FAMILIES))
    vector.append(1.0 if sample.get("answer_has_refusal") else 0.0)
    return vector


def collect_samples(log_path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(log_path)
    asks = {
        str(row.get("operation_id")): row
        for row in rows
        if row.get("event_type") == "ask" and row.get("operation_id")
    }
    answer_feedback = [
        row
        for row in rows
        if row.get("event_type") == "feedback"
        and feedback_scope(row) == "answer"
        and linked_operation_id(row) in asks
    ]
    samples: list[dict[str, Any]] = []
    for feedback in answer_feedback:
        op_id = linked_operation_id(feedback)
        ask = asks.get(op_id) or {}
        shadow_payload = shadow(ask)
        features = feature_payload(shadow_payload)
        if not features:
            continue
        label = feedback_label(feedback)
        for decision in shadow_payload.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            family = str(decision.get("behavior_family") or "")
            expected = expected_advisory(
                label=label,
                behavior_family=family,
                ask_event=ask,
                shadow_payload=shadow_payload,
            )
            samples.append(
                {
                    "operation_id": op_id,
                    "query": request(ask).get("query") or response(ask).get("query"),
                    "feedback_label": label,
                    "behavior_family": family,
                    "expected_advisory": expected,
                    "symbolic_advisory": str(decision.get("advisory") or ""),
                    "symbolic_probability": float_value(decision.get("shadow_probability"), 0.0),
                    "answer_has_refusal": answer_has_refusal(str(response(ask).get("answer") or "")),
                    "evidence_context_features": features,
                }
            )
    return samples


def split_samples(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = []
    test = []
    for sample in samples:
        bucket = sum(ord(ch) for ch in str(sample.get("operation_id") or "")) % 5
        if bucket == 0:
            test.append(sample)
        else:
            train.append(sample)
    if not test and samples:
        test = samples[::5]
        train = [sample for idx, sample in enumerate(samples) if idx % 5 != 0]
    return train, test


def standardize(train_vectors: list[list[float]], vectors: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    dims = len(train_vectors[0]) if train_vectors else 0
    means = []
    scales = []
    for idx in range(dims):
        values = [row[idx] for row in train_vectors]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / max(1, len(values))
        scale = math.sqrt(variance) or 1.0
        means.append(mean)
        scales.append(scale)
    return (
        [[(row[idx] - means[idx]) / scales[idx] for idx in range(dims)] for row in vectors],
        means,
        scales,
    )


def apply_standardization(vectors: list[list[float]], means: list[float], scales: list[float]) -> list[list[float]]:
    return [[(row[idx] - means[idx]) / scales[idx] for idx in range(len(means))] for row in vectors]


def softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    exps = [math.exp(value - peak) for value in logits]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def train_softmax(
    train_x: list[list[float]],
    train_y: list[int],
    *,
    epochs: int = 900,
    lr: float = 0.08,
    l2: float = 0.001,
) -> list[list[float]]:
    if not train_x:
        return []
    dims = len(train_x[0]) + 1
    weights = [[0.0 for _ in range(dims)] for _ in LABELS]
    for _epoch in range(epochs):
        for row, label_idx in zip(train_x, train_y):
            x = [1.0, *row]
            probs = softmax([sum(w * v for w, v in zip(class_weights, x)) for class_weights in weights])
            for class_idx, class_weights in enumerate(weights):
                error = probs[class_idx] - (1.0 if class_idx == label_idx else 0.0)
                for weight_idx, value in enumerate(x):
                    penalty = l2 * class_weights[weight_idx] if weight_idx else 0.0
                    class_weights[weight_idx] -= lr * (error * value + penalty)
    return weights


def predict(weights: list[list[float]], row: list[float]) -> tuple[str, float]:
    x = [1.0, *row]
    probs = softmax([sum(w * v for w, v in zip(class_weights, x)) for class_weights in weights])
    best_idx = max(range(len(probs)), key=lambda idx: probs[idx])
    return LABELS[best_idx], round(probs[best_idx], 6)


def accuracy(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(key) == row.get("expected_advisory")) / len(rows), 6)


def family_summary(rows: list[dict[str, Any]], prediction_key: str) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        family = str(row.get("behavior_family") or "unknown")
        counters[family]["total"] += 1
        counters[family]["matches"] += int(row.get(prediction_key) == row.get("expected_advisory"))
        counters[family][f"predicted:{row.get(prediction_key)}"] += 1
        counters[family][f"expected:{row.get('expected_advisory')}"] += 1
    summary = {}
    for family, counter in sorted(counters.items()):
        total = int(counter.get("total", 0))
        matches = int(counter.get("matches", 0))
        summary[family] = {
            **dict(sorted(counter.items())),
            "match_rate": round(matches / total, 6) if total else 0.0,
        }
    return summary


def build_report(log_path: Path) -> dict[str, Any]:
    samples = collect_samples(log_path)
    train, test = split_samples(samples)
    train_vectors = [vector_for(sample) for sample in train]
    test_vectors = [vector_for(sample) for sample in test]
    train_x, means, scales = standardize(train_vectors, train_vectors)
    test_x = apply_standardization(test_vectors, means, scales) if test_vectors else []
    train_y = [LABELS.index(sample["expected_advisory"]) for sample in train]
    weights = train_softmax(train_x, train_y)
    train_rows = []
    for sample, vector in zip(train, train_x):
        predicted, confidence = predict(weights, vector)
        train_rows.append({**sample, "learned_advisory": predicted, "learned_confidence": confidence})
    test_rows = []
    for sample, vector in zip(test, test_x):
        predicted, confidence = predict(weights, vector)
        test_rows.append({**sample, "learned_advisory": predicted, "learned_confidence": confidence})
    feature_export_count = sum(1 for sample in samples if sample.get("evidence_context_features"))
    return {
        "schema": "adaptive_behavior_feature_scorer_eval/v1",
        "description": "Report-only tiny local softmax scorer trained on exported EvidenceContextFeatures.",
        "ok": bool(train_rows and test_rows),
        "log_path": str(log_path),
        "sample_count": len(samples),
        "feature_export_count": feature_export_count,
        "feature_keys": list(FEATURE_KEYS),
        "family_keys": list(FAMILIES),
        "labels": list(LABELS),
        "train_count": len(train_rows),
        "test_count": len(test_rows),
        "train_learned_match_rate": accuracy(train_rows, "learned_advisory"),
        "test_learned_match_rate": accuracy(test_rows, "learned_advisory"),
        "test_symbolic_match_rate": accuracy(test_rows, "symbolic_advisory"),
        "test_family_summary_learned": family_summary(test_rows, "learned_advisory"),
        "test_family_summary_symbolic": family_summary(test_rows, "symbolic_advisory"),
        "test_mismatch_examples": [
            {
                "query": row.get("query"),
                "feedback_label": row.get("feedback_label"),
                "behavior_family": row.get("behavior_family"),
                "expected_advisory": row.get("expected_advisory"),
                "learned_advisory": row.get("learned_advisory"),
                "symbolic_advisory": row.get("symbolic_advisory"),
                "learned_confidence": row.get("learned_confidence"),
            }
            for row in test_rows
            if row.get("learned_advisory") != row.get("expected_advisory")
        ][:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
        "promotion_blocker": "single small local log; requires multi-log holdout before runtime use",
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Feature Scorer Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Samples: `{report['sample_count']}`",
        f"Train/test: `{report['train_count']}` / `{report['test_count']}`",
        f"Train learned match rate: `{report['train_learned_match_rate']}`",
        f"Test learned match rate: `{report['test_learned_match_rate']}`",
        f"Test symbolic match rate: `{report['test_symbolic_match_rate']}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Learned Family Summary",
        "",
        "```json",
        json.dumps(report["test_family_summary_learned"], indent=2),
        "```",
        "",
        "## Symbolic Family Summary",
        "",
        "```json",
        json.dumps(report["test_family_summary_symbolic"], indent=2),
        "```",
        "",
        "## Learned Mismatch Examples",
        "",
        "| family | expected | learned | symbolic | query |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.get("test_mismatch_examples") or []:
        query = str(row.get("query") or "").replace("|", "\\|")[:120]
        lines.append(
            f"| `{row.get('behavior_family')}` | `{row.get('expected_advisory')}` | "
            f"`{row.get('learned_advisory')}` | `{row.get('symbolic_advisory')}` | {query} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a tiny report-only scorer on EvidenceContextFeatures.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.log)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "sample_count": report["sample_count"],
                "test_learned_match_rate": report["test_learned_match_rate"],
                "test_symbolic_match_rate": report["test_symbolic_match_rate"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
