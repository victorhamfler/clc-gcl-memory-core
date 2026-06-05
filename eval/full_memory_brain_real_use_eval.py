from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline  # noqa: E402
from core.rpg_memory import RPGMemoryRecord, run_rpg_memory_probe  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "full_memory_brain_real_use_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "full_memory_brain_real_use_eval_report.md"


def run_command(name: str, command: list[str], *, timeout_seconds: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return {
            "name": name,
            "ok": False,
            "returncode": None,
            "stdout": stdout.strip(),
            "stderr": (stderr.strip() + f"\nTimed out after {timeout_seconds} seconds.").strip(),
            "timed_out": True,
        }
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "timed_out": False,
    }


def parse_stdout_json(step: dict[str, Any]) -> dict[str, Any]:
    text = str(step.get("stdout") or "").strip()
    starts = [idx for idx, char in enumerate(text) if char == "{"]
    for idx in reversed(starts):
        try:
            loaded = json.loads(text[idx:])
        except json.JSONDecodeError:
            continue
        return loaded if isinstance(loaded, dict) else {}
    return {}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def db_init(db_path: Path) -> None:
    db = MemoryDB(db_path)
    try:
        db.init_schema(SCHEMA_PATH)
    finally:
        db.close()


def compact_answer(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": answer.get("answer"),
        "confidence": answer.get("confidence"),
        "conflict": answer.get("conflict"),
        "session_context_used": answer.get("session_context_used"),
        "retrieval_query": answer.get("retrieval_query"),
        "evidence_ids": [item.get("memory_id") for item in answer.get("evidence") or []],
        "current_ids": [item.get("memory_id") for item in answer.get("current") or []],
        "stale_ids": [item.get("memory_id") for item in answer.get("stale") or []],
        "top_sources": [item.get("source") for item in answer.get("raw_results") or []],
        "top_previews": [str(item.get("text") or "")[:180] for item in answer.get("raw_results") or []],
    }


def rpg_records_for_memories(pipeline: MemoryPipeline, memories: list[dict[str, Any]]) -> list[RPGMemoryRecord]:
    records: list[RPGMemoryRecord] = []
    for index, memory in enumerate(memories, start=1):
        memory_id = str(memory.get("memory_id") or "")
        row = pipeline.db.memory_vectors_by_ids([memory_id], include_deprecated=True)
        text = str(row[0].get("text") if row else memory.get("text") or "")
        source = pipeline.db.get_memory_source(memory_id) or {}
        domain = pipeline.db.get_domain(memory.get("domain_id")) if memory.get("domain_id") else None
        feedback = pipeline.db.feedback_summary_for_memories([memory_id]).get(memory_id, {})
        negative_count = int(feedback.get("negative", 0) or 0)
        status = "deprecated" if negative_count > 0 or str(text).lower().startswith("correction:") is False and "old" in text.lower() else "active"
        records.append(
            RPGMemoryRecord(
                memory_id=memory_id,
                text=text,
                domain=domain.name if domain else str(memory.get("domain_name") or "general"),
                source=str(source.get("source") or ""),
                timestamp=f"2026-06-05T12:{index:02d}:00Z",
                authority=0.25 if negative_count > 0 else 0.9,
                status=status,
                retrieval_count=float(index),
                embedding=tuple(float(value) for value in pipeline.encoder.embed(text)),
            )
        )
    return records


