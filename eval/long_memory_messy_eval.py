from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.pipeline import MemoryPipeline
from core.runtime import create_pipeline, init_db


@dataclass
class MessyCase:
    id: str
    ability: str
    query: str
    expected_terms: list[str]
    expected_sources: list[str] | None = None
    forbidden_terms: list[str] | None = None
    should_abstain: bool = False
    should_conflict: bool = False


def make_pipeline(db_path: Path, fast_hash: bool, embedding_dim: int) -> MemoryPipeline:
    if not fast_hash:
        return create_pipeline(ROOT, db_path=db_path)
    config = load_config(ROOT)
    init_db(ROOT, db_path)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": int(embedding_dim)},
        retrieval_weights=config.get("retrieval_weights"),
    )


def has_all_terms(text: str, terms: list[str]) -> bool:
    lower = str(text or "").lower()
    return all(term.lower() in lower for term in terms)


def has_any_terms(text: str, terms: list[str] | None) -> bool:
    lower = str(text or "").lower()
    return any(term.lower() in lower for term in terms or [])


def answer_sources(answer: dict[str, Any]) -> list[str]:
    items = (
        list(answer.get("evidence") or [])
        + list(answer.get("source_context") or [])
        + list(answer.get("stale_context") or [])
        + list(answer.get("stale") or [])
    )
    return [str(item.get("source") or "") for item in items]


def source_ok(answer: dict[str, Any], expected_sources: list[str] | None) -> bool:
    if not expected_sources:
        return True
    sources = [source.lower() for source in answer_sources(answer)]
    return all(any(expected.lower() in source for source in sources) for expected in expected_sources)


def seed_irrelevant_turns(pipeline: MemoryPipeline, namespace: str, count: int) -> None:
    fillers = [
        "calendar grooming",
        "design review",
        "draft outline",
        "tool migration",
        "runtime notebook",
        "style notes",
        "interface polish",
        "diagnostic run",
    ]
    for idx in range(count):
        topic = fillers[idx % len(fillers)]
        pipeline.teach(
            (
                f"Messy background turn {idx:03d}: the {topic} note mentions ArchiveBox{idx:03d}, "
                f"but it does not define agent preferences, project owners, tokens, or current policy."
            ),
            namespace=namespace,
            agent_id="messy_memory_agent",
            source=f"messy/noise/turn_{idx:03d}.md",
            store_session=idx % 5 == 0,
        )


def seed_messy_information(pipeline: MemoryPipeline, namespace: str) -> MessyCase:
    session = pipeline.db.create_session(
        agent_id="messy_memory_agent",
        title="messy information extraction",
        metadata={"scenario": "buried_profile"},
    )
    source = "messy/info/nora_profile_turn.md"
    pipeline.teach(
        (
            "Conversation fragment from Nora: ignore the old mailbox note; for review packets, "
            "Nora's routing tag is Lantern-4. The lunch preference in the same message is soup."
        ),
        namespace=namespace,
        agent_id="messy_memory_agent",
        session_id=session["id"],
        source=source,
        store_session=True,
    )
    pipeline.teach(
        "Follow-up chatter: Nora liked the soup note, but this does not change the routing tag.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        session_id=session["id"],
        source="messy/info/nora_chatter.md",
        store_session=True,
    )
    return MessyCase(
        id="messy_info_nora_tag",
        ability="messy_information_extraction",
        query="For Nora's review packet, which routing tag should be used?",
        expected_terms=["Lantern-4"],
        expected_sources=[source],
        forbidden_terms=["soup"],
    )


def seed_temporal_update(pipeline: MemoryPipeline, namespace: str) -> MessyCase:
    old_source = "messy/temporal/atlas_v1.md"
    new_source = "messy/temporal/atlas_v2.md"
    old = pipeline.teach(
        "January planning memory: Atlas rollout owner is Devon and the current rollout room is North Annex.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        source=old_source,
        store_session=False,
    )
    pipeline.teach(
        "Unrelated update: Atlas dashboard theme is graphite and the icon set is square.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        source="messy/temporal/atlas_unrelated.md",
        store_session=False,
    )
    pipeline.correct(
        "April correction: Atlas rollout owner is Devon and the current rollout room is East Studio, not North Annex.",
        target_memory_ids=[old["memory"]["memory_id"]],
        namespace=namespace,
        agent_id="messy_memory_agent",
        source=new_source,
        store_session=False,
    )
    return MessyCase(
        id="messy_temporal_atlas_room",
        ability="temporal_update",
        query="After the later Atlas update, where is Devon running the rollout now?",
        expected_terms=["East Studio"],
        expected_sources=[new_source],
        forbidden_terms=["current rollout room is North Annex"],
        should_conflict=True,
    )


