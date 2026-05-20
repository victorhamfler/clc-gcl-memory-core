from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import POLICY_LONG_SEVERE, POLICY_PERIODIC, POLICY_XSEQ_MEMORY  # noqa: E402
from core.config import load_config  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.selector_runtime import (  # noqa: E402
    apply_retrieval_explanation_guard,
    build_policy_selector,
    selector_features_from_retrieval_context,
)
from core.runtime import init_db  # noqa: E402


AGGRESSIVE_POLICIES = {POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}
PROTECT_POLICIES = {POLICY_PERIODIC}


@dataclass(frozen=True)
class WorkflowWrite:
    text: str
    source: str
    domain: str = "agent_memory"
    memory_type: str = "semantic_note"
    ref: str | None = None
    target_ref: str | None = None


@dataclass(frozen=True)
class AskCheck:
    query: str
    condition_name: str
    target_behavior: str
    expected_hard: bool
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class WorkflowStep:
    action: str
    write: WorkflowWrite | None = None
    ask: AskCheck | None = None


OUT_STEM = "agent_workflow_selector_integration_eval"


def output_paths(embedding_backend: str) -> tuple[Path, Path]:
    suffix = "" if embedding_backend == "hash" else f"_{embedding_backend}"
    stem = f"{OUT_STEM}{suffix}"
    return REPO_ROOT / "experiments" / f"{stem}_results.json", REPO_ROOT / "experiments" / f"{stem}_report.md"


def init_pipeline(tmp: Path, embedding_backend: str) -> MemoryPipeline:
    db_path = tmp / "agent_workflow_selector.db"
    init_db(ROOT, db_path)
    if embedding_backend == "config":
        embedding_config = dict((load_config(ROOT).get("embedding") or {}))
    else:
        embedding_config = {"backend": "hash", "dim": 128}
    return MemoryPipeline(ROOT, db_path, embedding_dim=128, embedding_config=embedding_config)


def target_matches(policy: str, target_behavior: str) -> bool:
    if target_behavior == "aggressive":
        return policy in AGGRESSIVE_POLICIES
    if target_behavior == "protect":
        return policy in PROTECT_POLICIES
    raise ValueError(f"Unknown target behavior: {target_behavior}")


def answer_matches(answer: str, ask: AskCheck) -> tuple[bool, list[str]]:
    lowered = answer.lower()
    failures: list[str] = []
    for term in ask.must_include:
        if term.lower() not in lowered:
            failures.append(f"missing:{term}")
    for term in ask.must_not_include:
        if term.lower() in lowered:
            failures.append(f"forbidden:{term}")
    return not failures, failures


