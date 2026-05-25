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

from core.config import load_config  # noqa: E402
from core.controller_context import build_adaptive_memory_context  # noqa: E402
from eval.adaptive_context_dataset_guard import build_report as build_dataset_guard_report  # noqa: E402
from eval.adaptive_context_dataset_guard import write_report as write_dataset_guard_report  # noqa: E402
from eval.adaptive_context_outcome_dataset import compact_retrieval, outcome_family  # noqa: E402
from eval.adaptive_context_semantic_shadow_live_style_eval import score_eval_examples  # noqa: E402
from eval.canonical_ogcf_production_shadow_eval import (  # noqa: E402
    apply_embedding_override,
    build_ogcf_meta,
    run_pipeline,
)
from storage.db import MemoryDB  # noqa: E402


NAMESPACE = "agent:rich-gemma-canonical-ogcf"
DEFAULT_DB = REPO_ROOT / "experiments" / "rich_gemma_raw_canonical_ogcf_fixture.db"
DEFAULT_QUERIES = REPO_ROOT / "experiments" / "rich_gemma_canonical_ogcf_queries.json"
TRAIN_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
SEMANTIC_GUARD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_results.json"
OUT_DATASET_JSON = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_dataset_results.json"
OUT_DATASET_MD = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_dataset_report.md"
OUT_DATASET_GUARD_JSON = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_dataset_guard_results.json"
OUT_DATASET_GUARD_MD = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_dataset_guard_report.md"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_gemma_shadow_eval_report.md"


LABELS = {
    "clean_selector_support": ("answer_correct", "useful"),
    "clean_weather_support": ("answer_correct", "useful"),
    "drink_current": ("answer_correct", "useful"),
    "drink_old": ("answer_stale", "stale"),
    "duplicate_pressure": ("answer_overconfident", "wrong_domain"),
    "project_current": ("answer_correct", "useful"),
    "project_old": ("answer_stale", "stale"),
    "bridge_weather": ("answer_bridge_warning_useful", "bridge_relevant"),
    "bridge_profile": ("answer_bridge_warning_useful", "bridge_relevant"),
    "bridge_ogcf": ("answer_bridge_warning_useful", "ogcf_geometry"),
    "robot_procedure": ("answer_correct", "useful"),
    "calendar": ("answer_bridge_warning_noise", "ogcf_false_positive"),
}


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


def load_queries(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"Unsupported query file shape: {path}")
    out = []
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            case_id = str(row.get("case_id") or f"case_{index:02d}")
            query = str(row.get("query") or "").strip()
        else:
            case_id = f"case_{index:02d}"
            query = str(row or "").strip()
        if query:
            out.append({"case_id": case_id, "query": query})
    return out


def db_signature(db_path: Path) -> dict[str, Any]:
    db = MemoryDB(db_path)
    try:
        signature = db.get_runtime_state("embedding_signature")
        stats = db.stats()
    finally:
        db.close()
    return {"embedding_signature": signature, "stats": stats}


def rating_for(label: str) -> float:
    return 1.0 if str(label).strip().lower() in POSITIVE_LABELS else -1.0


