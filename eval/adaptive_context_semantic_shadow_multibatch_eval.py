from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config
from eval.adaptive_context_dataset_guard import build_report as build_dataset_guard_report
from eval.adaptive_context_dataset_guard import write_report as write_dataset_guard_report
from eval.adaptive_context_outcome_dataset import build_report as build_dataset_report
from eval.adaptive_context_outcome_dataset import write_report as write_dataset_report
from eval.adaptive_context_semantic_shadow_live_style_eval import (
    SCENARIOS,
    ask_and_feedback,
    score_eval_examples,
    teach,
)
from eval.outcome_logging_regression import build_test_api


TRAIN_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
SEMANTIC_GUARD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_multibatch_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_multibatch_eval_report.md"


BATCH_PROFILES = [
    {
        "name": "ops_shift",
        "query_prefix": "During the morning operations shift, ",
        "memory_prefix": "Morning shift evidence",
        "indices": [0, 1, 2, 3, 4, 5, 6, 7],
    },
    {
        "name": "audit_review",
        "query_prefix": "For a controller audit review, ",
        "memory_prefix": "Audit review evidence",
        "indices": [0, 2, 3, 4, 5, 7, 8, 9],
    },
    {
        "name": "incident_handoff",
        "query_prefix": "In an incident handoff, ",
        "memory_prefix": "Incident handoff evidence",
        "indices": [1, 2, 3, 4, 5, 6, 8, 9],
    },
]


def scenario_variant(base: dict[str, Any], profile: dict[str, Any], batch_index: int) -> dict[str, Any]:
    scenario = dict(base)
    scenario["name"] = f"{profile['name']}_b{batch_index}_{base['name']}"
    scenario["query"] = f"{profile['query_prefix']}{base['query']}"
    scenario["memories"] = [
        f"{profile['memory_prefix']} {index}: {text}"
        for index, text in enumerate(base["memories"], start=1)
    ]
    return scenario


def batch_scenarios(profile: dict[str, Any], batch_index: int) -> list[dict[str, Any]]:
    return [scenario_variant(SCENARIOS[index], profile, batch_index) for index in profile["indices"]]


def generate_batch_log(profile: dict[str, Any], batch_index: int) -> tuple[Path, list[dict[str, Any]]]:
    out_log = REPO_ROOT / "experiments" / f"adaptive_context_semantic_shadow_multibatch_{profile['name']}.jsonl"
    with tempfile.TemporaryDirectory(prefix=f"adaptive_shadow_multibatch_{profile['name']}_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        runs: list[dict[str, Any]] = []
        try:
            for scenario in batch_scenarios(profile, batch_index):
                memory_ids = teach(api, scenario)
                runs.append(ask_and_feedback(api, scenario, memory_ids))
            out_log.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(api.outcome_logger.path, out_log)
        finally:
            api.close()
    return out_log, runs


def evaluate_batch(profile: dict[str, Any], batch_index: int, train_dataset: Path, semantic_guard: Path) -> dict[str, Any]:
    log_path, runs = generate_batch_log(profile, batch_index)
    dataset_json = REPO_ROOT / "experiments" / f"adaptive_context_semantic_shadow_multibatch_{profile['name']}_dataset_results.json"
    dataset_md = REPO_ROOT / "experiments" / f"adaptive_context_semantic_shadow_multibatch_{profile['name']}_dataset_report.md"
    guard_json = REPO_ROOT / "experiments" / f"adaptive_context_semantic_shadow_multibatch_{profile['name']}_dataset_guard_results.json"
    guard_md = REPO_ROOT / "experiments" / f"adaptive_context_semantic_shadow_multibatch_{profile['name']}_dataset_guard_report.md"
    dataset = build_dataset_report([log_path])
    write_dataset_report(dataset, dataset_json, dataset_md)
    dataset_guard = build_dataset_guard_report(dataset_json)
    write_dataset_guard_report(dataset_guard, guard_json, guard_md)
    evaluation = score_eval_examples(train_dataset, dataset_json, semantic_guard, load_config(ROOT).get("adaptive_behavior"))
    checks = {
        "dataset_ok": dataset.get("ok") is True,
        "dataset_guard_ok": dataset_guard.get("ok") is True,
        "all_adaptive_context": dataset.get("context_source_counts") == {"adaptive_memory_context": dataset.get("example_count")},
        "precision_at_least_0_70": float(evaluation.get("actioned_precision") or 0.0) >= 0.70,
        "coverage_at_least_0_25": float(evaluation.get("coverage") or 0.0) >= 0.25,
        "report_only": evaluation.get("mutates_runtime") is False and evaluation.get("mutates_config") is False,
    }
    return {
        "batch": profile["name"],
        "ok": all(checks.values()),
        "checks": checks,
        "log_path": str(log_path),
        "dataset_json": str(dataset_json),
        "dataset_guard_json": str(guard_json),
        "scenario_runs": runs,
        "eval": evaluation,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Multibatch Eval",
        "",
        "Fresh multi-batch validation. Each batch is generated in a separate temporary runtime and evaluated against the same trained semantic shadow controller.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Batches: `{len(report['batches'])}`",
        "",
        "| batch | ok | examples | precision | coverage | advisories |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for batch in report["batches"]:
        evaluation = batch["eval"]
        lines.append(
            f"| `{batch['batch']}` | `{batch['ok']}` | `{evaluation['eval_count']}` | "
            f"`{evaluation['actioned_precision']}` | `{evaluation['coverage']}` | "
            f"`{json.dumps(evaluation['advisory_counts'], sort_keys=True)}` |"
        )
    lines.extend(["", "## Checks", "", "| check | pass |", "| --- | --- |"])
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-batch fresh validation for the semantic shadow controller.")
    parser.add_argument("--train-dataset", default=str(TRAIN_DATASET))
    parser.add_argument("--semantic-guard", default=str(SEMANTIC_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    batches = [
        evaluate_batch(profile, index, Path(args.train_dataset), Path(args.semantic_guard))
        for index, profile in enumerate(BATCH_PROFILES, start=1)
    ]
    total_examples = sum(int(batch["eval"]["eval_count"]) for batch in batches)
    total_actioned = sum(int(batch["eval"]["actioned_count"]) for batch in batches)
    weighted_precision = (
        sum(float(batch["eval"]["actioned_precision"]) * int(batch["eval"]["actioned_count"]) for batch in batches)
        / max(1, total_actioned)
    )
    weighted_coverage = total_actioned / max(1, total_examples)
    checks = {
        "all_batches_ok": all(batch["ok"] for batch in batches),
        "batch_count_at_least_3": len(batches) >= 3,
        "total_examples_at_least_40": total_examples >= 40,
        "weighted_precision_at_least_0_80": weighted_precision >= 0.80,
        "weighted_coverage_at_least_0_25": weighted_coverage >= 0.25,
        "all_report_only": all(batch["eval"].get("mutates_runtime") is False and batch["eval"].get("mutates_config") is False for batch in batches),
    }
    report = {
        "schema": "adaptive_context_semantic_shadow_multibatch_eval/v1",
        "ok": all(checks.values()),
        "readiness": "multibatch_shadow_candidate" if all(checks.values()) else "needs_more_shadow_validation",
        "checks": checks,
        "summary": {
            "total_examples": total_examples,
            "total_actioned": total_actioned,
            "weighted_precision": round(weighted_precision, 6),
            "weighted_coverage": round(weighted_coverage, 6),
        },
        "batches": batches,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "readiness": report["readiness"],
                "summary": report["summary"],
                "checks": checks,
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