def run_workflow(embedding_backend: str, top_k: int) -> dict[str, Any]:
    namespace = "agent:workflow-selector-integration"
    agent_id = "workflow-selector-agent"
    session_id = "workflow-selector-session"
    selector = build_policy_selector(ROOT, load_config(ROOT))

    steps = [
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="gcl_mechanism",
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="agent_memory_v3/gcl_mechanism.md",
                domain="G-CL",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="csd_signal",
                text="CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
                source="agent_memory_v3/csd_signal.md",
                domain="CSD",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="project_status",
                text="Hermes project status: selector calibration is stable and ready for longer harness testing.",
                source="agent_memory_v3/project_status.md",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="old_codename",
                text="Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project_codename.md",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="mid_codename",
                target_ref="old_codename",
                text="Hermes project codename is Cedar Map, not Alpha Loom.",
                source="agent_memory_v2/project_codename.md",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="current_codename",
                target_ref="mid_codename",
                text="Hermes project codename is Cedar Map with retrieval guards enabled.",
                source="agent_memory_v3/project_codename.md",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="radar_method",
                text="Weather radar method for Victor: use the AccuWeather URL for radar checks.",
                source="agent_memory_v3/radar_method.md",
                memory_type="procedure",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="old_radar_report",
                text="Radar report filename should be canvas_guessing_report.md.",
                source="agent_memory_v1/radar_report.md",
                memory_type="procedure",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="current_radar_report",
                target_ref="old_radar_report",
                text="Radar report filename should be accuweather_radar_report.md, not canvas_guessing_report.md.",
                source="agent_memory_v2/radar_report.md",
                memory_type="procedure",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="old_drink",
                text="Victor currently prefers espresso.",
                source="agent_memory_v1/drink.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="mid_drink",
                target_ref="old_drink",
                text="Victor currently prefers water, not espresso.",
                source="agent_memory_v2/drink.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="current_drink",
                target_ref="mid_drink",
                text="Victor currently prefers sparkling water, not plain water.",
                source="agent_memory_v3/drink.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ),
        WorkflowStep(
            "teach",
            WorkflowWrite(
                ref="old_pizza",
                text="Victor currently prefers mushroom pizza.",
                source="agent_memory_v1/pizza.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ),
        WorkflowStep(
            "correct",
            WorkflowWrite(
                ref="current_pizza",
                target_ref="old_pizza",
                text="Victor currently prefers cheese pizza, not mushroom pizza.",
                source="agent_memory_v2/pizza.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What is the current Hermes project codename?",
                condition_name="hard_budget144",
                target_behavior="aggressive",
                expected_hard=True,
                must_include=("Cedar Map",),
                notes="Direct correction chain should answer current codename and trigger hard refresh.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What is the Hermes project status?",
                condition_name="standard_budget144",
                target_behavior="protect",
                expected_hard=False,
                must_include=("stable", "longer harness"),
                must_not_include=("Alpha Loom",),
                notes="Near-topic codename chain should not override status answer.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What radar method should Victor use?",
                condition_name="standard_budget144",
                target_behavior="protect",
                expected_hard=False,
                must_include=("AccuWeather URL",),
                notes="Near-topic radar report correction should not force method refresh.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What drink does Victor currently prefer?",
                condition_name="hard_budget144",
                target_behavior="aggressive",
                expected_hard=True,
                must_include=("sparkling water",),
                notes="Deep preference correction chain should trigger hard refresh.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What pizza does Victor currently prefer?",
                condition_name="hard_budget144",
                target_behavior="aggressive",
                expected_hard=True,
                must_include=("cheese pizza",),
                notes="Direct food correction should trigger hard refresh.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What does G-CL maintain?",
                condition_name="long2_standard_budget288",
                target_behavior="protect",
                expected_hard=False,
                must_include=("domain geometry", "anchor drift"),
                notes="Clean G-CL target should stay protected despite other correction chains.",
            ),
        ),
        WorkflowStep(
            "ask",
            ask=AskCheck(
                query="What does CSD help detect?",
                condition_name="long2_standard_budget288",
                target_behavior="protect",
                expected_hard=False,
                must_include=("novelty", "contradiction pressure"),
                notes="Clean CSD target should stay protected despite other correction chains.",
            ),
        ),
    ]

    refs: dict[str, str] = {}
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="agent_workflow_selector_") as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp), embedding_backend)
        try:
            for index, step in enumerate(steps, start=1):
                if step.action in {"teach", "correct"}:
                    assert step.write is not None
                    write = step.write
                    if step.action == "teach":
                        taught = pipeline.teach(
                            write.text,
                            source=write.source,
                            namespace=namespace,
                            session_id=session_id,
                            agent_id=agent_id,
                            store_session=True,
                            domain=write.domain,
                            memory_type=write.memory_type,
                        )
                        memory_id = taught["memory"]["memory_id"]
                    else:
                        target_ids = [refs[write.target_ref]] if write.target_ref and write.target_ref in refs else []
                        corrected = pipeline.correct(
                            write.text,
                            target_memory_ids=target_ids,
                            target_query=write.text,
                            top_k=top_k,
                            source=write.source,
                            namespace=namespace,
                            session_id=session_id,
                            agent_id=agent_id,
                            store_session=True,
                            relation_type="corrects",
                            domain=write.domain,
                            memory_type=write.memory_type,
                        )
                        memory_id = corrected["correction_memory"]["memory_id"]
                    if write.ref:
                        refs[write.ref] = memory_id
                    reports.append(
                        {
                            "step": index,
                            "action": step.action,
                            "ref": write.ref,
                            "target_ref": write.target_ref,
                            "memory_id": memory_id,
                            "text": write.text,
                        }
                    )
                    continue

                assert step.ask is not None
                ask = step.ask
                answer = pipeline.ask(
                    ask.query,
                    top_k=top_k,
                    session_id=session_id,
                    agent_id=agent_id,
                    store_session=True,
                    namespace=namespace,
                    include_global=False,
                )
                retrieval_rows = answer["raw_results"][:top_k]
                features, diagnostics = selector_features_from_retrieval_context(
                    retrieval_rows,
                    condition_name=ask.condition_name,
                )
                explanation = apply_retrieval_explanation_guard(selector.explain(features, top_k=5), features, diagnostics)
                policy = explanation["decision"]["policy"]
                policy_ok = target_matches(policy, ask.target_behavior)
                hard_ok = bool(diagnostics["hard"]) == bool(ask.expected_hard)
                answer_ok, answer_failures = answer_matches(str(answer.get("answer") or ""), ask)
                reports.append(
                    {
                        "step": index,
                        "action": "ask",
                        "query": ask.query,
                        "notes": ask.notes,
                        "answer": answer.get("answer"),
                        "must_include": list(ask.must_include),
                        "must_not_include": list(ask.must_not_include),
                        "answer_ok": answer_ok,
                        "answer_failures": answer_failures,
                        "target_behavior": ask.target_behavior,
                        "expected_hard": ask.expected_hard,
                        "decision": explanation["decision"],
                        "base_decision": explanation.get("base_decision"),
                        "retrieval_guard": explanation.get("retrieval_guard"),
                        "diagnostics": diagnostics,
                        "policy_ok": policy_ok,
                        "hard_ok": hard_ok,
                        "aligned": answer_ok and policy_ok and hard_ok,
                        "evidence": [
                            {
                                "memory_id": row.get("memory_id"),
                                "authority_state": row.get("authority_state"),
                                "score": row.get("score"),
                                "text": row.get("text"),
                            }
                            for row in answer.get("evidence", [])
                        ],
                        "raw_results": [
                            {
                                "memory_id": row.get("memory_id"),
                                "authority_state": row.get("authority_state"),
                                "score": row.get("score"),
                                "text_match_score": row.get("text_match_score"),
                                "claim_scope_score": row.get("claim_scope_score"),
                                "correction_relevance_score": row.get("correction_relevance_score"),
                                "source": row.get("source"),
                                "text": row.get("text"),
                            }
                            for row in answer.get("raw_results", [])[:top_k]
                        ],
                    }
                )
        finally:
            pipeline.close()

    ask_reports = [row for row in reports if row["action"] == "ask"]
    aligned = sum(1 for row in ask_reports if row["aligned"])
    return {
        "ok": True,
        "purpose": "Multi-turn agent workflow integration eval for answer correctness and retrieval-aware selector behavior.",
        "embedding_backend": embedding_backend,
        "top_k": top_k,
        "ask_count": len(ask_reports),
        "aligned_asks": aligned,
        "alignment_rate": aligned / max(1, len(ask_reports)),
        "steps": reports,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Agent Workflow Selector Integration Eval",
        "",
        f"Embedding backend: `{report['embedding_backend']}`",
        f"Ask alignment: **{report['aligned_asks']} / {report['ask_count']}**",
        f"Alignment rate: **{report['alignment_rate']:.3f}**",
        "",
        "| Step | Query | Target | Expected Hard | Actual Hard | Policy | Answer | Aligned |",
        "|---:|---|---|---:|---:|---|---:|---:|",
    ]
    for row in report["steps"]:
        if row["action"] != "ask":
            continue
        lines.append(
            "| {step} | {query} | {target} | {expected} | {hard} | `{policy}` | {answer_ok} | {aligned} |".format(
                step=row["step"],
                query=row["query"],
                target=row["target_behavior"],
                expected=row["expected_hard"],
                hard=row["diagnostics"]["hard"],
                policy=row["decision"]["policy"],
                answer_ok="yes" if row["answer_ok"] else "no",
                aligned="yes" if row["aligned"] else "no",
            )
        )
    mismatches = [row for row in report["steps"] if row["action"] == "ask" and not row["aligned"]]
    lines.extend(["", "## Mismatches", ""])
    if not mismatches:
        lines.append("- None")
    for row in mismatches:
        lines.append(
            f"- Step {row['step']} `{row['query']}`: answer_ok={row['answer_ok']} "
            f"policy_ok={row['policy_ok']} hard_ok={row['hard_ok']} failures={row['answer_failures']}"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-turn integration eval for the CLC-GCL selector architecture.")
    parser.add_argument("--embedding-backend", choices=["hash", "config"], default="hash")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    out_json, out_md = output_paths(args.embedding_backend)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    report = run_workflow(args.embedding_backend, args.top_k)
    report["outputs"] = {"json": str(out_json), "markdown": str(out_md)}
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "embedding_backend": report["embedding_backend"],
                "alignment_rate": report["alignment_rate"],
                "aligned_asks": report["aligned_asks"],
                "ask_count": report["ask_count"],
                "json": str(out_json),
                "markdown": str(out_md),
                "mismatches": [
                    {
                        "step": row["step"],
                        "query": row["query"],
                        "answer_ok": row["answer_ok"],
                        "policy_ok": row["policy_ok"],
                        "hard_ok": row["hard_ok"],
                        "policy": row["decision"]["policy"],
                        "actual_hard": row["diagnostics"]["hard"],
                        "answer_failures": row["answer_failures"],
                    }
                    for row in report["steps"]
                    if row["action"] == "ask" and not row["aligned"]
                ],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
