from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicyFeatures, CLCPolicySelector  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_clc_selector_ab_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_clc_selector_ab_eval_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
NAMESPACE = "agent:hermes_ab_eval"
AGENT_ID = "hermes"


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


def evidence_states(result: dict[str, Any]) -> list[str]:
    return [str(item.get("memory_state") or "") for item in result.get("evidence") or []]


def evidence_ids(result: dict[str, Any]) -> list[str]:
    return [str(item.get("memory_id") or "") for item in result.get("evidence") or [] if item.get("memory_id")]


def ask_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "conflict": result.get("conflict"),
        "evidence_states": evidence_states(result),
        "evidence_ids": evidence_ids(result),
        "evidence_text": [item.get("text") for item in result.get("evidence") or []],
        "stale_count": len(result.get("stale") or []),
        "current_count": len(result.get("current") or []),
        "disputed_count": len(result.get("disputed") or []),
    }


def has_any(blob: str, terms: list[str]) -> bool:
    return any(term.lower() in blob for term in terms)


def has_all(blob: str, terms: list[str]) -> bool:
    return all(term.lower() in blob for term in terms)


def score_preference_current(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    blob = text_blob(result)
    has_current = has_any(blob, ["espresso", "green tea"])
    stale_dominates = has_any(str(result.get("answer") or "").lower(), ["hates all forms", "never drinks"])
    return has_current and not stale_dominates, {"has_current": has_current, "stale_dominates": stale_dominates}


def score_project_update(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    blob = text_blob(result)
    has_current = has_all(blob, ["cedar map", "selector"])
    stale_only = "without selector" in str(result.get("answer") or "").lower() and "selector" not in blob
    return has_current and not stale_only, {"has_current": has_current, "stale_only": stale_only}


def score_topic_isolation(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    answer = str(result.get("answer") or "").lower()
    mentions_target = "accuweather" in answer
    contamination = any(term in answer for term in ["pizza", "espresso", "cedar map"])
    return mentions_target and not contamination, {"mentions_target": mentions_target, "contamination": contamination}


def score_session_boundary(first: dict[str, Any], second: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    first_answer = str(first.get("answer") or "").lower()
    second_answer = str(second.get("answer") or "").lower()
    first_ok = "source clarity" in first_answer or "transparency" in first_answer
    second_ok = "g-cl" in second_answer or "domain geometry" in second_answer or "anchor" in second_answer
    leak = "source clarity" in second_answer and not second_ok
    return first_ok and second_ok and not leak, {"first_ok": first_ok, "second_ok": second_ok, "topic_leak": leak}


def selector_decision(condition_name: str) -> dict[str, Any]:
    decision = CLCPolicySelector().select(CLCPolicyFeatures.from_condition_name(condition_name))
    return {
        "policy": decision.policy,
        "action": decision.action,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def scenario_short_hard(pipeline: MemoryPipeline, mode: str) -> dict[str, Any]:
    old = pipeline.teach(
        "Victor likes coffee in the morning and tea in the afternoon.",
        namespace=NAMESPACE,
        agent_id=AGENT_ID,
        store_session=False,
        domain="agent_memory",
        memory_type="preference",
    )
    if mode == "selector":
        update = pipeline.correct(
            "Victor likes espresso in the morning and green tea in the afternoon.",
            target_memory_ids=[old["memory"]["memory_id"]],
            target_query="Victor drink preference",
            namespace=NAMESPACE,
            agent_id=AGENT_ID,
            store_session=False,
            force_clc_state="FOCUS",
            domain="agent_memory",
            memory_type="preference",
        )
    else:
        update = pipeline.teach(
            "Victor hates all forms of tea and never drinks it.",
            namespace=NAMESPACE,
            agent_id=AGENT_ID,
            store_session=False,
            domain="agent_memory",
            memory_type="preference",
        )
    asked = pipeline.ask(
        "What is Victor's current drink preference?",
        namespace=NAMESPACE,
        include_global=False,
        top_k=5,
        store_session=False,
    )
    passed, metrics = score_preference_current(asked)
    return {
        "passed": passed,
        "metrics": metrics,
        "writes": {"old": old["memory"], "update": update.get("memory") or update.get("correction_memory")},
        "ask": ask_summary(asked),
    }


def scenario_short_standard(pipeline: MemoryPipeline, mode: str) -> dict[str, Any]:
    old = pipeline.teach(
        "Hermes project codename is Cedar Map without selector routing.",
        namespace=NAMESPACE,
        agent_id=AGENT_ID,
        store_session=False,
        domain="agent_memory",
        memory_type="semantic_note",
    )
    if mode == "selector":
        update = pipeline.correct(
            "Hermes project codename is Cedar Map with the CLC selector enabled.",
            target_memory_ids=[old["memory"]["memory_id"]],
            target_query="Hermes project codename",
            namespace=NAMESPACE,
            agent_id=AGENT_ID,
            store_session=False,
            force_clc_state="FOCUS",
            domain="agent_memory",
            memory_type="semantic_note",
        )
    else:
        update = pipeline.teach(
            "Hermes project codename is Cedar Map with the CLC selector enabled.",
            namespace=NAMESPACE,
            agent_id=AGENT_ID,
            store_session=False,
            domain="agent_memory",
            memory_type="semantic_note",
        )
    asked = pipeline.ask(
        "What is the current Hermes project codename?",
        namespace=NAMESPACE,
        include_global=False,
        top_k=5,
        store_session=False,
    )
    passed, metrics = score_project_update(asked)
    return {
        "passed": passed,
        "metrics": metrics,
        "writes": {"old": old["memory"], "update": update.get("memory") or update.get("correction_memory")},
        "ask": ask_summary(asked),
    }


def scenario_long_hard(pipeline: MemoryPipeline, mode: str) -> dict[str, Any]:
    facts = [
        ("Victor pizza preference: he likes mushroom pizza.", "food_drink", "preference"),
        ("Weather radar method for Victor: use AccuWeather URL for radar checks.", "agent_memory", "procedure"),
        ("Hermes project codename is Cedar Map.", "agent_memory", "semantic_note"),
        ("Victor espresso preference: he likes espresso in the morning.", "food_drink", "preference"),
        ("Weather radar correction: AccuWeather remains preferred over visual radar canvas guessing.", "agent_memory", "procedure"),
    ]
    writes = []
    for text, domain, memory_type in facts:
        writes.append(
            pipeline.teach(
                text,
                namespace=NAMESPACE,
                agent_id=AGENT_ID,
                store_session=False,
                domain=domain,
                memory_type=memory_type,
                force_clc_state=None if mode == "baseline" else "RECALL",
            )["memory"]
        )
    asked = pipeline.ask(
        "What weather radar method should Victor use?",
        namespace=NAMESPACE,
        include_global=False,
        top_k=5,
        store_session=False,
    )
    passed, metrics = score_topic_isolation(asked)
    return {"passed": passed, "metrics": metrics, "writes": writes, "ask": ask_summary(asked)}


def scenario_long_standard(pipeline: MemoryPipeline, mode: str) -> dict[str, Any]:
    session_id = None
    pipeline.teach(
        "Victor values source clarity and transparency when information is presented.",
        namespace=NAMESPACE,
        agent_id=AGENT_ID,
        store_session=False,
        domain="agent_memory",
        memory_type="preference",
    )
    pipeline.teach(
        "G-CL maintains domain geometry, anchor drift, curvature, and stability.",
        namespace=NAMESPACE,
        agent_id=AGENT_ID,
        store_session=False,
        domain="G-CL",
        memory_type="semantic_note",
    )
    first = pipeline.ask(
        "What does Victor value when information is presented?",
        namespace=NAMESPACE,
        include_global=False,
        top_k=5,
        store_session=True,
        agent_id=AGENT_ID,
    )
    session_id = first.get("session_id")
    second = pipeline.ask(
        "What does G-CL maintain?",
        namespace=NAMESPACE,
        include_global=False,
        top_k=5,
        store_session=True,
        agent_id=AGENT_ID,
        session_id=session_id,
    )
    passed, metrics = score_session_boundary(first, second)
    return {
        "passed": passed,
        "metrics": metrics,
        "ask_first": ask_summary(first),
        "ask_second": ask_summary(second),
        "session_id": session_id,
    }


SCENARIOS = [
    {
        "id": "short_hard_preference_conflict",
        "condition_name": "hard_budget144",
        "runner": scenario_short_hard,
    },
    {
        "id": "short_standard_agent_fact_update",
        "condition_name": "standard_budget144",
        "runner": scenario_short_standard,
    },
    {
        "id": "long_hard_multi_topic_stream",
        "condition_name": "long2_hard_budget288",
        "runner": scenario_long_hard,
    },
    {
        "id": "long_standard_session_recall",
        "condition_name": "long2_standard_budget288",
        "runner": scenario_long_standard,
    },
]


def run_one(scenario: dict[str, Any], mode: str) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = make_pipeline(root, root / f"{scenario['id']}_{mode}.db")
        try:
            result = scenario["runner"](pipeline, mode)
            db_stats = pipeline.db.stats()
            stats = {
                "memories": int(db_stats.get("memories", 0)),
                "domains": int(db_stats.get("domains", 0)),
                "contradictions": int(db_stats.get("contradictions", 0)),
                "relations": int(db_stats.get("relations", 0)),
            }
        finally:
            pipeline.close()
    return {**result, "stats": stats}


def compare_result(baseline: dict[str, Any], selector: dict[str, Any]) -> str:
    if selector["passed"] and not baseline["passed"]:
        return "helped"
    if baseline["passed"] and not selector["passed"]:
        return "hurt"
    if selector["passed"] and baseline["passed"]:
        return "both_passed"
    return "both_failed"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Hermes CLC Selector A/B Eval",
        "",
        "This eval compares normal memory-core behavior against selector-advised memory operations.",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        "| Scenario | Policy | Baseline | Selector | Outcome |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["scenarios"]:
        lines.append(
            "| {id} | {policy} | {baseline} | {selector} | {outcome} |".format(
                id=row["id"],
                policy=row["selector_decision"]["policy"],
                baseline="PASS" if row["baseline"]["passed"] else "FAIL",
                selector="PASS" if row["selector"]["passed"] else "FAIL",
                outcome=row["comparison"],
            )
        )
    lines.extend(["", "## Notes", ""])
    lines.append("Selector-advised mode maps policies into concrete memory operations:")
    lines.append("- `XSEQ_MEMORY_REFRESH`: use correction workflow for hard contradictions.")
    lines.append("- `LONG_SEVERE_VERIFIED_REFRESH`: use correction/FOCUS workflow for compatible updates.")
    lines.append("- `PROTECT_PERIODIC`: keep normal periodic/protect memory behavior.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outcome_labels(report: dict[str, Any]) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = []
    for row in report["scenarios"]:
        lines.append(
            json.dumps(
                {
                    "run_id": run_id,
                    "source": "local_hash_ab_eval",
                    "scenario_id": row["id"],
                    "condition_name": row["condition_name"],
                    "selected_policy": row["selector_decision"]["policy"],
                    "selected_action": row["selector_decision"]["action"],
                    "outcome_label": row["comparison"],
                    "baseline_passed": bool(row["baseline"]["passed"]),
                    "selector_passed": bool(row["selector"]["passed"]),
                    "selector_confidence": float(row["selector_decision"]["confidence"]),
                },
                sort_keys=True,
            )
        )
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> int:
    scenarios = []
    for scenario in SCENARIOS:
        decision = selector_decision(scenario["condition_name"])
        baseline = run_one(scenario, "baseline")
        selector = run_one(scenario, "selector")
        scenarios.append(
            {
                "id": scenario["id"],
                "condition_name": scenario["condition_name"],
                "selector_decision": decision,
                "baseline": baseline,
                "selector": selector,
                "comparison": compare_result(baseline, selector),
            }
        )
    report = {
        "ok": all(row["selector"]["passed"] for row in scenarios),
        "purpose": "A/B outcome eval for Hermes CLC selector operations",
        "namespace": NAMESPACE,
        "agent_id": AGENT_ID,
        "scenarios": scenarios,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    write_outcome_labels(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD), "summary": [
        {
            "id": row["id"],
            "baseline_passed": row["baseline"]["passed"],
            "selector_passed": row["selector"]["passed"],
            "comparison": row["comparison"],
            "policy": row["selector_decision"]["policy"],
        }
        for row in scenarios
    ], "outcome_labels": str(OUT_JSONL)}, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
