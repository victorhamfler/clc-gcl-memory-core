from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_DATASET = REPO_ROOT / "experiments" / "adaptive_context_combined_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_tiny_scorer_report.md"


POSITIVE_LABELS = {
    "answer_correct",
    "answer_good_citation",
    "answer_bridge_warning_useful",
    "useful",
    "good",
    "excellent",
    "bridge_relevant",
    "cross_domain_bridge",
    "ogcf_bridge",
    "ogcf_geometry",
    "bridge_geometry",
}
NEGATIVE_LABELS = {
    "answer_stale",
    "answer_wrong_scope",
    "answer_missing_support",
    "answer_overconfident",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_noise",
    "stale",
    "wrong_domain",
    "missing_source",
    "ogcf_false_positive",
    "bridge_irrelevant",
    "ordinary_lookup",
    "ordinary_fact",
    "unrelated_bridge",
    "no_ogcf_pressure",
    "wrong",
    "bad",
    "incorrect",
}


def read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return loaded


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def label_to_target(example: dict[str, Any]) -> int | None:
    label = str(example.get("label") or "").strip().lower()
    if label in POSITIVE_LABELS:
        return 1
    if label in NEGATIVE_LABELS:
        return 0
    rating = as_float(example.get("rating"), 0.0)
    if rating > 0.0:
        return 1
    if rating < 0.0:
        return 0
    return None


def retrieval_stats(rows: list[dict[str, Any]]) -> dict[str, float]:
    numeric_fields = ("score", "cosine", "text_match_score", "claim_scope_score", "answer_type_score")
    out: dict[str, float] = {"retrieval_count": float(len(rows))}
    for field in numeric_fields:
        values = [as_float(row.get(field), math.nan) for row in rows if isinstance(row, dict)]
        values = [value for value in values if not math.isnan(value)]
        out[f"{field}_max"] = max(values) if values else 0.0
        out[f"{field}_mean"] = sum(values) / len(values) if values else 0.0
        out[f"{field}_min"] = min(values) if values else 0.0
    authority = Counter(str(row.get("authority_state") or "").strip().lower() for row in rows if isinstance(row, dict))
    total = max(1, len(rows))
    for key in ("standalone", "current", "stale", "superseded"):
        out[f"authority_{key}_ratio"] = authority.get(key, 0) / total
    return out


def feature_dict(example: dict[str, Any]) -> dict[str, float]:
    features: dict[str, float] = {
        "bias": 1.0,
        "scope_answer": 1.0 if example.get("feedback_scope") == "answer" else 0.0,
        "scope_memory": 1.0 if example.get("feedback_scope") == "memory" else 0.0,
        "context_adaptive": 1.0 if example.get("context_source") == "adaptive_memory_context" else 0.0,
        "ogcf_meta_present": 1.0 if example.get("ogcf_meta_present") else 0.0,
        "selected_memory_count": float(len(example.get("selected_memory_ids") or [])),
    }
    for prefix in ("features", "diagnostics"):
        values = example.get(prefix)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if isinstance(value, bool):
                features[f"{prefix}.{key}"] = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                features[f"{prefix}.{key}"] = float(value)
    decision = str(example.get("selector_action") or "unknown").strip().lower()
    if decision:
        features[f"selector_action.{decision}"] = 1.0
    policy = str(example.get("selector_policy") or "unknown").strip().lower()
    if policy:
        features[f"selector_policy.{policy}"] = 1.0
    features.update({f"retrieval.{key}": value for key, value in retrieval_stats(example.get("retrieval_context") or []).items()})
    return features