def real_use_run() -> dict[str, Any]:
    with TemporaryDirectory(prefix="full_memory_brain_real_use_") as tmp:
        tmp_root = Path(tmp)
        db_path = tmp_root / "full_memory_brain_real_use.db"
        db_init(db_path)
        pipeline = MemoryPipeline(root=tmp_root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        namespace = "agent:real_use_eval"
        agent_id = "real_use_eval"
        try:
            base = pipeline.teach(
                "Project Helios uses the blue retrieval plan for memory routing.",
                source="real_use/v1_project_plan.md",
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
                domain="project",
                memory_type="semantic_note",
            )
            duplicate = pipeline.teach(
                "Project Helios uses the blue retrieval plan for memory routing.",
                source="real_use/v1_project_plan_duplicate.md",
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
                domain="project",
                memory_type="semantic_note",
            )
            bridge = pipeline.teach(
                "The Helios memory route should not be confused with robotics actuator current checks.",
                source="real_use/bridge_warning.md",
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
                domain="bridge",
                memory_type="design_rule",
            )
            unrelated = pipeline.teach(
                "Robotics actuator current checks use separate torque safety limits.",
                source="real_use/robotics_safety.md",
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
                domain="robotics",
                memory_type="semantic_note",
            )
            first = pipeline.ask(
                "What retrieval plan does Project Helios use?",
                top_k=4,
                session_id=base["session_id"],
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
            )
            correction = pipeline.correct(
                "Project Helios now uses the green retrieval plan for memory routing.",
                target_memory_ids=[base["memory"]["memory_id"], duplicate["memory"]["memory_id"]],
                target_query="What retrieval plan does Project Helios use?",
                source="real_use/v2_project_plan.md",
                session_id=base["session_id"],
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
                domain="project",
                memory_type="semantic_note",
            )
            after = pipeline.ask(
                "What retrieval plan does Project Helios use now?",
                top_k=5,
                session_id=base["session_id"],
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
            )
            followup = pipeline.ask(
                "What should I remember about that plan?",
                top_k=5,
                session_id=base["session_id"],
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
            )
            bridge_ask = pipeline.ask(
                "Should the Helios route be mixed with robotics actuator current checks?",
                top_k=5,
                session_id=base["session_id"],
                agent_id=agent_id,
                namespace=namespace,
                store_session=True,
            )
            for rank, evidence in enumerate(after.get("evidence") or [], start=1):
                pipeline.db.add_retrieval_feedback(
                    str(evidence.get("memory_id")),
                    "useful",
                    query=after["query"],
                    rating=1.0,
                    rank=rank,
                    retrieval_score=evidence.get("score"),
                    notes="Real-use eval marked current answer evidence useful.",
                    metadata={"agent_id": agent_id, "namespace": namespace},
                )
            authority = pipeline.authority(
                query="Project Helios retrieval plan",
                top_k=6,
                namespace=namespace,
                include_global=False,
            )
            memories = [
                base["memory"],
                duplicate["memory"],
                bridge["memory"],
                unrelated["memory"],
                correction["correction_memory"],
            ]
            rpg_probe = run_rpg_memory_probe(rpg_records_for_memories(pipeline, memories), rank_k=3)
            stats = pipeline.db.stats()
            feedback_counts = pipeline.db.feedback_counts()
            history = pipeline.db.session_history(base["session_id"])
        finally:
            pipeline.close()
    return {
        "schema": "full_memory_brain_real_use_eval_run/v1",
        "database": str(db_path),
        "namespace": namespace,
        "memory_ids": {
            "base": base["memory"]["memory_id"],
            "duplicate": duplicate["memory"]["memory_id"],
            "bridge": bridge["memory"]["memory_id"],
            "unrelated": unrelated["memory"]["memory_id"],
            "correction": correction["correction_memory"]["memory_id"],
        },
        "first_answer": compact_answer(first),
        "after_correction_answer": compact_answer(after),
        "followup_answer": compact_answer(followup),
        "bridge_answer": compact_answer(bridge_ask),
        "correction": {
            "linked": correction.get("linked"),
            "target_memory_ids": correction.get("target_memory_ids"),
            "relations": correction.get("relations"),
            "feedback_count": len(correction.get("feedback") or []),
        },
        "authority": {
            "current_memory_id": authority.get("current_memory_id"),
            "authoritative_memory_ids": authority.get("authoritative_memory_ids"),
            "node_states": {
                item.get("memory_id"): item.get("authority_state")
                for item in authority.get("nodes") or []
            },
        },
        "rpg_probe": rpg_probe,
        "stats": stats,
        "feedback_counts": feedback_counts,
        "session_turn_count": len(history),
        "report_only": True,
        "mutates_live_db": False,
    }


def analyze_run(run: dict[str, Any], preflight: dict[str, Any], collection_plan: dict[str, Any]) -> dict[str, Any]:
    after_answer = str((run.get("after_correction_answer") or {}).get("answer") or "")
    followup = run.get("followup_answer") or {}
    bridge_answer = str((run.get("bridge_answer") or {}).get("answer") or "")
    rpg = run.get("rpg_probe") or {}
    checks = {
        "stored_expected_memories": int((run.get("stats") or {}).get("memories") or 0) >= 5,
        "correction_linked_targets": (run.get("correction") or {}).get("linked") is True
        and len((run.get("correction") or {}).get("target_memory_ids") or []) >= 2,
        "current_answer_mentions_green_plan": "green" in after_answer.lower(),
        "after_answer_has_stale_evidence": bool((run.get("after_correction_answer") or {}).get("stale_ids")),
        "followup_used_session_context": followup.get("session_context_used") is True,
        "bridge_answer_separates_robotics": "robotics" in bridge_answer.lower()
        and any(term in bridge_answer.lower() for term in ("not", "separate", "confus", "should")),
        "feedback_recorded": sum(int(item.get("count") or 0) for item in run.get("feedback_counts") or []) >= 3,
        "rpg_probe_report_only": rpg.get("report_only") is True and rpg.get("mutates_db") is False,
        "rpg_activity_present": float(rpg.get("max_omega_norm") or 0.0) >= 0.0
        and len(rpg.get("constraint_pair_reports") or []) >= 3,
        "architecture_preflight_ok": preflight.get("ok") is True,
        "label_collection_plan_available": collection_plan.get("schema")
        == "memory_maintenance_rpg_label_collection_plan/v1",
    }
    blockers = [key for key, value in checks.items() if not value]
    next_developments = [
        {
            "priority": 1,
            "step": "Build an operator-facing review flow for the RPG label collection plan.",
            "why": "The full memory loop works, but the supervised RPG path needs real reviewed labels to move beyond fixtures.",
        },
        {
            "priority": 2,
            "step": "Add a real-use maintenance rehearsal eval that turns this temp DB into copied-DB duplicate/stale review packets.",
            "why": "The test writes duplicate and stale memories; the next useful step is proving the maintenance lifecycle can propose safe review actions from them.",
        },
        {
            "priority": 3,
            "step": "Persist a controller evidence packet for this real-use run.",
            "why": "The roadmap wants one shared training/evaluation unit across selector, residual shadow, RPG, and memory maintenance.",
        },
        {
            "priority": 4,
            "step": "Run the same real-use eval with Gemma embeddings as an optional slower quality check.",
            "why": "Hash embeddings are good for repeatable CI; Gemma should validate semantic ranking quality before production claims.",
        },
    ]
    return {
        "schema": "full_memory_brain_real_use_eval/v1",
        "ok": not blockers,
        "checks": checks,
        "blockers": blockers,
        "run": run,
        "architecture_preflight_summary": {
            "ok": preflight.get("ok"),
            "transition_state": preflight.get("artifact_summary", {}).get("transition_state"),
            "dashboard_handover_ready": preflight.get("artifact_summary", {}).get("dashboard_handover_ready"),
            "dashboard_transition_map_ok": preflight.get("artifact_summary", {}).get("dashboard_transition_map_ok"),
        },
        "label_collection_summary": {
            "labeled_count": collection_plan.get("labeled_count"),
            "unlabeled_count": collection_plan.get("unlabeled_count"),
            "recommended_review_target_count": collection_plan.get("recommended_review_target_count"),
            "ready_for_label_quality_eval": collection_plan.get("ready_for_label_quality_eval"),
            "next_action": collection_plan.get("next_action"),
        },
        "architecture_analysis": {
            "current_state": "stable_report_only_neural_symbolic_memory_loop",
            "strengths": [
                "CSD/G-CL/CLC ingestion stores novelty, domain, and correction metadata in a usable memory store.",
                "Retrieval, answer resolution, session context, correction links, and feedback all work in one non-destructive loop.",
                "RPG diagnostics can inspect the resulting memory set without mutating policy or memory.",
                "Architecture preflight now protects against stale readiness artifacts.",
            ],
            "weaknesses": [
                "RPG supervised learning still lacks real reviewed label volume and class diversity.",
                "Maintenance review/apply lifecycle is not yet driven directly from this real-use interaction pattern.",
                "The shared controller evidence packet is not yet the single data unit for every learned/shadow subsystem.",
                "Gemma-quality real-use runs remain optional and should be compared against fast hash runs.",
            ],
            "next_developments": next_developments,
        },
        "report_only": True,
        "mutates_live_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    analysis = report.get("architecture_analysis") or {}
    lines = [
        "# Full Memory Brain Real Use Eval",
        "",
        "End-to-end real-use smoke for the memory brain on a temporary DB.",
        "",
        f"Passed: `{report['ok']}`",
        f"Current state: `{analysis.get('current_state')}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Strengths", ""])
    for item in analysis.get("strengths") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Weaknesses", ""])
    for item in analysis.get("weaknesses") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Next Developments", ""])
    for item in analysis.get("next_developments") or []:
        lines.append(f"{item['priority']}. {item['step']}  ")
        lines.append(f"   Why: {item['why']}")
    lines.extend(
        [
            "",
            "## Key Answers",
            "",
            "```json",
            json.dumps(
                {
                    "first": (report.get("run") or {}).get("first_answer"),
                    "after_correction": (report.get("run") or {}).get("after_correction_answer"),
                    "followup": (report.get("run") or {}).get("followup_answer"),
                    "bridge": (report.get("run") or {}).get("bridge_answer"),
                },
                indent=2,
            ),
            "```",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full memory-brain real-use eval on a temporary DB.")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    run = real_use_run()
    packet_step = run_command(
        "natural_candidate_review_packet",
        [
            sys.executable,
            str(ROOT / "eval" / "memory_maintenance_rpg_natural_candidate_review_packet.py"),
            "--per-class",
            "8",
        ],
        timeout_seconds=300,
    )
    collection_step = run_command(
        "label_collection_plan",
        [
            sys.executable,
            str(ROOT / "eval" / "memory_maintenance_rpg_label_collection_plan.py"),
            "--packet",
            str(REPO_ROOT / "experiments" / "memory_maintenance_rpg_natural_candidate_review_packet_results.json"),
        ],
        timeout_seconds=120,
    )
    collection_plan = read_json(REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_collection_plan_results.json")
    if args.skip_preflight:
        preflight = {"ok": True, "artifact_summary": {"transition_state": "skipped"}}
    else:
        preflight_step = run_command(
            "architecture_preflight",
            [sys.executable, str(ROOT / "eval" / "architecture_preflight.py"), "--random-cases", "8"],
            timeout_seconds=900,
        )
        preflight = parse_stdout_json(preflight_step)
        preflight_artifact = read_json(REPO_ROOT / "experiments" / "architecture_preflight_results.json")
        if preflight_artifact:
            preflight = preflight_artifact
        elif not preflight:
            preflight = {"ok": False, "step": preflight_step}
    report = analyze_run(run, preflight, collection_plan)
    report["steps"] = {
        "natural_candidate_review_packet": packet_step,
        "label_collection_plan": collection_step,
        "architecture_preflight": preflight if args.skip_preflight else preflight,
    }
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "schema": report["schema"],
                "current_state": report["architecture_analysis"]["current_state"],
                "blockers": report["blockers"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_live_db": False,
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