def selector_decision(context: Any) -> dict[str, Any]:
    decision = context.decision
    if decision is None:
        return {}
    return {
        "policy": decision.policy,
        "action": decision.action,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def make_example(
    *,
    case_id: str,
    query: str,
    scope: str,
    label: str,
    context: Any,
    linked_operation_id: str,
    feedback_operation_id: str,
) -> dict[str, Any]:
    selected_ids = [
        str(row.get("memory_id") or row.get("id"))
        for row in context.retrieval_context[:3]
        if row.get("memory_id") or row.get("id")
    ]
    decision = selector_decision(context)
    return {
        "id": f"adaptive_context_gemma_shadow_{feedback_operation_id}",
        "source_log": "synthetic_gemma_adaptive_context_fixture",
        "feedback_operation_id": feedback_operation_id,
        "linked_operation_id": linked_operation_id,
        "context_schema": "adaptive_memory_context/v1",
        "context_source": "adaptive_memory_context",
        "feedback_scope": scope,
        "label": label,
        "rating": rating_for(label),
        "outcome_family": outcome_family(label, scope),
        "query": query,
        "answer_preview": f"Gemma shadow fixture expected behavior for {case_id}.",
        "selected_memory_ids": selected_ids,
        "selector_policy": decision.get("policy"),
        "selector_action": decision.get("action"),
        "selector_reason": decision.get("reason"),
        "features": context.feature_dict(),
        "diagnostics": {
            key: context.diagnostics.get(key)
            for key in (
                "memory_bad_rate",
                "probe_drop",
                "csd_ratio",
                "stale_current_conflict",
                "contradiction_peak",
                "canonical_confidence_signal",
                "canonical_duplicate_pressure",
                "ogcf_bridge_overload_score",
                "ogcf_effective_affected_memory_ratio",
                "ogcf_intent",
                "ogcf_intent_score",
            )
            if key in context.diagnostics
        },
        "ogcf_meta_present": bool(context.ogcf_meta_present),
        "retrieval_context": compact_retrieval(context.retrieval_context),
        "resolver_shadow_actions": [],
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_dataset(
    *,
    db_path: Path,
    queries_path: Path,
    namespace: str,
    top_k: int,
    ogcf_sample_limit: int,
) -> dict[str, Any]:
    root_config = load_config(ROOT)
    config = apply_embedding_override(
        root_config,
        db_path=db_path,
        backend="auto",
        embedding_dim=None,
        embedding_normalize=False,
    )
    ogcf_meta = build_ogcf_meta(
        db_path,
        sample_limit=max(12, int(ogcf_sample_limit)),
        normalize_embeddings=False,
    )
    queries = load_queries(queries_path)
    examples: list[dict[str, Any]] = []
    retrieval_counts: dict[str, int] = {}
    skipped: list[dict[str, Any]] = []
    pipeline = run_pipeline(db_path, canonical_enabled=True, config=config)
    try:
        for index, item in enumerate(queries, start=1):
            case_id = item["case_id"]
            query = item["query"]
            labels = LABELS.get(case_id)
            if labels is None:
                skipped.append({"case_id": case_id, "reason": "missing_labels"})
                continue
            rows = pipeline.retrieve(query, top_k=top_k, namespace=namespace, include_global=True)
            retrieval_counts[case_id] = len(rows)
            payload = {
                "query": query,
                "condition_name": "hard_budget144",
                "namespace": namespace,
                "include_global": True,
                "top_k": top_k,
                "ogcf_meta": ogcf_meta,
            }
            context = build_adaptive_memory_context(
                root=ROOT,
                config=config,
                payload=payload,
                retrieval_rows=rows,
                include_decision=True,
            )
            if not context.ok:
                skipped.append({"case_id": case_id, "reason": "context_error", "error": context.error})
                continue
            answer_label, memory_label = labels
            linked = f"gemma_shadow_ask_{index:02d}_{case_id}"
            examples.append(
                make_example(
                    case_id=case_id,
                    query=query,
                    scope="answer",
                    label=answer_label,
                    context=context,
                    linked_operation_id=linked,
                    feedback_operation_id=f"{linked}_answer_feedback",
                )
            )
            examples.append(
                make_example(
                    case_id=case_id,
                    query=query,
                    scope="memory",
                    label=memory_label,
                    context=context,
                    linked_operation_id=linked,
                    feedback_operation_id=f"{linked}_memory_feedback",
                )
            )
    finally:
        pipeline.close()

    context_counts = Counter(str(item.get("context_source")) for item in examples)
    scope_counts = Counter(str(item.get("feedback_scope")) for item in examples)
    family_counts = Counter(str(item.get("outcome_family")) for item in examples)
    label_counts = Counter(str(item.get("label")) for item in examples)
    return {
        "schema": "adaptive_context_outcome_dataset/v1",
        "description": "Gemma-backed adaptive-context shadow holdout built from real Gemma retrieval over the rich canonical/OGCF fixture.",
        "ok": bool(examples) and all(count > 0 for count in retrieval_counts.values()),
        "source_kind": "gemma_retrieval_fixture",
        "db_path": str(db_path),
        "queries_path": str(queries_path),
        "namespace": namespace,
        "top_k": int(top_k),
        "ogcf_sample_limit": int(ogcf_sample_limit),
        "embedding": db_signature(db_path),
        "ogcf_meta_summary": {
            "ok": ogcf_meta.get("ok"),
            "vector_count": ogcf_meta.get("vector_count"),
            "bridge_cluster_count": len(ogcf_meta.get("bridge_clusters") or []),
            "bridge_overload_score": ogcf_meta.get("bridge_overload_score"),
            "max_interaction_z": ogcf_meta.get("max_interaction_z"),
        },
        "retrieval_counts": retrieval_counts,
        "example_count": len(examples),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "context_source_counts": dict(sorted(context_counts.items())),
        "feedback_scope_counts": dict(sorted(scope_counts.items())),
        "outcome_family_counts": dict(sorted(family_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "examples": examples,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_dataset_report(dataset: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Gemma Shadow Dataset",
        "",
        "Report-only Gemma-backed adaptive-context holdout. It does not change runtime behavior, memory rows, or config.",
        "",
        f"Passed: **{dataset['ok']}**",
        f"Examples: `{dataset['example_count']}`",
        f"DB: `{dataset['db_path']}`",
        f"Namespace: `{dataset['namespace']}`",
        "",
        "## Retrieval Counts",
        "",
        "```json",
        json.dumps(dataset["retrieval_counts"], indent=2),
        "```",
        "",
        "## Labels",
        "",
        "```json",
        json.dumps(dataset["label_counts"], indent=2),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_eval_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Gemma Semantic Shadow Eval",
        "",
        "Gemma-backed retrieval holdout evaluated with the report-only semantic shadow controller.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Examples: `{report['eval']['eval_count']}`",
        f"Actioned precision: `{report['eval']['actioned_precision']}`",
        f"Coverage: `{report['eval']['coverage']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "```json",
            json.dumps(
                {
                    "advisory": report["eval"]["advisory_counts"],
                    "routes": report["eval"]["route_counts"],
                    "labels": report["dataset"]["label_counts"],
                },
                indent=2,
            ),
            "```",
            "",
            "## Sample Decisions",
            "",
            "| advisory | route | behavior | probability | label |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for item in report["eval"].get("decisions", [])[:24]:
        lines.append(
            f"| `{item['advisory']}` | `{item['route']}` | `{item['behavior_group']}` | "
            f"`{item['shadow_probability']}` | `{item['label']}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the semantic adaptive shadow controller on real Gemma retrieval.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--queries-json", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--ogcf-sample-limit", type=int, default=384)
    parser.add_argument("--train-dataset", type=Path, default=TRAIN_DATASET)
    parser.add_argument("--semantic-guard", type=Path, default=SEMANTIC_GUARD)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    dataset = build_dataset(
        db_path=args.db_path.resolve(),
        queries_path=args.queries_json.resolve(),
        namespace=args.namespace,
        top_k=args.top_k,
        ogcf_sample_limit=args.ogcf_sample_limit,
    )
    write_dataset_report(dataset, OUT_DATASET_JSON, OUT_DATASET_MD)
    dataset_guard = build_dataset_guard_report(OUT_DATASET_JSON)
    write_dataset_guard_report(dataset_guard, OUT_DATASET_GUARD_JSON, OUT_DATASET_GUARD_MD)
    evaluation = score_eval_examples(
        args.train_dataset,
        OUT_DATASET_JSON,
        args.semantic_guard,
        load_config(ROOT).get("adaptive_behavior"),
    )
    embedding_sig = ((dataset.get("embedding") or {}).get("embedding_signature") or {})
    retrieval_counts = list((dataset.get("retrieval_counts") or {}).values())
    checks = {
        "dataset_ok": dataset.get("ok") is True,
        "dataset_guard_ok": dataset_guard.get("ok") is True,
        "dataset_guard_promotion_candidate": dataset_guard.get("readiness") == "promotion_candidate",
        "all_adaptive_context": dataset.get("context_source_counts") == {"adaptive_memory_context": dataset.get("example_count")},
        "gemma_backend": embedding_sig.get("backend") == "wsl_llama_cpp",
        "gemma_dim_768": embedding_sig.get("embedding_dim") == 768,
        "retrieval_coverage_full": bool(retrieval_counts) and min(retrieval_counts) > 0,
        "semantic_guard_promotion_candidate": evaluation.get("guard_readiness") == "promotion_candidate",
        "has_actioned_advisories": int(evaluation.get("actioned_count") or 0) > 0,
        "actioned_precision_at_least_0_70": float(evaluation.get("actioned_precision") or 0.0) >= 0.70,
        "coverage_at_least_0_20": float(evaluation.get("coverage") or 0.0) >= 0.20,
        "report_only": evaluation.get("mutates_runtime") is False and evaluation.get("mutates_config") is False,
    }
    report = {
        "schema": "adaptive_context_gemma_shadow_eval/v1",
        "ok": all(checks.values()),
        "readiness": "gemma_shadow_candidate" if all(checks.values()) else "needs_more_gemma_shadow_validation",
        "checks": checks,
        "dataset_json": str(OUT_DATASET_JSON),
        "dataset_guard_json": str(OUT_DATASET_GUARD_JSON),
        "dataset": {
            key: dataset.get(key)
            for key in (
                "db_path",
                "namespace",
                "example_count",
                "retrieval_counts",
                "label_counts",
                "outcome_family_counts",
                "ogcf_meta_summary",
                "embedding",
            )
        },
        "dataset_guard": {
            "ok": dataset_guard.get("ok"),
            "readiness": dataset_guard.get("readiness"),
            "issue_count": dataset_guard.get("issue_count"),
            "warning_count": dataset_guard.get("warning_count"),
        },
        "eval": evaluation,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    write_eval_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "readiness": report["readiness"],
                "checks": checks,
                "eval_summary": {
                    key: evaluation[key]
                    for key in ("eval_count", "advisory_counts", "route_counts", "actioned_count", "actioned_precision", "coverage")
                },
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