def load_examples(dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    examples: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in dataset.get("examples") or []:
        if not isinstance(raw, dict):
            continue
        target = label_to_target(raw)
        if target is None:
            skipped.append({"id": raw.get("id"), "reason": "neutral_or_unknown_label", "label": raw.get("label")})
            continue
        item = dict(raw)
        item["_target"] = target
        item["_features"] = feature_dict(raw)
        examples.append(item)
    return examples, skipped


def vocabulary(examples: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for example in examples:
        keys.update(example["_features"].keys())
    return sorted(keys)


def matrix(examples: list[dict[str, Any]], vocab: list[str]) -> tuple[list[list[float]], list[int]]:
    xs = [[float(example["_features"].get(key, 0.0)) for key in vocab] for example in examples]
    ys = [int(example["_target"]) for example in examples]
    return xs, ys


def fit_scaler(xs: list[list[float]]) -> tuple[list[float], list[float]]:
    if not xs:
        return [], []
    cols = len(xs[0])
    means = [sum(row[col] for row in xs) / len(xs) for col in range(cols)]
    scales: list[float] = []
    for col in range(cols):
        var = sum((row[col] - means[col]) ** 2 for row in xs) / max(1, len(xs))
        scales.append(math.sqrt(var) or 1.0)
    return means, scales


def transform(xs: list[list[float]], means: list[float], scales: list[float]) -> list[list[float]]:
    return [[(value - means[index]) / scales[index] for index, value in enumerate(row)] for row in xs]


def sigmoid(value: float) -> float:
    if value < -40:
        return 0.0
    if value > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def train_logistic(xs: list[list[float]], ys: list[int], *, epochs: int = 700, lr: float = 0.08, l2: float = 0.015) -> list[float]:
    if not xs:
        return []
    rng = random.Random(1337)
    weights = [0.0 for _ in xs[0]]
    order = list(range(len(xs)))
    for _ in range(epochs):
        rng.shuffle(order)
        for idx in order:
            row = xs[idx]
            pred = sigmoid(sum(w * x for w, x in zip(weights, row)))
            error = pred - ys[idx]
            for col, value in enumerate(row):
                weights[col] -= lr * (error * value + l2 * weights[col])
    return weights


def predict(weights: list[float], xs: list[list[float]]) -> list[float]:
    return [sigmoid(sum(w * x for w, x in zip(weights, row))) for row in xs]


def evaluate_probs(probs: list[float], ys: list[int]) -> dict[str, Any]:
    preds = [1 if prob >= 0.5 else 0 for prob in probs]
    total = len(ys)
    correct = sum(1 for pred, y in zip(preds, ys) if pred == y)
    tp = sum(1 for pred, y in zip(preds, ys) if pred == 1 and y == 1)
    tn = sum(1 for pred, y in zip(preds, ys) if pred == 0 and y == 0)
    fp = sum(1 for pred, y in zip(preds, ys) if pred == 1 and y == 0)
    fn = sum(1 for pred, y in zip(preds, ys) if pred == 0 and y == 1)
    return {
        "count": total,
        "accuracy": round(correct / total, 6) if total else 0.0,
        "brier": round(sum((prob - y) ** 2 for prob, y in zip(probs, ys)) / total, 6) if total else 0.0,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def majority_baseline(train_y: list[int], test_y: list[int]) -> dict[str, Any]:
    majority = 1 if sum(train_y) >= (len(train_y) / 2.0) else 0
    return evaluate_probs([float(majority) for _ in test_y], test_y)


def symbolic_health_prob(example: dict[str, Any]) -> float:
    features = example["_features"]
    top_score = features.get("retrieval.score_max", 0.0)
    claim_score = features.get("retrieval.claim_scope_score_max", 0.0)
    memory_bad = features.get("diagnostics.memory_bad_rate", 0.18)
    stale_conflict = features.get("diagnostics.stale_current_conflict", 0.0)
    contradiction = features.get("diagnostics.contradiction_peak", 0.0)
    ogcf = features.get("ogcf_meta_present", 0.0)
    signal = 1.0 * top_score + 0.7 * claim_score - 0.8 * memory_bad - 0.8 * stale_conflict - 0.6 * contradiction
    if ogcf and example.get("label") in {"answer_bridge_warning_noise", "ogcf_false_positive"}:
        signal -= 0.4
    return sigmoid(2.2 * (signal - 0.25))


def train_eval(train: list[dict[str, Any]], test: list[dict[str, Any]]) -> dict[str, Any]:
    vocab = vocabulary(train)
    train_x, train_y = matrix(train, vocab)
    test_x, test_y = matrix(test, vocab)
    means, scales = fit_scaler(train_x)
    scaled_train = transform(train_x, means, scales)
    scaled_test = transform(test_x, means, scales)
    weights = train_logistic(scaled_train, train_y)
    learned = evaluate_probs(predict(weights, scaled_test), test_y)
    majority = majority_baseline(train_y, test_y)
    symbolic = evaluate_probs([symbolic_health_prob(example) for example in test], test_y)
    coefficients = sorted(
        (
            {"feature": feature, "weight": round(weight, 6)}
            for feature, weight in zip(vocab, weights)
            if feature != "bias"
        ),
        key=lambda item: abs(item["weight"]),
        reverse=True,
    )[:20]
    return {
        "train_count": len(train),
        "test_count": len(test),
        "positive_train": int(sum(train_y)),
        "positive_test": int(sum(test_y)),
        "learned": learned,
        "majority_baseline": majority,
        "symbolic_health_baseline": symbolic,
        "top_coefficients": coefficients,
    }


def answer_label_by_operation(examples: list[dict[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for example in examples:
        if example.get("feedback_scope") != "answer":
            continue
        linked = str(example.get("linked_operation_id") or "")
        label = str(example.get("label") or "").strip().lower()
        if linked and label:
            labels[linked] = label
    return labels


def behavior_group(example: dict[str, Any], answer_labels: dict[str, str]) -> str:
    linked = str(example.get("linked_operation_id") or "")
    answer_label = answer_labels.get(linked)
    if answer_label:
        return answer_label
    return str(example.get("label") or example.get("outcome_family") or "unknown").strip().lower()


def behavior_holdout(examples: list[dict[str, Any]]) -> dict[str, Any]:
    answer_labels = answer_label_by_operation(examples)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        groups[behavior_group(example, answer_labels)].append(example)

    group_results: list[dict[str, Any]] = []
    for group_name in sorted(groups):
        test = groups[group_name]
        train = [item for name, group in groups.items() if name != group_name for item in group]
        if len(train) < 8 or len(test) < 2 or len({item["_target"] for item in train}) < 2:
            continue
        result = train_eval(train, test)
        group_results.append(
            {
                "heldout_group": group_name,
                "test_count": len(test),
                "positive_test": sum(int(item["_target"]) for item in test),
                "negative_test": sum(1 - int(item["_target"]) for item in test),
                "learned": result["learned"],
                "majority_baseline": result["majority_baseline"],
                "symbolic_health_baseline": result["symbolic_health_baseline"],
            }
        )

    def weighted(metric: str, model: str) -> float:
        denom = sum(int(row["test_count"]) for row in group_results)
        if denom <= 0:
            return 0.0
        return round(
            sum(float(row[model][metric]) * int(row["test_count"]) for row in group_results) / denom,
            6,
        )

    return {
        "groups": len(group_results),
        "test_count": sum(int(row["test_count"]) for row in group_results),
        "weighted": {
            "learned": {"accuracy": weighted("accuracy", "learned"), "brier": weighted("brier", "learned")},
            "majority_baseline": {
                "accuracy": weighted("accuracy", "majority_baseline"),
                "brier": weighted("brier", "majority_baseline"),
            },
            "symbolic_health_baseline": {
                "accuracy": weighted("accuracy", "symbolic_health_baseline"),
                "brier": weighted("brier", "symbolic_health_baseline"),
            },
        },
        "group_results": group_results,
    }


def stratified_folds(examples: list[dict[str, Any]], k: int = 5) -> list[list[dict[str, Any]]]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        buckets[int(example["_target"])].append(example)
    rng = random.Random(20260525)
    folds = [[] for _ in range(k)]
    for bucket in buckets.values():
        bucket = list(bucket)
        rng.shuffle(bucket)
        for index, item in enumerate(bucket):
            folds[index % k].append(item)
    return folds


def cross_validate(examples: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    folds = stratified_folds(examples, k=k)
    learned_all: list[dict[str, Any]] = []
    majority_all: list[dict[str, Any]] = []
    symbolic_all: list[dict[str, Any]] = []
    for index in range(k):
        test = folds[index]
        train = [item for fold_index, fold in enumerate(folds) if fold_index != index for item in fold]
        result = train_eval(train, test)
        learned_all.append(result["learned"])
        majority_all.append(result["majority_baseline"])
        symbolic_all.append(result["symbolic_health_baseline"])

    def avg(metric: str, rows: list[dict[str, Any]]) -> float:
        return round(sum(float(row[metric]) for row in rows) / len(rows), 6) if rows else 0.0

    return {
        "folds": k,
        "learned": {"accuracy": avg("accuracy", learned_all), "brier": avg("brier", learned_all)},
        "majority_baseline": {"accuracy": avg("accuracy", majority_all), "brier": avg("brier", majority_all)},
        "symbolic_health_baseline": {"accuracy": avg("accuracy", symbolic_all), "brier": avg("brier", symbolic_all)},
    }


def context_breakdown(examples: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for context in sorted({str(item.get("context_source")) for item in examples}):
        group = [item for item in examples if str(item.get("context_source")) == context]
        out[context] = {
            "count": len(group),
            "positive": sum(int(item["_target"]) for item in group),
            "negative": sum(1 - int(item["_target"]) for item in group),
        }
    return out


def build_report(dataset_path: Path) -> dict[str, Any]:
    dataset = read_json(dataset_path)
    if dataset.get("schema") != "adaptive_context_outcome_dataset/v1":
        raise ValueError(f"Unsupported dataset schema: {dataset.get('schema')}")
    examples, skipped = load_examples(dataset)
    adaptive = [item for item in examples if item.get("context_source") == "adaptive_memory_context"]
    legacy = [item for item in examples if item.get("context_source") == "legacy_selector_snapshot"]
    report: dict[str, Any] = {
        "schema": "adaptive_context_tiny_scorer/v1",
        "description": "Report-only tiny learned scorer for adaptive-context outcome polarity. It does not mutate runtime, config, or selector policy.",
        "dataset_path": str(dataset_path),
        "example_count": len(examples),
        "skipped_count": len(skipped),
        "context_breakdown": context_breakdown(examples),
        "label_counts": dict(sorted(Counter(str(item.get("label")) for item in examples).items())),
        "target_counts": {
            "positive": sum(int(item["_target"]) for item in examples),
            "negative": sum(1 - int(item["_target"]) for item in examples),
        },
        "evaluations": {},
        "skipped": skipped[:50],
        "mutates_runtime": False,
        "mutates_config": False,
    }
    checks = {
        "has_examples": len(examples) >= 12,
        "has_positive_and_negative": len({item["_target"] for item in examples}) == 2,
        "has_adaptive_examples": bool(adaptive),
        "report_only": True,
    }
    capability_checks = {
        "has_legacy_examples": bool(legacy),
        "has_historical_to_adaptive_eval": bool(legacy and adaptive),
    }
    if len(examples) >= 12 and len({item["_target"] for item in examples}) == 2:
        report["evaluations"]["five_fold_combined"] = cross_validate(examples, k=5)
    if legacy and adaptive and len({item["_target"] for item in legacy}) == 2 and len({item["_target"] for item in adaptive}) == 2:
        report["evaluations"]["train_legacy_test_adaptive"] = train_eval(legacy, adaptive)
    if len(adaptive) >= 8 and len({item["_target"] for item in adaptive}) == 2:
        report["evaluations"]["adaptive_only_leave_style"] = cross_validate(adaptive, k=min(4, len(adaptive)))
        report["evaluations"]["adaptive_behavior_holdout"] = behavior_holdout(adaptive)
    holdout = report["evaluations"].get("adaptive_behavior_holdout", {}).get("weighted", {})
    learned_holdout = holdout.get("learned", {})
    symbolic_holdout = holdout.get("symbolic_health_baseline", {})
    if holdout and (
        float(learned_holdout.get("accuracy", 0.0)) < float(symbolic_holdout.get("accuracy", 0.0))
        or float(learned_holdout.get("brier", 1.0)) > float(symbolic_holdout.get("brier", 0.0))
    ):
        report["readiness"] = "blocked_behavior_generalization"
    elif report["evaluations"]:
        report["readiness"] = "analysis_ready"
    else:
        report["readiness"] = "insufficient_data"
    report["checks"] = checks
    report["capability_checks"] = capability_checks
    report["ok"] = all(checks.values()) and bool(report["evaluations"])
    return report


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Tiny Scorer",
        "",
        "This is a report-only learned scorer. It does not change runtime behavior, selector policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report.get('readiness')}`",
        f"Examples: `{report['example_count']}`",
        f"Skipped: `{report['skipped_count']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report.get("checks", {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Evaluation Summary", ""])
    for name, result in (report.get("evaluations") or {}).items():
        lines.append(f"### {name}")
        if "learned" in result:
            lines.append("")
            lines.append("| model | accuracy | brier |")
            lines.append("| --- | ---: | ---: |")
            for model_name in ("learned", "majority_baseline", "symbolic_health_baseline"):
                row = result[model_name]
                lines.append(f"| `{model_name}` | `{row['accuracy']}` | `{row['brier']}` |")
        elif "weighted" in result:
            lines.append("")
            lines.append(f"Held-out groups: `{result.get('groups')}`, evaluated examples: `{result.get('test_count')}`")
            lines.append("")
            lines.append("| model | weighted accuracy | weighted brier |")
            lines.append("| --- | ---: | ---: |")
            for model_name in ("learned", "majority_baseline", "symbolic_health_baseline"):
                row = result["weighted"][model_name]
                lines.append(f"| `{model_name}` | `{row['accuracy']}` | `{row['brier']}` |")
        else:
            lines.append("")
            lines.append("| model | accuracy | brier |")
            lines.append("| --- | ---: | ---: |")
            for model_name in ("learned", "majority_baseline", "symbolic_health_baseline"):
                row = result[model_name]
                lines.append(f"| `{model_name}` | `{row['accuracy']}` | `{row['brier']}` |")
        lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train/evaluate a report-only tiny scorer over adaptive-context outcome data.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.dataset))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "example_count": report["example_count"],
                "target_counts": report["target_counts"],
                "evaluations": report["evaluations"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
