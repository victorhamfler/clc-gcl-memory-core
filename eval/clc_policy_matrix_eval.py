from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCPolicyFeatures,
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
AGENT_ID = "hermes_policy_matrix"
POLICIES = [POLICY_PERIODIC, POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY]
POLICY_ACTIONS = {
    POLICY_PERIODIC: "PROTECT_PERIODIC",
    POLICY_LONG_SEVERE: "LONG_SEVERE_VERIFIED_REFRESH",
    POLICY_XSEQ_MEMORY: "XSEQ_MEMORY_REFRESH",
}
POLICY_COST = {
    POLICY_PERIODIC: 0.0,
    POLICY_LONG_SEVERE: 0.015,
    POLICY_XSEQ_MEMORY: 0.025,
}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family: str
    condition_name: str
    features: CLCPolicyFeatures
    runner: Callable[[MemoryPipeline, str, str], dict[str, Any]]


def make_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def text_blob(result: dict[str, Any]) -> str:
    parts = [str(result.get("answer") or "")]
    for key in ("evidence", "current", "stale", "disputed", "historical"):
        for item in result.get(key) or []:
            parts.append(str(item.get("text") or ""))
    return " ".join(parts).lower()


def ask_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "conflict": result.get("conflict"),
        "evidence_text": [item.get("text") for item in result.get("evidence") or []],
        "evidence_states": [str(item.get("memory_state") or "") for item in result.get("evidence") or []],
        "stale_count": len(result.get("stale") or []),
        "current_count": len(result.get("current") or []),
        "disputed_count": len(result.get("disputed") or []),
    }


def has_all(blob: str, terms: list[str]) -> bool:
    return all(term.lower() in blob for term in terms)


def has_any(blob: str, terms: list[str]) -> bool:
    return any(term.lower() in blob for term in terms)


def policy_utility(passed: bool, policy: str, features: CLCPolicyFeatures) -> float:
    label_cost_multiplier = max(0.25, features.label_cost / 0.0002)
    return (1.0 if passed else 0.0) - POLICY_COST[policy] * label_cost_multiplier


def apply_update(
    pipeline: MemoryPipeline,
    policy: str,
    correction: str,
    target_ids: list[str],
    target_query: str,
    namespace: str,
    domain: str,
    memory_type: str,
) -> dict[str, Any]:
    if policy == POLICY_PERIODIC or not target_ids:
        return pipeline.teach(
            correction,
            namespace=namespace,
            agent_id=AGENT_ID,
            store_session=False,
            domain=domain,
            memory_type=memory_type,
        )
    selected_targets = target_ids if policy == POLICY_XSEQ_MEMORY else target_ids[:1]
    return pipeline.correct(
        correction,
        target_memory_ids=selected_targets,
        target_query=target_query,
        namespace=namespace,
        agent_id=AGENT_ID,
        store_session=False,
        force_clc_state="FOCUS",
        domain=domain,
        memory_type=memory_type,
    )


def hard_bad_majority_runner(
    subject: str,
    current_terms: list[str],
    stale_terms: list[str],
    question: str,
) -> Callable[[MemoryPipeline, str, str], dict[str, Any]]:
    def run(pipeline: MemoryPipeline, policy: str, namespace: str) -> dict[str, Any]:
        stale_texts = [
            f"{subject} legacy preference: {subject} {stale_terms[0]}.",
            f"{subject} archived preference: {subject} {stale_terms[1]}.",
            f"{subject} old profile note: {subject} {stale_terms[2]}.",
        ]
        stale_ids = []
        for text in stale_texts:
            mem = pipeline.teach(
                text,
                namespace=namespace,
                agent_id=AGENT_ID,
                store_session=False,
                domain="agent_memory",
                memory_type="preference",
            )["memory"]
            stale_ids.append(mem["memory_id"])
        update = apply_update(
            pipeline,
            policy,
            f"{subject} current preference: {subject} {current_terms[0]} and {current_terms[1]}.",
            stale_ids,
            question,
            namespace,
            "agent_memory",
            "preference",
        )
        asked = pipeline.ask(question, namespace=namespace, include_global=False, top_k=6, store_session=False)
        blob = text_blob(asked)
        stale_dominates = has_any(str(asked.get("answer") or "").lower(), stale_terms)
        passed = has_all(blob, current_terms) and not stale_dominates
        return {
            "passed": passed,
            "metrics": {"has_current": has_all(blob, current_terms), "stale_dominates": stale_dominates},
            "writes": {"update": update.get("memory") or update.get("correction_memory")},
            "ask": ask_summary(asked),
        }

    return run