def seed_multi_hop(pipeline: MemoryPipeline, namespace: str) -> MessyCase:
    project_source = "messy/multihop/project_owner.md"
    code_source = "messy/multihop/owner_code.md"
    pipeline.teach(
        "Project mapping: Project Juniper is owned by Imani. Project Larch is owned by Tomas.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        source=project_source,
        store_session=False,
    )
    pipeline.teach(
        "Owner contact code table: Imani uses contact code Prism-22. Tomas uses contact code Ember-91.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        source=code_source,
        store_session=False,
    )
    return MessyCase(
        id="messy_multihop_juniper_code",
        ability="multi_hop_association",
        query="What contact code belongs to the owner of Project Juniper?",
        expected_terms=["Imani", "Prism-22"],
        expected_sources=[project_source, code_source],
        forbidden_terms=["Ember-91", "Tomas"],
    )


def seed_session_topic_switch(pipeline: MemoryPipeline, namespace: str) -> MessyCase:
    session = pipeline.db.create_session(
        agent_id="messy_memory_agent",
        title="topic switching session",
        metadata={"scenario": "session_topic_switch"},
    )
    session_id = session["id"]
    source = "messy/session/active_policy.md"
    pipeline.teach(
        "Session topic A: the active safety policy says repository upload requires explicit user approval.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        session_id=session_id,
        source=source,
        store_session=True,
    )
    pipeline.ask(
        "Can repository upload happen without explicit user approval?",
        namespace=namespace,
        agent_id="messy_memory_agent",
        session_id=session_id,
        include_global=False,
        store_session=True,
    )
    pipeline.teach(
        "Session topic B: the visual design palette for the demo uses moss, white, and charcoal.",
        namespace=namespace,
        agent_id="messy_memory_agent",
        session_id=session_id,
        source="messy/session/palette.md",
        store_session=True,
    )
    return MessyCase(
        id="messy_session_upload_policy",
        ability="session_topic_switch",
        query="In that earlier policy topic, what approval is needed before repository upload?",
        expected_terms=["explicit user approval"],
        expected_sources=[source],
        forbidden_terms=["moss", "charcoal"],
    )


def seed_abstention(_: MemoryPipeline, __: str) -> MessyCase:
    return MessyCase(
        id="messy_abstain_private_key",
        ability="abstention_under_noise",
        query="What is Nora's private signing key?",
        expected_terms=[],
        should_abstain=True,
    )


def build_benchmark(pipeline: MemoryPipeline, namespace: str, noise_count: int) -> list[MessyCase]:
    seed_irrelevant_turns(pipeline, namespace, noise_count)
    return [
        seed_messy_information(pipeline, namespace),
        seed_temporal_update(pipeline, namespace),
        seed_multi_hop(pipeline, namespace),
        seed_session_topic_switch(pipeline, namespace),
        seed_abstention(pipeline, namespace),
    ]


def evaluate_case(pipeline: MemoryPipeline, namespace: str, case: MessyCase, top_k: int) -> dict[str, Any]:
    answer = pipeline.ask(case.query, namespace=namespace, include_global=False, top_k=top_k, store_session=False)
    answer_text = str(answer.get("answer") or "")
    abstained = "not have enough memory evidence" in answer_text.lower()
    if case.should_abstain:
        answer_ok = abstained
        sources_ok = True
        forbidden_ok = True
    else:
        answer_ok = has_all_terms(answer_text, case.expected_terms)
        sources_ok = source_ok(answer, case.expected_sources)
        forbidden_ok = not has_any_terms(answer_text, case.forbidden_terms)
    conflict_ok = True if not case.should_conflict else bool(answer.get("conflict"))
    return {
        "id": case.id,
        "ability": case.ability,
        "query": case.query,
        "answer": answer_text,
        "answer_ok": answer_ok,
        "source_ok": sources_ok,
        "forbidden_ok": forbidden_ok,
        "conflict_ok": conflict_ok,
        "confidence": answer.get("confidence"),
        "conflict": answer.get("conflict"),
        "expected_terms": case.expected_terms,
        "expected_sources": case.expected_sources,
        "forbidden_terms": case.forbidden_terms,
        "evidence_sources": [item.get("source") for item in answer.get("evidence") or []],
        "source_context_sources": [item.get("source") for item in answer.get("source_context") or []],
        "stale_context_sources": [item.get("source") for item in answer.get("stale_context") or []],
    }


def row_passed(row: dict[str, Any]) -> bool:
    return bool(row["answer_ok"] and row["source_ok"] and row["forbidden_ok"] and row["conflict_ok"])


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1.0 if row.get(key) else 0.0 for row in rows) / len(rows), 4)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    abilities = sorted({row["ability"] for row in rows})
    return {
        "count": len(rows),
        "pass_rate": round(sum(1.0 if row_passed(row) else 0.0 for row in rows) / max(1, len(rows)), 4),
        "answer_accuracy": mean_bool(rows, "answer_ok"),
        "source_accuracy": mean_bool(rows, "source_ok"),
        "forbidden_accuracy": mean_bool(rows, "forbidden_ok"),
        "conflict_accuracy": mean_bool(rows, "conflict_ok"),
        "by_ability": {
            ability: {
                "count": len([row for row in rows if row["ability"] == ability]),
                "pass_rate": mean_bool([row for row in rows if row["ability"] == ability], "passed"),
                "answer_accuracy": mean_bool([row for row in rows if row["ability"] == ability], "answer_ok"),
                "source_accuracy": mean_bool([row for row in rows if row["ability"] == ability], "source_ok"),
            }
            for ability in abilities
        },
    }


