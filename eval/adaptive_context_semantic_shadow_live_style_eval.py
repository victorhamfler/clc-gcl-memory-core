from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_behavior import normalize_adaptive_behavior_config, superfamily_for_label
from core.config import load_config
from eval.adaptive_context_behavior_aware_scorer import family_predict
from eval.adaptive_context_dataset_guard import build_report as build_dataset_guard_report
from eval.adaptive_context_dataset_guard import write_report as write_dataset_guard_report
from eval.adaptive_context_outcome_dataset import build_report as build_dataset_report
from eval.adaptive_context_outcome_dataset import write_report as write_dataset_report
from eval.adaptive_context_semantic_behavior_guard import build_report as build_semantic_guard_report
from eval.adaptive_context_semantic_shadow_controller import advisory_from_probability, route_confidence
from eval.adaptive_context_semantic_behavior_scorer import train_models
from eval.adaptive_context_tiny_scorer import answer_label_by_operation, behavior_group, load_examples, read_json, symbolic_health_prob
from eval.outcome_logging_regression import build_test_api


TRAIN_DATASET = REPO_ROOT / "experiments" / "adaptive_context_rich_runtime_dataset_results.json"
SEMANTIC_GUARD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_results.json"
OUT_LOG = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_examples.jsonl"
OUT_DATASET_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_dataset_results.json"
OUT_DATASET_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_dataset_report.md"
OUT_DATASET_GUARD_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_dataset_guard_results.json"
OUT_DATASET_GUARD_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_dataset_guard_report.md"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_shadow_live_style_eval_report.md"


NAMESPACE = "agent:adaptive-shadow-live-style"
AGENT_ID = "adaptive-shadow-live-style-agent"


SCENARIOS = [
    {
        "name": "operations_summary_supported",
        "memories": [
            "Live-style controller note: status summaries must use selected memory evidence before calling a task ready.",
            "Live-style evidence note: a supported operational answer should quote the retrieved status note.",
        ],
        "query": "For today's operator summary, what evidence should decide whether a task is ready?",
        "answer_label": "answer_correct",
        "memory_label": "useful",
    },
    {
        "name": "handover_citation_good",
        "memories": [
            "Live-style citation rule: handover answers should cite only selected memory rows.",
            "Live-style citation support: unselected notes are context, not evidence citations.",
        ],
        "query": "In the next handover, what should count as citation support?",
        "answer_label": "answer_good_citation",
        "memory_label": "good",
    },
    {
        "name": "unlisted_budget_missing",
        "memories": [
            "Live-style unrelated note: the UI theme review prefers compact spacing.",
            "Live-style unrelated note: weekly coffee inventory is checked on Monday.",
        ],
        "query": "What exact GPU budget was approved for the unlisted drone rehearsal?",
        "answer_label": "answer_missing_support",
        "memory_label": "wrong_domain",
    },
    {
        "name": "bridge_synthesis_useful",
        "memories": [
            "Live-style OGCF note: alert routing and weather-risk memories can form a cross-domain bridge.",
            "Live-style OGCF geometry: shared affected clusters make bridge warnings useful during synthesis.",
        ],
        "query": "Explain whether alert routing and weather-risk memories form a useful bridge.",
        "answer_label": "answer_bridge_warning_useful",
        "memory_label": "bridge_relevant",
        "ogcf": True,
    },
    {
        "name": "ordinary_bridge_room_noise",
        "memories": [
            "Live-style ordinary note: Bridge Lab is the room for the maintenance review.",
            "Live-style ordinary note: the maintenance review starts at 14:00 in Bridge Lab.",
        ],
        "query": "Where is the maintenance review located?",
        "answer_label": "answer_bridge_warning_noise",
        "memory_label": "ogcf_false_positive",
        "ogcf": True,
        "ordinary": True,
    },
    {
        "name": "current_rule_stale",
        "memories": [
            "Live-style old rule: bridge warnings can be omitted when a single selected row looks strong.",
            "Live-style current rule: bridge warnings should be disclosed when OGCF pressure is high.",
        ],
        "query": "What is the current rule for bridge warnings under high OGCF pressure?",
        "answer_label": "answer_stale",
        "memory_label": "stale",
    },
    {
        "name": "threshold_conflict",
        "memories": [
            "Live-style threshold note A: keep strict bridge thresholds for controller shadow tests.",
            "Live-style threshold note B: keep default bridge thresholds until more live logs exist.",
        ],
        "query": "Which bridge threshold should the controller use right now?",
        "answer_label": "answer_conflict_not_disclosed",
        "memory_label": "stale",
    },
    {
        "name": "citation_trap_bad",
        "memories": [
            "Live-style citation trap: generated summaries are not citations unless selected as evidence.",
            "Live-style citation trap: source labels should not be invented for unsupported claims.",
        ],
        "query": "Can generated summaries be cited as evidence if they were not selected?",
        "answer_label": "answer_bad_citation",
        "memory_label": "useful",
    },
    {
        "name": "robot_schedule_supported",
        "memories": [
            "Live-style robotics status: calibration rehearsal is ready only after the safety checklist memory is selected.",
            "Live-style robotics evidence: readiness answers should include the selected checklist evidence.",
        ],
        "query": "When can the calibration rehearsal be called ready?",
        "answer_label": "answer_correct",
        "memory_label": "useful",
    },
    {
        "name": "ordinary_policy_wrong_scope",
        "memories": [
            "Live-style repository rule: GitHub uploads need explicit approval in the active conversation.",
            "Live-style calendar rule: calendar changes are separate from repository upload approval.",
        ],
        "query": "Does a calendar approval also approve a GitHub upload?",
        "answer_label": "answer_wrong_scope",
        "memory_label": "wrong_domain",
    },
]


