from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_DATASET = REPO_ROOT / "experiments" / "adaptive_context_outcome_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_dataset_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_dataset_guard_report.md"


ANSWER_FAMILIES = {
    "answer_quality",
    "answer_bridge_warning",
    "answer_missing_support",
    "answer_stale_conflict",
    "answer_citation",
}
OGCF_FAMILIES = {"ogcf_positive", "ogcf_negative", "answer_bridge_warning"}
RETRIEVAL_FAMILIES = {"retrieval_positive", "retrieval_negative"}


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read adaptive context dataset {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Adaptive context dataset must be a JSON object: {path}")
    return loaded


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def contains_mutation_markers(dataset: dict[str, Any]) -> bool:
    text = json.dumps(dataset, sort_keys=True).lower()
    markers = (
        '"mutates_config": true',
        '"mutates_runtime": true',
        '"mutates_db": true',
        '"promoted": true',
        '"auto_promote": true',
        '"config_patch"',
        '"selector_policy_patch"',
        '"resolver_weight_patch"',
    )
    return any(marker in text for marker in markers)


def example_issues(example: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    example_id = str(example.get("id") or "")
    scope = normalize_text(example.get("feedback_scope"))
    label = normalize_text(example.get("label"))
    family = normalize_text(example.get("outcome_family"))
    rating = float(example.get("rating") or 0.0)
    context_source = normalize_text(example.get("context_source"))
    retrieval_context = example.get("retrieval_context")
    diagnostics = example.get("diagnostics")
    features = example.get("features")

    if not example.get("linked_operation_id"):
        issues.append({"severity": "error", "id": example_id, "reason": "missing_linked_operation_id"})
    if scope not in {"answer", "memory"}:
        issues.append({"severity": "warning", "id": example_id, "reason": f"unusual_feedback_scope:{scope}"})
    if not label:
        issues.append({"severity": "error", "id": example_id, "reason": "missing_label"})
    if context_source not in {"adaptive_memory_context", "legacy_selector_snapshot"}:
        issues.append({"severity": "error", "id": example_id, "reason": f"invalid_context_source:{context_source}"})
    if not isinstance(retrieval_context, list) or not retrieval_context:
        issues.append({"severity": "error", "id": example_id, "reason": "missing_retrieval_context"})
    if not isinstance(diagnostics, dict):
        issues.append({"severity": "error", "id": example_id, "reason": "missing_diagnostics"})
    if context_source == "adaptive_memory_context" and not isinstance(features, dict):
        issues.append({"severity": "error", "id": example_id, "reason": "adaptive_context_missing_features"})
    if scope == "answer" and family not in ANSWER_FAMILIES:
        issues.append({"severity": "warning", "id": example_id, "reason": f"answer_scope_unexpected_family:{family}"})
    if scope == "memory" and family not in RETRIEVAL_FAMILIES | OGCF_FAMILIES | {"memory_feedback"} and not family.endswith("_feedback"):
        issues.append({"severity": "warning", "id": example_id, "reason": f"memory_scope_unexpected_family:{family}"})
    if label in {"answer_correct", "answer_good_citation", "useful", "good", "excellent"} and rating <= 0.0:
        issues.append({"severity": "error", "id": example_id, "reason": "positive_label_non_positive_rating"})
    if label in {"answer_stale", "answer_wrong_scope", "answer_missing_support", "answer_bad_citation", "answer_bridge_warning_noise", "stale", "wrong_domain"} and rating >= 0.0:
        issues.append({"severity": "warning", "id": example_id, "reason": "negative_label_non_negative_rating"})
    if family == "answer_bridge_warning" and not example.get("ogcf_meta_present"):
        issues.append({"severity": "warning", "id": example_id, "reason": "bridge_warning_without_ogcf_meta"})
    return issues


def readiness_for(dataset: dict[str, Any], issues: list[dict[str, Any]]) -> str:
    examples = dataset.get("examples") if isinstance(dataset.get("examples"), list) else []
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    if error_count:
        return "blocked"
    if not examples:
        return "empty"
    context_counts = Counter(str(item.get("context_source") or "") for item in examples if isinstance(item, dict))
    family_counts = Counter(str(item.get("outcome_family") or "") for item in examples if isinstance(item, dict))
    scope_counts = Counter(str(item.get("feedback_scope") or "") for item in examples if isinstance(item, dict))
    has_adaptive = int(context_counts.get("adaptive_memory_context", 0)) > 0
    has_answer = int(scope_counts.get("answer", 0)) > 0
    has_memory = int(scope_counts.get("memory", 0)) > 0
    has_ogcf = any(family in OGCF_FAMILIES for family in family_counts)
    if has_adaptive and has_answer and has_memory and has_ogcf and len(examples) >= 12:
        return "promotion_candidate"
    if has_adaptive and has_answer and has_memory:
        return "ready_for_runtime_collection"
    return "analysis_only"


def surface_readiness(dataset: dict[str, Any]) -> dict[str, Any]:
    examples = dataset.get("examples") if isinstance(dataset.get("examples"), list) else []
    families = Counter(str(item.get("outcome_family") or "") for item in examples if isinstance(item, dict))
    contexts = Counter(str(item.get("context_source") or "") for item in examples if isinstance(item, dict))
    return {
        "answer_behavior": {
            "example_count": sum(count for family, count in families.items() if family in ANSWER_FAMILIES),
            "families_present": sorted(family for family in ANSWER_FAMILIES if families.get(family)),
        },
        "retrieval_memory": {
            "example_count": sum(count for family, count in families.items() if family in RETRIEVAL_FAMILIES),
            "families_present": sorted(family for family in RETRIEVAL_FAMILIES if families.get(family)),
        },
        "ogcf": {
            "example_count": sum(count for family, count in families.items() if family in OGCF_FAMILIES),
            "families_present": sorted(family for family in OGCF_FAMILIES if families.get(family)),
        },
        "adaptive_context_examples": int(contexts.get("adaptive_memory_context", 0)),
        "legacy_context_examples": int(contexts.get("legacy_selector_snapshot", 0)),
    }


def build_report(dataset_path: Path) -> dict[str, Any]:
    dataset = read_json(dataset_path)
    if dataset.get("schema") != "adaptive_context_outcome_dataset/v1":
        return {
            "schema": "adaptive_context_dataset_guard/v1",
            "ok": False,
            "dataset_path": str(dataset_path),
            "readiness": "blocked",
            "error": f"Unsupported schema: {dataset.get('schema')}",
            "checks": {},
            "issues": [],
        }
    examples = [item for item in dataset.get("examples") or [] if isinstance(item, dict)]
    issues = [issue for example in examples for issue in example_issues(example)]
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    context_counts = Counter(str(item.get("context_source") or "") for item in examples)
    scope_counts = Counter(str(item.get("feedback_scope") or "") for item in examples)
    family_counts = Counter(str(item.get("outcome_family") or "") for item in examples)
    structural_checks = {
        "schema_ok": dataset.get("schema") == "adaptive_context_outcome_dataset/v1",
        "report_only_no_mutation": not contains_mutation_markers(dataset),
        "has_examples": bool(examples),
        "all_examples_linked": all(bool(item.get("linked_operation_id")) for item in examples),
        "all_examples_have_context": all(item.get("context_source") in {"adaptive_memory_context", "legacy_selector_snapshot"} for item in examples),
        "all_examples_have_retrieval_context": all(bool(item.get("retrieval_context")) for item in examples),
        "no_error_issues": not errors,
    }
    capability_checks = {
        "has_answer_feedback": int(scope_counts.get("answer", 0)) > 0,
        "has_memory_feedback": int(scope_counts.get("memory", 0)) > 0,
        "has_adaptive_context_example": int(context_counts.get("adaptive_memory_context", 0)) > 0,
        "has_ogcf_family": any(family in OGCF_FAMILIES for family in family_counts),
    }
    checks = {**structural_checks, **capability_checks}
    readiness = readiness_for(dataset, issues)
    return {
        "schema": "adaptive_context_dataset_guard/v1",
        "description": "Report-only guard/readiness assessment for adaptive-context outcome datasets.",
        "ok": all(structural_checks.values()),
        "dataset_path": str(dataset_path),
        "readiness": readiness,
        "example_count": len(examples),
        "checks": checks,
        "structural_checks": structural_checks,
        "capability_checks": capability_checks,
        "context_source_counts": dict(sorted(context_counts.items())),
        "feedback_scope_counts": dict(sorted(scope_counts.items())),
        "outcome_family_counts": dict(sorted(family_counts.items())),
        "surface_readiness": surface_readiness(dataset),
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues[:100],
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Dataset Guard",
        "",
        "This guard is advisory only. It does not promote config, runtime behavior, or learned models.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report.get('readiness')}`",
        f"Dataset: `{report.get('dataset_path')}`",
        f"Examples: `{report.get('example_count', 0)}`",
        f"Issues: `{report.get('issue_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Surface Readiness", "", "```json", json.dumps(report.get("surface_readiness"), indent=2), "```"])
    lines.extend(["", "## Issues", ""])
    if not report.get("issues"):
        lines.append("- None")
    for issue in report.get("issues") or []:
        lines.append(f"- `{issue.get('severity')}` `{issue.get('id')}`: `{issue.get('reason')}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard an adaptive-context outcome dataset before learning or promotion.")
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
                "readiness": report.get("readiness"),
                "example_count": report.get("example_count"),
                "error_count": report.get("error_count"),
                "warning_count": report.get("warning_count"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