def standard_update_runner(
    old_text: str,
    new_text: str,
    question: str,
    current_terms: list[str],
    stale_terms: list[str],
    domain: str = "agent_memory",
    memory_type: str = "semantic_note",
) -> Callable[[MemoryPipeline, str, str], dict[str, Any]]:
    def run(pipeline: MemoryPipeline, policy: str, namespace: str) -> dict[str, Any]:
        old = pipeline.teach(
            old_text,
            namespace=namespace,
            agent_id=AGENT_ID,
            store_session=False,
            domain=domain,
            memory_type=memory_type,
        )
        update = apply_update(
            pipeline,
            policy,
            new_text,
            [old["memory"]["memory_id"]],
            question,
            namespace,
            domain,
            memory_type,
        )
        asked = pipeline.ask(question, namespace=namespace, include_global=False, top_k=5, store_session=False)
        blob = text_blob(asked)
        answer = str(asked.get("answer") or "").lower()
        stale_dominates = has_any(answer, stale_terms)
        passed = has_all(blob, current_terms) and not stale_dominates
        return {
            "passed": passed,
            "metrics": {"has_current": has_all(blob, current_terms), "stale_dominates": stale_dominates},
            "writes": {"old": old["memory"], "update": update.get("memory") or update.get("correction_memory")},
            "ask": ask_summary(asked),
        }

    return run


def long_topic_runner(topic: str, target_terms: list[str], distractors: list[str]) -> Callable[[MemoryPipeline, str, str], dict[str, Any]]:
    def run(pipeline: MemoryPipeline, policy: str, namespace: str) -> dict[str, Any]:
        facts = [
            (f"{topic} target procedure: use {target_terms[0]} for {target_terms[1]}.", "agent_memory", "procedure"),
            (f"Food distractor: Victor prefers {distractors[0]}.", "food_drink", "preference"),
            (f"Project distractor: Hermes codename is {distractors[1]}.", "agent_memory", "semantic_note"),
            (f"{topic} verification rule: {target_terms[0]} remains preferred for {target_terms[1]}.", "agent_memory", "procedure"),
            (f"Personal distractor: Victor likes {distractors[2]}.", "food_drink", "preference"),
        ]
        writes = []
        for text, domain, memory_type in facts:
            force_state = None if policy == POLICY_PERIODIC else "RECALL"
            writes.append(
                pipeline.teach(
                    text,
                    namespace=namespace,
                    agent_id=AGENT_ID,
                    store_session=False,
                    domain=domain,
                    memory_type=memory_type,
                    force_clc_state=force_state,
                )["memory"]
            )
        asked = pipeline.ask(
            f"What should be used for {target_terms[1]}?",
            namespace=namespace,
            include_global=False,
            top_k=5,
            store_session=False,
        )
        answer = str(asked.get("answer") or "").lower()
        passed = has_all(answer, target_terms) and not has_any(answer, distractors)
        return {"passed": passed, "metrics": {"target_only": passed}, "writes": writes, "ask": ask_summary(asked)}

    return run


def session_runner(topic_a: str, topic_b: str, terms_a: list[str], terms_b: list[str]) -> Callable[[MemoryPipeline, str, str], dict[str, Any]]:
    def run(pipeline: MemoryPipeline, policy: str, namespace: str) -> dict[str, Any]:
        force_state = None if policy == POLICY_PERIODIC else "RECALL"
        pipeline.teach(
            f"{topic_a}: Victor values {terms_a[0]} and {terms_a[1]}.",
            namespace=namespace,
            agent_id=AGENT_ID,
            store_session=False,
            domain="agent_memory",
            memory_type="preference",
            force_clc_state=force_state,
        )
        pipeline.teach(
            f"{topic_b}: G-CL maintains {terms_b[0]} and {terms_b[1]}.",
            namespace=namespace,
            agent_id=AGENT_ID,
            store_session=False,
            domain="G-CL",
            memory_type="semantic_note",
            force_clc_state=force_state,
        )
        first = pipeline.ask(
            f"What does Victor value for {topic_a}?",
            namespace=namespace,
            include_global=False,
            top_k=5,
            store_session=True,
            agent_id=AGENT_ID,
        )
        second = pipeline.ask(
            "What does G-CL maintain?",
            namespace=namespace,
            include_global=False,
            top_k=5,
            store_session=True,
            agent_id=AGENT_ID,
            session_id=first.get("session_id"),
        )
        first_answer = str(first.get("answer") or "").lower()
        second_answer = str(second.get("answer") or "").lower()
        passed = has_all(first_answer, terms_a) and has_all(second_answer, terms_b) and not has_any(second_answer, terms_a)
        return {
            "passed": passed,
            "metrics": {"first_ok": has_all(first_answer, terms_a), "second_ok": has_all(second_answer, terms_b)},
            "ask_first": ask_summary(first),
            "ask_second": ask_summary(second),
        }

    return run