def scenario_namespace(name: str) -> str:
    return f"{NAMESPACE}:{name}"


def ogcf_meta(memory_ids: list[str], *, ordinary: bool = False) -> dict[str, Any]:
    return {
        "bridge_overload_score": 0.82 if not ordinary else 0.68,
        "max_interaction_z": 2.45,
        "loop_count": 4,
        "cluster_summary": [{"cluster_id": 11}, {"cluster_id": 12}],
        "bridge_clusters": [{"cluster_id": 11}],
        "risk_regions": [{"clusters": "11-12", "interaction_z": 2.4}],
        "memory_cluster_map": {memory_id: 11 if index == 0 else 12 for index, memory_id in enumerate(memory_ids)},
    }


def teach(api: Any, scenario: dict[str, Any]) -> list[str]:
    memory_ids = []
    for index, text in enumerate(scenario["memories"], start=1):
        taught = api.teach(
            {
                "text": text,
                "namespace": scenario_namespace(scenario["name"]),
                "agent_id": AGENT_ID,
                "source": f"eval/adaptive_context_semantic_shadow_live_style/{scenario['name']}.md",
                "memory_type": "semantic_note",
                "domain_name": "adaptive_shadow_live_style",
                "metadata": {"scenario": scenario["name"], "fixture_index": index},
            }
        )
        memory_ids.append(str(taught["memory"]["memory_id"]))
    return memory_ids


def ask_and_feedback(api: Any, scenario: dict[str, Any], memory_ids: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": scenario["query"],
        "namespace": scenario_namespace(scenario["name"]),
        "include_global": False,
        "agent_id": AGENT_ID,
        "top_k": 5,
        "include_resolver_shadow": True,
        "condition_name": "hard_budget144",
    }
    if scenario.get("ogcf"):
        payload["ogcf_meta"] = ogcf_meta(memory_ids, ordinary=bool(scenario.get("ordinary")))
    asked = api.ask(payload)
    evidence = asked.get("evidence") or []
    selected_ids = [str(row.get("memory_id")) for row in evidence if row.get("memory_id")]
    target_memory_id = selected_ids[0] if selected_ids else memory_ids[0]
    retrieval_score = evidence[0].get("score") if evidence else None
    answer_feedback = api.feedback(
        {
            "feedback_scope": "answer",
            "label": scenario["answer_label"],
            "query": scenario["query"],
            "operation_id": asked["operation_id"],
            "selected_memory_ids": selected_ids,
            "answer": asked.get("answer"),
            "notes": "fresh live-style shadow holdout answer label",
        }
    )
    memory_feedback = api.feedback(
        {
            "memory_id": target_memory_id,
            "label": scenario["memory_label"],
            "query": scenario["query"],
            "operation_id": asked["operation_id"],
            "rank": 1,
            "retrieval_score": retrieval_score,
            "notes": "fresh live-style shadow holdout memory label",
        }
    )
    return {
        "scenario": scenario["name"],
        "ask_operation_id": asked["operation_id"],
        "answer_feedback_operation_id": answer_feedback["operation_id"],
        "memory_feedback_operation_id": memory_feedback["operation_id"],
        "selected_memory_count": len(selected_ids),
    }


def generate_log() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="adaptive_shadow_live_style_") as raw_tmp:
        tmp = Path(raw_tmp)
        api = build_test_api(tmp)
        runs: list[dict[str, Any]] = []
        try:
            for scenario in SCENARIOS:
                memory_ids = teach(api, scenario)
                runs.append(ask_and_feedback(api, scenario, memory_ids))
            log_path = api.outcome_logger.path
            OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log_path, OUT_LOG)
        finally:
            api.close()
    return runs


