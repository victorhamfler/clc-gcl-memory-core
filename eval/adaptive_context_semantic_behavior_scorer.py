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

from core.adaptive_behavior import normalize_adaptive_behavior_config, superfamily_for_label
from core.config import load_config
from eval.adaptive_context_behavior_aware_scorer import train_family_model, family_predict
from eval.adaptive_context_tiny_scorer import (
    answer_label_by_operation,
    behavior_group,
    evaluate_probs,
    load_examples,
    read_json,
    symbolic_health_prob,
)


DEFAULT_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_report.md"


def symbolic_probs(examples: list[dict[str, Any]]) -> list[float]:
    return [symbolic_health_prob(example) for example in examples]


def superfamily_for(group: str, behavior_config: dict[str, Any]) -> str:
    return superfamily_for_label(group, behavior_config)


def train_models(
    train: list[dict[str, Any]],
    answer_labels: dict[str, str],
    behavior_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_super: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in train:
        exact = behavior_group(example, answer_labels)
        by_exact[exact].append(example)
        by_super[superfamily_for(exact, behavior_config)].append(example)
    return (
        {name: train_family_model(items) for name, items in by_exact.items()},
        {name: train_family_model(items) for name, items in by_super.items()},
    )


def predict_semantic(
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    answer_labels: dict[str, str],
    behavior_config: dict[str, Any],
) -> tuple[list[float], list[dict[str, Any]]]:
    exact_models, super_models = train_models(train, answer_labels, behavior_config)
    probs: list[float] = []
    routes: list[dict[str, Any]] = []
    for example in test:
        exact = behavior_group(example, answer_labels)
        superfamily = superfamily_for(exact, behavior_config)
        symbolic = symbolic_health_prob(example)
        model = exact_models.get(exact)
        route = "symbolic_unseen_family"
        if model is None:
            model = super_models.get(superfamily)
            route = "superfamily_model" if model and model.get("can_learn") else "superfamily_prior_blend"
        else:
            route = "exact_family_model" if model.get("can_learn") else "exact_family_prior_blend"

        if model is None:
            prob = symbolic
        else:
            learned = family_predict(model, [example])[0]
            confidence = min(0.8, math.log1p(float(model.get("count", 0))) / 3.6)
            if not model.get("can_learn"):
                confidence = min(confidence, 0.35)
            prob = confidence * learned + (1.0 - confidence) * symbolic
        probs.append(prob)
        routes.append(
            {
                "id": example.get("id"),
                "behavior_group": exact,
                "superfamily": superfamily,
                "route": route,
                "probability": round(prob, 6),
            }
        )
    return probs, routes


def behavior_holdout(examples: list[dict[str, Any]], behavior_config: dict[str, Any]) -> dict[str, Any]:
    answer_labels = answer_label_by_operation(examples)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        groups[behavior_group(example, answer_labels)].append(example)

    rows: list[dict[str, Any]] = []
    all_semantic: list[float] = []
    all_symbolic: list[float] = []
    all_y: list[int] = []
    for group_name in sorted(groups):
        test = groups[group_name]
        train = [item for name, group in groups.items() if name != group_name for item in group]
        if len(train) < 8 or len(test) < 2 or len({item["_target"] for item in train}) < 2:
            continue
        probs, routes = predict_semantic(train, test, answer_labels, behavior_config)
        symbolic = symbolic_probs(test)
        ys = [int(item["_target"]) for item in test]
        all_semantic.extend(probs)
        all_symbolic.extend(symbolic)
        all_y.extend(ys)
        rows.append(
            {
                "heldout_group": group_name,
                "superfamily": superfamily_for(group_name, behavior_config),
                "test_count": len(test),
                "semantic_hybrid": evaluate_probs(probs, ys),
                "symbolic_health_baseline": evaluate_probs(symbolic, ys),
                "routes": routes[:8],
            }
        )

    return {
        "groups": len(rows),
        "test_count": len(all_y),
        "weighted": {
            "semantic_hybrid": evaluate_probs(all_semantic, all_y),
            "symbolic_health_baseline": evaluate_probs(all_symbolic, all_y),
        },
        "group_results": rows,
    }


def build_report(dataset_path: Path, behavior_config: dict[str, Any] | None = None) -> dict[str, Any]:
    dataset = read_json(dataset_path)
    if dataset.get("schema") != "adaptive_context_outcome_dataset/v1":
        raise ValueError(f"Unsupported dataset schema: {dataset.get('schema')}")
    normalized_behavior = normalize_adaptive_behavior_config(behavior_config)
    examples, skipped = load_examples(dataset)
    adaptive = [item for item in examples if item.get("context_source") == "adaptive_memory_context"]
    holdout = behavior_holdout(adaptive, normalized_behavior)
    semantic = holdout["weighted"]["semantic_hybrid"]
    symbolic = holdout["weighted"]["symbolic_health_baseline"]
    checks = {
        "has_adaptive_examples": len(adaptive) >= 24,
        "has_behavior_holdout": bool(holdout.get("groups")),
        "semantic_beats_symbolic_brier": float(semantic.get("brier", 1.0)) < float(symbolic.get("brier", 0.0)),
        "report_only": True,
    }
    readiness = "analysis_ready" if all(checks.values()) else "needs_more_behavior_signal"
    return {
        "schema": "adaptive_context_semantic_behavior_scorer/v1",
        "description": "Report-only semantic behavior-family scorer. Exact behavior labels are mapped into broader behavior superfamilies before learned scoring.",
        "ok": all(checks.values()),
        "readiness": readiness,
        "dataset_path": str(dataset_path),
        "example_count": len(examples),
        "adaptive_example_count": len(adaptive),
        "skipped_count": len(skipped),
        "behavior_config": normalized_behavior,
        "checks": checks,
        "evaluations": {"adaptive_behavior_holdout": holdout},
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    holdout = report["evaluations"]["adaptive_behavior_holdout"]
    lines = [
        "# Adaptive Context Semantic Behavior Scorer",
        "",
        "Report-only semantic behavior-family scorer. It does not change runtime behavior, selector policy, or config.",
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
    for key in ("semantic_hybrid", "symbolic_health_baseline"):
        row = holdout["weighted"][key]
        lines.append(f"| `{key}` | `{row['accuracy']}` | `{row['brier']}` |")
    lines.extend(["", "## Checks", "", "| check | pass |", "| --- | --- |"])
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a report-only semantic behavior-family adaptive scorer.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(Path(args.dataset), load_config(ROOT).get("adaptive_behavior"))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "evaluations": report["evaluations"], "json": str(Path(args.out_json)), "markdown": str(Path(args.out_md))}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
