from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_context_tiny_scorer import (
    answer_label_by_operation,
    behavior_group,
    cross_validate,
    evaluate_probs,
    fit_scaler,
    load_examples,
    matrix,
    predict,
    read_json,
    symbolic_health_prob,
    train_logistic,
    transform,
    vocabulary,
)


DEFAULT_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_behavior_aware_scorer_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_behavior_aware_scorer_report.md"


def train_family_model(train: list[dict[str, Any]]) -> dict[str, Any]:
    ys = [int(item["_target"]) for item in train]
    prior = (sum(ys) + 1.0) / (len(ys) + 2.0)
    model: dict[str, Any] = {"count": len(train), "prior": prior, "can_learn": False}
    if len(train) >= 4 and len(set(ys)) == 2:
        vocab = vocabulary(train)
        train_x, _ = matrix(train, vocab)
        means, scales = fit_scaler(train_x)
        weights = train_logistic(transform(train_x, means, scales), ys, epochs=500, lr=0.06, l2=0.02)
        model.update({"can_learn": True, "vocab": vocab, "means": means, "scales": scales, "weights": weights})
    return model


def family_predict(model: dict[str, Any], examples: list[dict[str, Any]]) -> list[float]:
    if not model.get("can_learn"):
        return [float(model.get("prior", 0.5)) for _ in examples]
    xs, _ = matrix(examples, list(model["vocab"]))
    return predict(list(model["weights"]), transform(xs, list(model["means"]), list(model["scales"])))


def symbolic_probs(examples: list[dict[str, Any]]) -> list[float]:
    return [symbolic_health_prob(example) for example in examples]


def behavior_aware_predict(train: list[dict[str, Any]], test: list[dict[str, Any]]) -> tuple[list[float], list[dict[str, Any]]]:
    answer_labels = answer_label_by_operation(train + test)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in train:
        groups[behavior_group(example, answer_labels)].append(example)
    models = {name: train_family_model(items) for name, items in groups.items()}

    probs: list[float] = []
    routes: list[dict[str, Any]] = []
    for example in test:
        group = behavior_group(example, answer_labels)
        model = models.get(group)
        symbolic = symbolic_health_prob(example)
        if model is None:
            prob = symbolic
            route = "symbolic_unseen_family"
        else:
            learned = family_predict(model, [example])[0]
            confidence = min(0.75, math.log1p(float(model.get("count", 0))) / 4.0)
            prob = confidence * learned + (1.0 - confidence) * symbolic
            route = "family_model" if model.get("can_learn") else "family_prior_blend"
        probs.append(prob)
        routes.append({"id": example.get("id"), "behavior_group": group, "route": route, "probability": round(prob, 6)})
    return probs, routes


def behavior_holdout(examples: list[dict[str, Any]]) -> dict[str, Any]:
    answer_labels = answer_label_by_operation(examples)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        groups[behavior_group(example, answer_labels)].append(example)
    rows: list[dict[str, Any]] = []
    all_probs: list[float] = []
    all_symbolic: list[float] = []
    all_y: list[int] = []
    for group_name in sorted(groups):
        test = groups[group_name]
        train = [item for name, group in groups.items() if name != group_name for item in group]
        if len(train) < 8 or len(test) < 2 or len({item["_target"] for item in train}) < 2:
            continue
        probs, routes = behavior_aware_predict(train, test)
        ys = [int(item["_target"]) for item in test]
        symbolic = symbolic_probs(test)
        all_probs.extend(probs)
        all_symbolic.extend(symbolic)
        all_y.extend(ys)
        rows.append(
            {
                "heldout_group": group_name,
                "test_count": len(test),
                "hybrid": evaluate_probs(probs, ys),
                "symbolic_health_baseline": evaluate_probs(symbolic, ys),
                "routes": routes[:8],
            }
        )
    return {
        "groups": len(rows),
        "test_count": len(all_y),
        "weighted": {
            "hybrid": evaluate_probs(all_probs, all_y),
            "symbolic_health_baseline": evaluate_probs(all_symbolic, all_y),
        },
        "group_results": rows,
    }


def random_split_eval(examples: list[dict[str, Any]], k: int = 4) -> dict[str, Any]:
    base = cross_validate(examples, k=k)
    return {
        "folds": k,
        "generic_learned": base["learned"],
        "majority_baseline": base["majority_baseline"],
        "symbolic_health_baseline": base["symbolic_health_baseline"],
    }


def build_report(dataset_path: Path) -> dict[str, Any]:
    dataset = read_json(dataset_path)
    if dataset.get("schema") != "adaptive_context_outcome_dataset/v1":
        raise ValueError(f"Unsupported dataset schema: {dataset.get('schema')}")
    examples, skipped = load_examples(dataset)
    adaptive = [item for item in examples if item.get("context_source") == "adaptive_memory_context"]
    holdout = behavior_holdout(adaptive)
    hybrid = holdout.get("weighted", {}).get("hybrid", {})
    symbolic = holdout.get("weighted", {}).get("symbolic_health_baseline", {})
    checks = {
        "has_adaptive_examples": len(adaptive) >= 24,
        "has_behavior_holdout": bool(holdout.get("groups")),
        "hybrid_matches_or_beats_symbolic_holdout_brier": float(hybrid.get("brier", 1.0)) <= float(symbolic.get("brier", 0.0)) + 1e-9,
        "report_only": True,
    }
    readiness = "analysis_ready"
    if not checks["hybrid_matches_or_beats_symbolic_holdout_brier"]:
        readiness = "blocked_behavior_generalization"
    return {
        "schema": "adaptive_context_behavior_aware_scorer/v1",
        "description": "Report-only neural-symbolic behavior-aware scorer. Learned family routes are blended with symbolic health; unseen behavior families fall back to symbolic health.",
        "ok": all(checks.values()),
        "readiness": readiness,
        "dataset_path": str(dataset_path),
        "example_count": len(examples),
        "adaptive_example_count": len(adaptive),
        "skipped_count": len(skipped),
        "checks": checks,
        "evaluations": {
            "adaptive_behavior_holdout": holdout,
            "adaptive_random_split_reference": random_split_eval(adaptive, k=4) if len(adaptive) >= 8 else {},
        },
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    holdout = report["evaluations"]["adaptive_behavior_holdout"]
    lines = [
        "# Adaptive Context Behavior-Aware Scorer",
        "",
        "Report-only neural-symbolic scorer. It does not change runtime behavior, selector policy, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Adaptive examples: `{report['adaptive_example_count']}`",
        "",
        "## Behavior Holdout",
        "",
        "| model | accuracy | brier |",
        "| --- | ---: | ---: |",
    ]
    for key in ("hybrid", "symbolic_health_baseline"):
        row = holdout["weighted"][key]
        lines.append(f"| `{key}` | `{row['accuracy']}` | `{row['brier']}` |")
    lines.extend(["", "## Checks", "", "| check | pass |", "| --- | --- |"])
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a report-only behavior-aware adaptive-context scorer.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(Path(args.dataset))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "evaluations": report["evaluations"], "json": str(Path(args.out_json)), "markdown": str(Path(args.out_md))}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
