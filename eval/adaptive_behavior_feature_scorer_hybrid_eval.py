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

from eval.adaptive_behavior_feature_scorer_eval import (  # noqa: E402
    DEFAULT_LOG,
    FEATURE_KEYS,
    LABELS,
    accuracy,
    apply_standardization,
    collect_samples,
    family_summary,
    predict,
    split_samples,
    standardize,
    train_softmax,
    vector_for,
)


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_hybrid_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_scorer_hybrid_eval_report.md"
RESIDUAL_LABELS = ("symbolic_correct", "symbolic_wrong")


def train_family_models(train: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    families = sorted({str(sample.get("behavior_family") or "") for sample in train})
    for family in families:
        family_train = [sample for sample in train if sample.get("behavior_family") == family]
        if len(family_train) < 4:
            continue
        expected_labels = {sample.get("expected_advisory") for sample in family_train}
        if len(expected_labels) < 2:
            continue
        vectors = [vector_for(sample) for sample in family_train]
        train_x, means, scales = standardize(vectors, vectors)
        train_y = [LABELS.index(sample["expected_advisory"]) for sample in family_train]
        weights = train_softmax(train_x, train_y, epochs=700, lr=0.06, l2=0.004)
        models[family] = {"weights": weights, "means": means, "scales": scales, "train_count": len(family_train)}
    return models


def family_predict(models: dict[str, dict[str, Any]], sample: dict[str, Any]) -> tuple[str, float, str]:
    family = str(sample.get("behavior_family") or "")
    model = models.get(family)
    if not model:
        return str(sample.get("symbolic_advisory") or ""), 1.0, "symbolic_fallback_no_family_model"
    vector = apply_standardization([vector_for(sample)], model["means"], model["scales"])[0]
    prediction, confidence = predict(model["weights"], vector)
    return prediction, confidence, "family_model"


def train_residual_model(train: list[dict[str, Any]]) -> dict[str, Any]:
    vectors = [vector_for(sample) for sample in train]
    train_x, means, scales = standardize(vectors, vectors)
    train_y = [
        0 if sample.get("symbolic_advisory") == sample.get("expected_advisory") else 1
        for sample in train
    ]
    weights = train_binary_softmax(train_x, train_y)
    return {"weights": weights, "means": means, "scales": scales, "train_count": len(train)}


def train_binary_softmax(
    train_x: list[list[float]],
    train_y: list[int],
    *,
    epochs: int = 700,
    lr: float = 0.06,
    l2: float = 0.006,
) -> list[list[float]]:
    if not train_x:
        return []
    dims = len(train_x[0]) + 1
    weights = [[0.0 for _ in range(dims)] for _ in RESIDUAL_LABELS]
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


def softmax(logits: list[float]) -> list[float]:
    import math

    if not logits:
        return []
    peak = max(logits)
    exps = [math.exp(value - peak) for value in logits]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def residual_predict(model: dict[str, Any], sample: dict[str, Any]) -> tuple[str, float]:
    if not model.get("weights"):
        return "symbolic_correct", 1.0
    vector = apply_standardization([vector_for(sample)], model["means"], model["scales"])[0]
    x = [1.0, *vector]
    probs = softmax([sum(w * v for w, v in zip(class_weights, x)) for class_weights in model["weights"]])
    if not probs:
        return "symbolic_correct", 1.0
    best_idx = max(range(len(probs)), key=lambda idx: probs[idx])
    return RESIDUAL_LABELS[best_idx], round(probs[best_idx], 6)


def summarize_residual(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for row in rows:
        actual = "symbolic_correct" if row.get("symbolic_advisory") == row.get("expected_advisory") else "symbolic_wrong"
        predicted = str(row.get("residual_prediction") or "")
        counter["total"] += 1
        counter["matches"] += int(actual == predicted)
        counter[f"actual:{actual}"] += 1
        counter[f"predicted:{predicted}"] += 1
    total = int(counter.get("total", 0))
    matches = int(counter.get("matches", 0))
    return {**dict(sorted(counter.items())), "match_rate": round(matches / total, 6) if total else 0.0}


def build_report(log_path: Path, *, override_confidence: float = 0.70) -> dict[str, Any]:
    samples = collect_samples(log_path)
    train, test = split_samples(samples)
    family_models = train_family_models(train)
    residual_model = train_residual_model(train)
    test_rows = []
    override_count = 0
    harmful_override_count = 0
    helpful_override_count = 0
    for sample in test:
        family_advisory, family_confidence, family_source = family_predict(family_models, sample)
        residual_label, residual_confidence = residual_predict(residual_model, sample)
        hybrid_advisory = sample["symbolic_advisory"]
        hybrid_source = "symbolic"
        if (
            residual_label == "symbolic_wrong"
            and residual_confidence >= override_confidence
            and family_source == "family_model"
        ):
            override_count += 1
            hybrid_advisory = family_advisory
            hybrid_source = "family_override"
            if hybrid_advisory == sample["expected_advisory"]:
                helpful_override_count += 1
            else:
                harmful_override_count += 1
        test_rows.append(
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
    symbolic_rate = accuracy(test_rows, "symbolic_advisory")
    family_rate = accuracy(test_rows, "family_advisory")
    hybrid_rate = accuracy(test_rows, "hybrid_advisory")
    return {
        "schema": "adaptive_behavior_feature_scorer_hybrid_eval/v1",
        "description": "Report-only family-specific and residual hybrid scorer over exported EvidenceContextFeatures.",
        "ok": bool(train and test),
        "log_path": str(log_path),
        "sample_count": len(samples),
        "train_count": len(train),
        "test_count": len(test),
        "feature_keys": list(FEATURE_KEYS),
        "family_model_count": len(family_models),
        "family_model_train_counts": {family: model["train_count"] for family, model in sorted(family_models.items())},
        "override_confidence": override_confidence,
        "test_symbolic_match_rate": symbolic_rate,
        "test_family_model_match_rate": family_rate,
        "test_hybrid_match_rate": hybrid_rate,
        "residual_summary": summarize_residual(test_rows),
        "override_count": override_count,
        "helpful_override_count": helpful_override_count,
        "harmful_override_count": harmful_override_count,
        "hybrid_delta_vs_symbolic": round(hybrid_rate - symbolic_rate, 6),
        "family_summary_symbolic": family_summary(test_rows, "symbolic_advisory"),
        "family_summary_family_model": family_summary(test_rows, "family_advisory"),
        "family_summary_hybrid": family_summary(test_rows, "hybrid_advisory"),
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
            for row in test_rows
            if row.get("hybrid_source") == "family_override"
        ][:20],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
        "promotion_blocker": "single feature log and no multi-log holdout; hybrid must beat symbolic consistently before promotion",
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Feature Scorer Hybrid Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Samples: `{report['sample_count']}`",
        f"Train/test: `{report['train_count']}` / `{report['test_count']}`",
        f"Family models: `{report['family_model_count']}`",
        f"Symbolic match rate: `{report['test_symbolic_match_rate']}`",
        f"Family model match rate: `{report['test_family_model_match_rate']}`",
        f"Hybrid match rate: `{report['test_hybrid_match_rate']}`",
        f"Hybrid delta vs symbolic: `{report['hybrid_delta_vs_symbolic']}`",
        f"Overrides: `{report['override_count']}` helpful `{report['helpful_override_count']}` harmful `{report['harmful_override_count']}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Residual Summary",
        "",
        "```json",
        json.dumps(report["residual_summary"], indent=2),
        "```",
        "",
        "## Hybrid Family Summary",
        "",
        "```json",
        json.dumps(report["family_summary_hybrid"], indent=2),
        "```",
        "",
        "## Override Examples",
        "",
        "| family | expected | symbolic | family | hybrid | query |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("override_examples") or []:
        query = str(row.get("query") or "").replace("|", "\\|")[:120]
        lines.append(
            f"| `{row.get('behavior_family')}` | `{row.get('expected_advisory')}` | "
            f"`{row.get('symbolic_advisory')}` | `{row.get('family_advisory')}` | "
            f"`{row.get('hybrid_advisory')}` | {query} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate report-only family/residual scorers over EvidenceContextFeatures.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    parser.add_argument("--override-confidence", type=float, default=0.70)
    args = parser.parse_args()
    report = build_report(args.log, override_confidence=args.override_confidence)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "test_symbolic_match_rate": report["test_symbolic_match_rate"],
                "test_family_model_match_rate": report["test_family_model_match_rate"],
                "test_hybrid_match_rate": report["test_hybrid_match_rate"],
                "hybrid_delta_vs_symbolic": report["hybrid_delta_vs_symbolic"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