def write_report(payload: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(
    db_path: Path,
    top_k: int,
    noise_count: int,
    fast_hash: bool,
    embedding_dim: int,
    include_rows: bool,
) -> dict[str, Any]:
    start = time.perf_counter()
    timings: dict[str, float] = {}
    namespace = "agent:lme_messy_benchmark"
    stage_start = time.perf_counter()
    pipeline = make_pipeline(db_path, fast_hash=fast_hash, embedding_dim=embedding_dim)
    timings["pipeline_init_sec"] = round(time.perf_counter() - stage_start, 6)
    try:
        stage_start = time.perf_counter()
        cases = build_benchmark(pipeline, namespace, noise_count)
        timings["seed_sec"] = round(time.perf_counter() - stage_start, 6)
        stage_start = time.perf_counter()
        rows = [evaluate_case(pipeline, namespace, case, top_k=top_k) for case in cases]
        for row in rows:
            row["passed"] = row_passed(row)
        timings["query_eval_sec"] = round(time.perf_counter() - stage_start, 6)
        stage_start = time.perf_counter()
        stats = pipeline.db.stats()
        cache_stats_fn = getattr(pipeline.encoder, "cache_stats", None)
        embedding_cache = cache_stats_fn() if callable(cache_stats_fn) else None
        timings["stats_sec"] = round(time.perf_counter() - stage_start, 6)
    finally:
        stage_start = time.perf_counter()
        pipeline.close()
        timings["close_sec"] = round(time.perf_counter() - stage_start, 6)
    summary = summarize(rows)
    weak = [row for row in rows if not row["passed"]]
    payload = {
        "ok": summary["pass_rate"] >= 0.80 and summary["answer_accuracy"] >= 0.80 and summary["source_accuracy"] >= 0.80,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "embedding_mode": "hash" if fast_hash else "configured",
        "noise_count": noise_count,
        "top_k": top_k,
        "summary": summary,
        "weak_case_count": len(weak),
        "weak_cases": weak,
        "stats": stats,
        "timings": timings,
        "embedding_cache": embedding_cache,
    }
    if include_rows:
        payload["rows"] = rows
    return payload


def print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("Messy Long Memory Eval")
    print(f"ok: {payload['ok']}")
    print(f"embedding: {payload['embedding_mode']}")
    print(f"cases: {summary['count']} | noise: {payload['noise_count']} | elapsed_sec: {payload['elapsed_sec']}")
    timings = payload.get("timings") or {}
    print(
        "timings: "
        f"init={timings.get('pipeline_init_sec', 0.0):.4f}s "
        f"seed={timings.get('seed_sec', 0.0):.4f}s "
        f"query={timings.get('query_eval_sec', 0.0):.4f}s"
    )
    if payload.get("embedding_cache"):
        cache = payload["embedding_cache"]
        print(f"embedding_cache: entries={cache.get('entries')} hits={cache.get('hits')} path={cache.get('path')}")
    print(
        "overall: "
        f"pass={summary['pass_rate']:.4f} "
        f"answer={summary['answer_accuracy']:.4f} "
        f"source={summary['source_accuracy']:.4f} "
        f"forbidden={summary['forbidden_accuracy']:.4f} "
        f"conflict={summary['conflict_accuracy']:.4f}"
    )
    print("by ability:")
    for ability, row in summary["by_ability"].items():
        print(
            f"- {ability}: pass={row['pass_rate']:.4f} answer={row['answer_accuracy']:.4f} "
            f"source={row['source_accuracy']:.4f}"
        )
    if payload["weak_cases"]:
        print("weak cases:")
        for row in payload["weak_cases"]:
            print(f"- {row['id']} [{row['ability']}]: {row['answer'][:180]}")
    else:
        print("weak cases: none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a messy LongMemEval-inspired memory pressure test.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--noise-count", type=int, default=80)
    parser.add_argument("--configured-embedding", action="store_true", help="Use config.yaml embedding backend instead of hash.")
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--include-rows", action="store_true")
    parser.add_argument("--save-report", default=None)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    fast_hash = not args.configured_embedding
    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(db_path, args.top_k, args.noise_count, fast_hash, args.embedding_dim, args.include_rows)
    else:
        with TemporaryDirectory() as tmp:
            payload = run(
                Path(tmp) / "long_memory_messy.db",
                args.top_k,
                args.noise_count,
                fast_hash,
                args.embedding_dim,
                args.include_rows,
            )
    if args.save_report:
        report_path = Path(args.save_report)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        payload["saved_report"] = str(report_path)
        write_report(payload, report_path)
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print_text(payload)
        if args.save_report:
            print(f"saved_report: {payload['saved_report']}")
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