def build_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []
    hard_cases = [
        ("victor_drink", "Victor", ["espresso", "green tea"], ["hates tea", "never drinks tea", "avoids espresso"], "What is Victor's current drink preference?"),
        ("operator_channel", "Operator", ["matrix room", "blue channel"], ["uses red channel", "stays in old room", "blocks blue channel"], "What is Operator's current channel?"),
        ("hermes_mode", "Hermes", ["selector mode", "focus refresh"], ["periodic only", "no refresh", "ignores selector"], "What is Hermes current mode?"),
        ("victor_tool", "Victor", ["accuweather", "radar checks"], ["visual guessing", "canvas guessing", "no radar source"], "What tool should Victor use for radar checks?"),
        ("agent_memory", "Agent", ["domain tags", "semantic notes"], ["drops domain tags", "generic notes only", "forgets semantic notes"], "What should Agent preserve?"),
        ("lab_protocol", "Lab", ["cedar protocol", "verified update"], ["old protocol", "unverified update", "ignores cedar protocol"], "What protocol is current for Lab?"),
    ]
    for idx, subject, current, stale, question in hard_cases:
        scenarios.append(
            Scenario(
                scenario_id=f"hard_bad_majority_{idx}",
                family="hard_bad_majority",
                condition_name="hard_budget144",
                features=CLCPolicyFeatures.from_condition_name(
                    "hard_budget144", memory_bad_rate=0.75, probe_drop=0.18, csd_ratio=1.4
                ),
                runner=hard_bad_majority_runner(subject, current, stale, question),
            )
        )
    standard_cases = [
        ("standard_cedar", "Hermes project codename is Cedar Map without selector routing.", "Hermes project codename is Cedar Map with selector routing enabled.", "What is the current Hermes project codename?", ["cedar map", "selector"], ["without selector"]),
        ("standard_port", "Hermes memory server port is 8765.", "Hermes memory server port is 8772.", "What is Hermes memory server port?", ["8772"], ["8765"]),
        ("standard_embedding", "Gemma embedding dimension is unknown.", "Gemma embedding dimension is 768.", "What is the Gemma embedding dimension?", ["768"], ["unknown"]),
        ("standard_report", "Live eval report says the correct endpoint drops metadata.", "Live eval report says the correct endpoint preserves metadata.", "What does the live eval report say about metadata?", ["preserves metadata"], ["drops metadata"]),
        ("standard_backend", "The live embedding backend is hash only.", "The live embedding backend is wsl llama cpp.", "What is the live embedding backend?", ["wsl", "llama"], ["hash only"]),
        ("standard_goal", "CLC selector outcomes are only printed.", "CLC selector outcomes are logged to jsonl.", "How are CLC selector outcomes stored?", ["logged", "jsonl"], ["only printed"]),
    ]
    for idx, old_text, new_text, question, current, stale in standard_cases:
        scenarios.append(
            Scenario(
                scenario_id=f"standard_update_{idx}",
                family="standard_update",
                condition_name="standard_budget144",
                features=CLCPolicyFeatures.from_condition_name(
                    "standard_budget144", memory_bad_rate=0.25, probe_drop=0.08, csd_ratio=0.9
                ),
                runner=standard_update_runner(old_text, new_text, question, current, stale),
            )
        )
    long_cases = [
        ("weather", ["accuweather", "radar checks"], ["mushroom pizza", "cedar map", "espresso"]),
        ("docs", ["source clarity", "summaries"], ["green tea", "red channel", "old protocol"]),
        ("memory", ["domain tags", "corrections"], ["pizza", "blue channel", "espresso"]),
        ("testing", ["jsonl logs", "outcome labels"], ["canvas guessing", "old room", "hash only"]),
    ]
    for idx, target_terms, distractors in long_cases:
        scenarios.append(
            Scenario(
                scenario_id=f"long_topic_{idx}",
                family="long_topic",
                condition_name="long2_hard_budget288",
                features=CLCPolicyFeatures.from_condition_name(
                    "long2_hard_budget288", memory_bad_rate=0.35, probe_drop=0.04, csd_ratio=0.7
                ),
                runner=long_topic_runner(idx, target_terms, distractors),
            )
        )
    session_cases = [
        ("presentation preference", "geometry memory", ["source clarity", "transparency"], ["domain geometry", "anchor drift"]),
        ("testing preference", "selector memory", ["small tests", "repeatability"], ["policy selection", "outcome labels"]),
        ("agent preference", "gcl memory", ["metadata", "namespaces"], ["curvature", "stability"]),
        ("report preference", "csd memory", ["evidence", "dates"], ["surprise", "recall"]),
    ]
    for idx, topic_b, terms_a, terms_b in session_cases:
        scenarios.append(
            Scenario(
                scenario_id=f"long_session_{idx}",
                family="long_session",
                condition_name="long2_standard_budget288",
                features=CLCPolicyFeatures.from_condition_name(
                    "long2_standard_budget288", memory_bad_rate=0.2, probe_drop=0.03, csd_ratio=0.6
                ),
                runner=session_runner(idx, topic_b, terms_a, terms_b),
            )
        )
    return scenarios


