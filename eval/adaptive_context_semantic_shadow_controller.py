from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_behavior import normalize_adaptive_behavior_config, superfamily_for_label
from core.config import load_config
from eval.adaptive_context_behavior_aware_scorer import family_predict
from eval.adaptive_context_semantic_behavior_scorer import train_models
from eval.adaptive_context_tiny_scorer import (
    answer_label_by_operation,
    behavior_group,
    load_examples,
    read_json,
    symbolic_health_prob,
)


DEFAULT_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
DEFAULT_GUARD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_controller_report.md"


def route_confidence(model: dict[str, Any] | None) -> float:
    if not model:
        return 0.0
    confidence = min(0.8, math.log1p(float(model.get("count", 0))) / 3.6)
    if not model.get("can_learn"):
        confidence = min(confidence, 0.35)
    return round(confidence, 6)


def advisory_from_probability(probability: float, shadow_cfg: dict[str, Any]) -> str:
    if probability >= float(shadow_cfg["positive_threshold"]):
        return "likely_helpful"
    if probability <= float(shadow_cfg["negative_threshold"]):
        return "likely_harmful"
    return "uncertain_keep_symbolic"


def build_shadow_decisions(
    examples: list[dict[str, Any]],
    behavior_config: dict[str, Any],
) -> list[dict[str, Any]]:
    answer_labels = answer_label_by_operation(examples)
    exact_models, super_models = train_models(examples, answer_labels, behavior_config)
    shadow_cfg = behavior_config["shadow"]
    out: list[dict[str, Any]] = []
    for example in examples:
        exact = behavior_group(example, answer_labels)
        superfamily = superfamily_for_label(exact, behavior_config)
        symbolic = symbolic_health_prob(example)
        model = exact_models.get(exact)
        route = "symbolic_unseen_family"
        if model is None:
            model = super_models.get(superfamily)
            route = "superfamily_model" if model and model.get("can_learn") else "superfamily_prior_blend"
        else:
            route = "exact_family_model" if model.get("can_learn") else "exact_family_prior_blend"

        confidence = route_confidence(model)
        if model is None:
            learned = None
            probability = symbolic
        else:
            learned = family_predict(model, [example])[0]
            probability = confidence * learned + (1.0 - confidence) * symbolic

        advisory = advisory_from_probability(probability, shadow_cfg)
        if confidence < float(shadow_cfg["min_route_confidence"]):
            advisory = "uncertain_keep_symbolic"
        out.append(
            {
                "id": example.get("id"),
                "linked_operation_id": example.get("linked_operation_id"),
                "feedback_scope": example.get("feedback_scope"),
                "label": example.get("label"),
                "target": int(example["_target"]),
                "behavior_group": exact,
                "superfamily": superfamily,
                "route": route,
                "route_confidence": confidence,
                "learned_probability": None if learned is None else round(float(learned), 6),
                "symbolic_probability": round(float(symbolic), 6),
                "shadow_probability": round(float(probability), 6),
                "advisory": advisory,
                "mutates_runtime": False,
                "mutates_config": False,
            }
        )
    return out


def build_report(dataset_path: Path, guard_path: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    dataset = read_json(dataset_path)
    guard = read_json(guard_path)
    if dataset.get("schema") != "adaptive_context_outcome_dataset/v1":
        raise ValueError(f"Unsupported dataset schema: {dataset.get('schema')}")
    behavior_config = normalize_adaptive_behavior_config(config)
    examples, skipped = load_examples(dataset)
    adaptive = [item for item in examples if item.get("context_source") == "adaptive_memory_context"]
    decisions = build_shadow_decisions(adaptive, behavior_config)
    advisory_counts = Counter(item["advisory"] for item in decisions)
    route_counts = Counter(item["route"] for item in decisions)
    checks = {
        "guard_promotion_candidate": guard.get("readiness") == "promotion_candidate",
        "config_schema_ok": behavior_config.get("schema") == "adaptive_behavior_config/v1",
        "shadow_disabled_by_default": behavior_config.get("shadow", {}).get("enabled") is False,
        "has_shadow_decisions": bool(decisions),
        "all_report_only": all(item.get("mutates_runtime") is False and item.get("mutates_config") is False for item in decisions),
        "has_non_symbolic_routes": any(str(item.get("route")) in {"exact_family_model", "superfamily_model"} for item in decisions),
    }
    return {
        "schema": "adaptive_context_semantic_shadow_controller/v1",
        "description": "Report-only shadow controller artifact for semantic adaptive behavior scoring.",
        "ok": all(checks.values()),
        "readiness": "shadow_candidate" if all(checks.values()) else "blocked",
        "dataset_path": str(dataset_path),
        "guard_path": str(guard_path),
        "example_count": len(examples),
        "adaptive_example_count": len(adaptive),
        "skipped_count": len(skipped),
        "behavior_config": behavior_config,
        "checks": checks,
        "advisory_counts": dict(sorted(advisory_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "decisions": decisions,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Controller",
        "",
        "Report-only shadow controller artifact. It does not change runtime behavior, selector policy, memory rows, or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Adaptive examples: `{report['adaptive_example_count']}`",
        "",
        "## Counts",
        "",
        "```json",
        json.dumps({"advisory": report["advisory_counts"], "routes": report["route_counts"]}, indent=2),
        "```",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Sample Decisions", "", "| advisory | route | behavior | probability | label |", "| --- | --- | --- | ---: | --- |"])
    for item in report.get("decisions", [])[:24]:
        lines.append(
            f"| `{item['advisory']}` | `{item['route']}` | `{item['behavior_group']}` | "
            f"`{item['shadow_probability']}` | `{item['label']}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report-only semantic adaptive behavior shadow-controller artifact.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(Path(args.dataset), Path(args.guard), load_config(ROOT).get("adaptive_behavior"))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "readiness": report["readiness"],
                "advisory_counts": report["advisory_counts"],
                "route_counts": report["route_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