def score_eval_examples(train_dataset: Path, eval_dataset: Path, guard_path: Path, config: dict[str, Any] | None) -> dict[str, Any]:
    guard = read_json(guard_path)
    behavior_config = normalize_adaptive_behavior_config(config)
    train_examples, _ = load_examples(read_json(train_dataset))
    eval_examples, skipped = load_examples(read_json(eval_dataset))
    train_adaptive = [item for item in train_examples if item.get("context_source") == "adaptive_memory_context"]
    eval_adaptive = [item for item in eval_examples if item.get("context_source") == "adaptive_memory_context"]
    answer_labels = answer_label_by_operation(train_adaptive + eval_adaptive)
    exact_models, super_models = train_models(train_adaptive, answer_labels, behavior_config)
    shadow_cfg = behavior_config["shadow"]
    rows = []
    for example in eval_adaptive:
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
        if model is None:
            confidence = 0.0
            learned = None
            probability = symbolic
        else:
            learned = family_predict(model, [example])[0]
            confidence = min(0.8, __import__("math").log1p(float(model.get("count", 0))) / 3.6)
            if not model.get("can_learn"):
                confidence = min(confidence, 0.35)
            probability = confidence * learned + (1.0 - confidence) * symbolic
        advisory = advisory_from_probability(probability, shadow_cfg)
        if confidence < float(shadow_cfg["min_route_confidence"]):
            advisory = "uncertain_keep_symbolic"
        target = int(example["_target"])
        actioned = advisory in {"likely_helpful", "likely_harmful"}
        correct = (advisory == "likely_helpful" and target == 1) or (advisory == "likely_harmful" and target == 0)
        rows.append(
            {
                "id": example.get("id"),
                "label": example.get("label"),
                "target": target,
                "behavior_group": exact,
                "superfamily": superfamily,
                "route": route,
                "route_confidence": round(confidence, 6),
                "learned_probability": None if learned is None else round(float(learned), 6),
                "symbolic_probability": round(float(symbolic), 6),
                "shadow_probability": round(float(probability), 6),
                "advisory": advisory,
                "actioned": actioned,
                "correct": correct if actioned else None,
                "mutates_runtime": False,
                "mutates_config": False,
            }
        )
    actioned = [row for row in rows if row["actioned"]]
    correct_actioned = [row for row in actioned if row["correct"] is True]
    return {
        "guard_readiness": guard.get("readiness"),
        "behavior_config": behavior_config,
        "eval_count": len(rows),
        "skipped_count": len(skipped),
        "advisory_counts": dict(sorted(Counter(row["advisory"] for row in rows).items())),
        "route_counts": dict(sorted(Counter(row["route"] for row in rows).items())),
        "actioned_count": len(actioned),
        "actioned_precision": round(len(correct_actioned) / len(actioned), 6) if actioned else 0.0,
        "coverage": round(len(actioned) / len(rows), 6) if rows else 0.0,
        "decisions": rows,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Shadow Live-Style Eval",
        "",
        "Fresh live-style holdout log generated locally. The shadow controller is trained on the existing rich fixture and evaluated on this new log.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Eval examples: `{report['eval']['eval_count']}`",
        f"Actioned precision: `{report['eval']['actioned_precision']}`",
        f"Coverage: `{report['eval']['coverage']}`",
        "",
        "## Counts",
        "",
        "```json",
        json.dumps({"advisory": report["eval"]["advisory_counts"], "routes": report["eval"]["route_counts"]}, indent=2),
        "```",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fresh live-style logs and evaluate semantic shadow controller advisories.")
    parser.add_argument("--train-dataset", default=str(TRAIN_DATASET))
    parser.add_argument("--semantic-guard", default=str(SEMANTIC_GUARD))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    runs = generate_log()
    dataset = build_dataset_report([OUT_LOG])
    write_dataset_report(dataset, OUT_DATASET_JSON, OUT_DATASET_MD)
    dataset_guard = build_dataset_guard_report(OUT_DATASET_JSON)
    write_dataset_guard_report(dataset_guard, OUT_DATASET_GUARD_JSON, OUT_DATASET_GUARD_MD)
    evaluation = score_eval_examples(Path(args.train_dataset), OUT_DATASET_JSON, Path(args.semantic_guard), load_config(ROOT).get("adaptive_behavior"))
    checks = {
        "log_generated": OUT_LOG.exists(),
        "dataset_ok": dataset.get("ok") is True,
        "dataset_guard_ok": dataset_guard.get("ok") is True,
        "all_adaptive_context": dataset.get("context_source_counts") == {"adaptive_memory_context": dataset.get("example_count")},
        "semantic_guard_promotion_candidate": evaluation.get("guard_readiness") == "promotion_candidate",
        "has_actioned_advisories": int(evaluation.get("actioned_count") or 0) > 0,
        "actioned_precision_at_least_0_70": float(evaluation.get("actioned_precision") or 0.0) >= 0.70,
        "report_only": evaluation.get("mutates_runtime") is False and evaluation.get("mutates_config") is False,
    }
    report = {
        "schema": "adaptive_context_semantic_shadow_live_style_eval/v1",
        "ok": all(checks.values()),
        "readiness": "live_style_shadow_candidate" if all(checks.values()) else "needs_more_shadow_validation",
        "checks": checks,
        "scenario_runs": runs,
        "log_path": str(OUT_LOG),
        "dataset_json": str(OUT_DATASET_JSON),
        "dataset_guard_json": str(OUT_DATASET_GUARD_JSON),
        "eval": evaluation,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "checks": checks, "eval_summary": {k: evaluation[k] for k in ("eval_count", "advisory_counts", "route_counts", "actioned_count", "actioned_precision", "coverage")}, "json": str(Path(args.out_json)), "markdown": str(Path(args.out_md))}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