def run_policy(scenario: Scenario, policy: str) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = make_pipeline(root, root / f"{scenario.scenario_id}_{policy}.db")
        namespace = f"agent:policy_matrix:{scenario.scenario_id}:{policy}"
        try:
            result = scenario.runner(pipeline, policy, namespace)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()
    return {
        **result,
        "utility": round(policy_utility(bool(result["passed"]), policy, scenario.features), 6),
        "stats": {
            "memories": int(stats.get("memories", 0)),
            "domains": int(stats.get("domains", 0)),
            "contradictions": int(stats.get("contradictions", 0)),
            "relations": int(stats.get("relations", 0)),
        },
    }


def oracle_policy(policy_results: dict[str, dict[str, Any]]) -> str:
    return max(POLICIES, key=lambda policy: (policy_results[policy]["utility"], -POLICY_COST[policy]))


def feature_vector(features: CLCPolicyFeatures) -> list[float]:
    return [
        1.0 if features.hard else 0.0,
        1.0 if features.long_stream else 0.0,
        features.budget_units / 288.0,
        features.cycles / 2.0,
        features.csd_ratio,
        features.probe_drop,
        features.label_cost / 0.0002,
        features.budget_pressure,
        features.memory_bad_rate,
    ]


def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def knn_predict(train_rows: list[dict[str, Any]], features: CLCPolicyFeatures, k: int = 3) -> str:
    target = feature_vector(features)
    ranked = sorted(
        train_rows,
        key=lambda row: distance(feature_vector(row["features"]), target),
    )
    votes = Counter(row["oracle_policy"] for row in ranked[:k])
    return max(POLICIES, key=lambda policy: (votes[policy], -POLICY_COST[policy]))


def strategy_policy(name: str, scenario: Scenario, train_rows: list[dict[str, Any]] | None = None) -> str:
    if name == "periodic_only":
        return POLICY_PERIODIC
    if name == "always_long_severe":
        return POLICY_LONG_SEVERE
    if name == "always_xseq_memory":
        return POLICY_XSEQ_MEMORY
    if name == "current_clc_selector":
        return CLCPolicySelector().select(scenario.features).policy
    if name == "learned_knn_selector":
        if not train_rows:
            return CLCPolicySelector().select(scenario.features).policy
        return knn_predict(train_rows, scenario.features)
    raise ValueError(f"unknown strategy: {name}")


def summarize_strategies(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strategies = [
        "periodic_only",
        "always_long_severe",
        "always_xseq_memory",
        "current_clc_selector",
        "learned_knn_selector",
    ]
    summary: dict[str, Any] = {}
    for strategy in strategies:
        total_utility = 0.0
        pass_count = 0
        oracle_matches = 0
        policy_counts: Counter[str] = Counter()
        for idx, row in enumerate(rows):
            train_rows = rows[:idx] + rows[idx + 1 :]
            policy = strategy_policy(strategy, row["scenario"], train_rows)
            policy_counts[policy] += 1
            result = row["policy_results"][policy]
            total_utility += float(result["utility"])
            pass_count += 1 if result["passed"] else 0
            oracle_matches += 1 if policy == row["oracle_policy"] else 0
        summary[strategy] = {
            "utility": round(total_utility, 6),
            "pass_rate": round(pass_count / len(rows), 6),
            "oracle_match_rate": round(oracle_matches / len(rows), 6),
            "policy_counts": dict(policy_counts),
        }
    return summary


def write_outcome_labels(report: dict[str, Any]) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for row in report["scenarios"]:
            chosen = row["strategies"]["current_clc_selector"]["policy"]
            result = row["policy_results"][chosen]
            if result["passed"] and chosen == row["oracle_policy"]:
                label = "oracle_match_passed"
            elif result["passed"]:
                label = "passed_non_oracle"
            else:
                label = "failed"
            f.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "source": "policy_matrix_hash_eval",
                        "scenario_id": row["id"],
                        "family": row["family"],
                        "condition_name": row["condition_name"],
                        "selected_policy": chosen,
                        "selected_action": POLICY_ACTIONS[chosen],
                        "oracle_policy": row["oracle_policy"],
                        "outcome_label": label,
                        "selector_passed": bool(result["passed"]),
                        "selector_utility": float(result["utility"]),
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# CLC Policy Matrix Eval",
        "",
        "This experiment evaluates each scenario against all candidate policies, then compares selector strategies.",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'REVIEW'}**",
        "",
        "| Strategy | Utility | Pass rate | Oracle match | Policy counts |",
        "|---|---:|---:|---:|---|",
    ]
    for name, stats in report["strategy_summary"].items():
        lines.append(
            f"| {name} | {stats['utility']} | {stats['pass_rate']} | {stats['oracle_match_rate']} | {stats['policy_counts']} |"
        )
    lines.extend(["", "## Oracle Policies", "", "| Family | Scenario | Oracle | Current CLC | Outcome |", "|---|---|---|---|---|"])
    for row in report["scenarios"]:
        current = row["strategies"]["current_clc_selector"]
        lines.append(
            f"| {row['family']} | {row['id']} | {row['oracle_policy']} | {current['policy']} | {current['outcome']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    scenarios = build_scenarios()
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        policy_results = {policy: run_policy(scenario, policy) for policy in POLICIES}
        oracle = oracle_policy(policy_results)
        rows.append(
            {
                "scenario": scenario,
                "id": scenario.scenario_id,
                "family": scenario.family,
                "condition_name": scenario.condition_name,
                "features": scenario.features,
                "policy_results": policy_results,
                "oracle_policy": oracle,
            }
        )

    strategy_summary = summarize_strategies(rows)
    serialized_rows = []
    for idx, row in enumerate(rows):
        strategies = {}
        for strategy in strategy_summary:
            train_rows = rows[:idx] + rows[idx + 1 :]
            policy = strategy_policy(strategy, row["scenario"], train_rows)
            result = row["policy_results"][policy]
            strategies[strategy] = {
                "policy": policy,
                "passed": bool(result["passed"]),
                "utility": float(result["utility"]),
                "outcome": "oracle" if policy == row["oracle_policy"] else ("passed" if result["passed"] else "failed"),
            }
        serialized_rows.append(
            {
                "id": row["id"],
                "family": row["family"],
                "condition_name": row["condition_name"],
                "features": row["features"].__dict__,
                "oracle_policy": row["oracle_policy"],
                "policy_results": row["policy_results"],
                "strategies": strategies,
            }
        )

    report = {
        "ok": strategy_summary["current_clc_selector"]["pass_rate"] >= 0.95
        and strategy_summary["current_clc_selector"]["utility"] >= strategy_summary["periodic_only"]["utility"],
        "purpose": "Expanded policy-matrix evaluation for CSD/G-CL/CLC memory selector development",
        "num_scenarios": len(serialized_rows),
        "policies": POLICIES,
        "strategy_summary": strategy_summary,
        "scenarios": serialized_rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    write_outcome_labels(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "outcome_labels": str(OUT_JSONL),
                "num_scenarios": report["num_scenarios"],
                "strategy_summary": strategy_summary,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
