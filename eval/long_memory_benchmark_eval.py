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
class BenchmarkCase:
    id: str
    ability: str
    query: str
    expected_terms: list[str]
    expected_source: str | None = None
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


def source_matches(answer: dict[str, Any], expected_source: str | None) -> bool:
    if not expected_source:
        return True
    sources = [
        str(item.get("source") or "").lower()
        for item in list(answer.get("evidence") or [])
        + list(answer.get("source_context") or [])
        + list(answer.get("stale_context") or [])
        + list(answer.get("stale") or [])
    ]
    return any(expected_source.lower() in source for source in sources)


def top_source_matches(answer: dict[str, Any], expected_source: str | None) -> bool:
    if not expected_source:
        return True
    evidence = answer.get("evidence") or []
    if not evidence:
        return False
    return expected_source.lower() in str(evidence[0].get("source") or "").lower()


def add_noise(pipeline: MemoryPipeline, namespace: str, noise_count: int) -> None:
    topics = ["planning", "interface", "logging", "review", "notebook", "prototype", "diagnostic", "runtime"]
    for idx in range(noise_count):
        topic = topics[idx % len(topics)]
        pipeline.teach(
            (
                f"LME distractor {idx:04d}: routine {topic} note for workspace item "
                f"NoiseItem{idx:04d} uses ordinary label NoiseLabel{idx:04d}."
            ),
            namespace=namespace,
            agent_id="long_benchmark_agent",
            source=f"lme/noise/noise_{idx:04d}.md",
            store_session=False,
        )


def seed_information_extraction(pipeline: MemoryPipeline, namespace: str, count: int) -> list[BenchmarkCase]:
    cases = []
    for idx in range(count):
        project = f"Project{idx:03d}"
        phrase = f"AccessPhrase{idx:03d}"
        source = f"lme/info/info_{idx:03d}.md"
        pipeline.teach(
            f"LME information extraction fact {idx}: {project} uses access phrase {phrase}.",
            namespace=namespace,
            agent_id="long_benchmark_agent",
            source=source,
            store_session=False,
        )
        cases.append(
            BenchmarkCase(
                id=f"info_{idx:03d}",
                ability="information_extraction",
                query=f"What access phrase does {project} use?",
                expected_terms=[phrase],
                expected_source=source,
            )
        )
    return cases


def seed_multi_session(pipeline: MemoryPipeline, namespace: str, count: int) -> list[BenchmarkCase]:
    cases = []
    for idx in range(count):
        city = f"City{idx:03d}"
        hotel = f"Hotel{idx:03d}"
        session = pipeline.db.create_session(
            agent_id="long_benchmark_agent",
            title=f"multi session {idx:03d}",
            metadata={"ability": "multi_session"},
        )
        session_id = session["id"]
        pipeline.teach(
            f"LME multi-session setup {idx}: travel notebook topic is {city}.",
            namespace=namespace,
            agent_id="long_benchmark_agent",
            session_id=session_id,
            source=f"lme/multi/topic_{idx:03d}.md",
            store_session=True,
        )
        source = f"lme/multi/detail_{idx:03d}.md"
        pipeline.teach(
            f"LME multi-session detail {idx}: the hotel chosen for {city} is {hotel}.",
            namespace=namespace,
            agent_id="long_benchmark_agent",
            session_id=session_id,
            source=source,
            store_session=True,
        )
        cases.append(
            BenchmarkCase(
                id=f"multi_{idx:03d}",
                ability="multi_session",
                query=f"Which hotel was chosen for {city}?",
                expected_terms=[hotel],
                expected_source=source,
            )
        )
    return cases


def seed_temporal_updates(
    pipeline: MemoryPipeline,
    namespace: str,
    count: int,
    ability: str,
    source_prefix: str,
) -> list[BenchmarkCase]:
    cases = []
    for idx in range(count):
        item = f"{source_prefix.title()}Item{idx:03d}"
        old_value = f"Old{source_prefix.title()}Value{idx:03d}"
        new_value = f"New{source_prefix.title()}Value{idx:03d}"
        old_source = f"lme/{source_prefix}/old_{idx:03d}.md"
        new_source = f"lme/{source_prefix}/new_{idx:03d}.md"
        old = pipeline.teach(
            f"LME {ability} old fact {idx}: current value for {item} is {old_value}.",
            namespace=namespace,
            agent_id="long_benchmark_agent",
            source=old_source,
            store_session=False,
        )
        pipeline.correct(
            f"LME {ability} correction {idx}: current value for {item} is {new_value}, not {old_value}.",
            target_memory_ids=[old["memory"]["memory_id"]],
            namespace=namespace,
            agent_id="long_benchmark_agent",
            source=new_source,
            store_session=False,
        )
        cases.append(
            BenchmarkCase(
                id=f"{source_prefix}_{idx:03d}",
                ability=ability,
                query=f"What is the current value for {item}?",
                expected_terms=[new_value],
                expected_source=new_source,
                forbidden_terms=[f"current value for {item} is {old_value}"],
                should_conflict=True,
            )
        )
    return cases


def seed_abstention(count: int) -> list[BenchmarkCase]:
    return [
        BenchmarkCase(
            id=f"abstain_{idx:03d}",
            ability="abstention",
            query=f"What is the secret token for Vault{idx:03d}?",
            expected_terms=[],
            should_abstain=True,
        )
        for idx in range(count)
    ]


def build_benchmark(pipeline: MemoryPipeline, namespace: str, cases_per_ability: int, noise_count: int) -> list[BenchmarkCase]:
    add_noise(pipeline, namespace, noise_count)
    cases: list[BenchmarkCase] = []
    cases.extend(seed_information_extraction(pipeline, namespace, cases_per_ability))
    cases.extend(seed_multi_session(pipeline, namespace, cases_per_ability))
    cases.extend(seed_temporal_updates(pipeline, namespace, cases_per_ability, "temporal_reasoning", "temporal"))
    cases.extend(seed_temporal_updates(pipeline, namespace, cases_per_ability, "knowledge_update", "update"))
    cases.extend(seed_abstention(cases_per_ability))
    return cases


def evaluate_case(pipeline: MemoryPipeline, namespace: str, case: BenchmarkCase, top_k: int) -> dict[str, Any]:
    answer = pipeline.ask(case.query, namespace=namespace, include_global=False, top_k=top_k, store_session=False)
    answer_text = str(answer.get("answer") or "")
    abstained = "not have enough memory evidence" in answer_text.lower()
    if case.should_abstain:
        answer_ok = abstained
        source_ok = True
        forbidden_ok = True
    else:
        answer_ok = has_all_terms(answer_text, case.expected_terms)
        source_ok = source_matches(answer, case.expected_source)
        forbidden_ok = not has_any_terms(answer_text, case.forbidden_terms)
    top_source_ok = True if case.should_abstain else top_source_matches(answer, case.expected_source)
    conflict_ok = True if not case.should_conflict else bool(answer.get("conflict"))
    return {
        "id": case.id,
        "ability": case.ability,
        "query": case.query,
        "answer": answer_text,
        "answer_ok": answer_ok,
        "source_ok": source_ok,
        "top_source_ok": top_source_ok,
        "forbidden_ok": forbidden_ok,
        "conflict_ok": conflict_ok,
        "confidence": answer.get("confidence"),
        "conflict": answer.get("conflict"),
        "evidence_ids": [item.get("memory_id") for item in answer.get("evidence") or []],
        "evidence_sources": [item.get("source") for item in answer.get("evidence") or []],
    }


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1.0 if row.get(key) else 0.0 for row in rows) / len(rows), 4)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    abilities = sorted({row["ability"] for row in rows})
    by_ability = {}
    for ability in abilities:
        ability_rows = [row for row in rows if row["ability"] == ability]
        by_ability[ability] = {
            "count": len(ability_rows),
            "answer_accuracy": mean_bool(ability_rows, "answer_ok"),
            "source_accuracy": mean_bool(ability_rows, "source_ok"),
            "top_source_accuracy": mean_bool(ability_rows, "top_source_ok"),
            "forbidden_accuracy": mean_bool(ability_rows, "forbidden_ok"),
            "conflict_accuracy": mean_bool(ability_rows, "conflict_ok"),
        }
    return {
        "count": len(rows),
        "answer_accuracy": mean_bool(rows, "answer_ok"),
        "source_accuracy": mean_bool(rows, "source_ok"),
        "top_source_accuracy": mean_bool(rows, "top_source_ok"),
        "forbidden_accuracy": mean_bool(rows, "forbidden_ok"),
        "conflict_accuracy": mean_bool(rows, "conflict_ok"),
        "by_ability": by_ability,
    }


def weak_cases(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    weak = [row for row in rows if not case_passed(row)]
    return weak[:limit]


def case_passed(row: dict[str, Any]) -> bool:
    return bool(
        row["answer_ok"]
        and row["source_ok"]
        and row["top_source_ok"]
        and row["forbidden_ok"]
        and row["conflict_ok"]
    )


def apply_preset(args: argparse.Namespace) -> None:
    presets = {
        "smoke": {"cases_per_ability": 5, "noise_count": 40},
        "medium": {"cases_per_ability": 20, "noise_count": 150},
        "full": {"cases_per_ability": 40, "noise_count": 300},
    }
    if not args.preset:
        return
    for key, value in presets[args.preset].items():
        if getattr(args, key) is None:
            setattr(args, key, value)


def write_report(payload: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(
    db_path: Path,
    cases_per_ability: int,
    noise_count: int,
    top_k: int,
    fast_hash: bool,
    embedding_dim: int,
    weak_case_limit: int,
    include_rows: bool,
) -> dict[str, Any]:
    start = time.perf_counter()
    timings: dict[str, float] = {}
    namespace = "agent:lme_local_benchmark"
    stage_start = time.perf_counter()
    pipeline = make_pipeline(db_path, fast_hash=fast_hash, embedding_dim=embedding_dim)
    timings["pipeline_init_sec"] = round(time.perf_counter() - stage_start, 6)
    try:
        stage_start = time.perf_counter()
        cases = build_benchmark(pipeline, namespace, cases_per_ability, noise_count)
        timings["seed_sec"] = round(time.perf_counter() - stage_start, 6)
        stage_start = time.perf_counter()
        rows = [evaluate_case(pipeline, namespace, case, top_k) for case in cases]
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
    weak = weak_cases(rows, limit=weak_case_limit)
    payload = {
        "ok": (
            summary["answer_accuracy"] >= 0.88
            and summary["source_accuracy"] >= 0.85
            and summary["conflict_accuracy"] >= 0.95
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "timings": timings,
        "embedding_mode": "hash" if fast_hash else "configured",
        "cases_per_ability": cases_per_ability,
        "noise_count": noise_count,
        "top_k": top_k,
        "summary": summary,
        "weak_case_count": sum(1 for row in rows if not case_passed(row)),
        "weak_cases": weak,
        "stats": stats,
        "embedding_cache": embedding_cache,
    }
    if include_rows:
        payload["rows"] = rows
    return payload


def print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("Long Memory Benchmark Eval")
    print(f"ok: {payload['ok']}")
    print(f"embedding: {payload['embedding_mode']}")
    print(f"cases: {summary['count']} | noise: {payload['noise_count']} | elapsed_sec: {payload['elapsed_sec']}")
    timings = payload.get("timings") or {}
    if timings:
        print(
            "timings: "
            f"init={timings.get('pipeline_init_sec', 0.0):.4f}s "
            f"seed={timings.get('seed_sec', 0.0):.4f}s "
            f"query={timings.get('query_eval_sec', 0.0):.4f}s "
            f"stats={timings.get('stats_sec', 0.0):.4f}s"
        )
    if payload.get("embedding_cache"):
        cache = payload["embedding_cache"]
        print(f"embedding_cache: entries={cache.get('entries')} hits={cache.get('hits')} path={cache.get('path')}")
    print(
        "overall: "
        f"answer={summary['answer_accuracy']:.4f} "
        f"source={summary['source_accuracy']:.4f} "
        f"top_source={summary['top_source_accuracy']:.4f} "
        f"forbidden={summary['forbidden_accuracy']:.4f} "
        f"conflict={summary['conflict_accuracy']:.4f}"
    )
    print("by ability:")
    for ability, row in summary["by_ability"].items():
        print(
            f"- {ability}: answer={row['answer_accuracy']:.4f} source={row['source_accuracy']:.4f} "
            f"top={row['top_source_accuracy']:.4f} conflict={row['conflict_accuracy']:.4f}"
        )
    if payload["weak_cases"]:
        print("weak cases:")
        for row in payload["weak_cases"]:
            print(f"- {row['id']} [{row['ability']}]: {row['answer'][:180]}")
    else:
        print("weak cases: none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a LongMemEval-inspired synthetic benchmark against the memory core.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--preset", choices=["smoke", "medium", "full"], default=None)
    parser.add_argument("--cases-per-ability", type=int, default=None)
    parser.add_argument("--noise-count", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fast-hash", action="store_true", default=True)
    parser.add_argument("--configured-embedding", action="store_true", help="Use configured embedding backend instead of fast hash.")
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--weak-case-limit", type=int, default=12)
    parser.add_argument("--include-rows", action="store_true", help="Include every evaluated case in the JSON payload/report.")
    parser.add_argument("--save-report", default=None, help="Write the JSON payload to this path.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()
    apply_preset(args)
    if args.cases_per_ability is None:
        args.cases_per_ability = 40
    if args.noise_count is None:
        args.noise_count = 300

    fast_hash = not args.configured_embedding
    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(
            db_path,
            args.cases_per_ability,
            args.noise_count,
            args.top_k,
            fast_hash,
            args.embedding_dim,
            args.weak_case_limit,
            args.include_rows,
        )
    else:
        with TemporaryDirectory() as tmp:
            payload = run(
                Path(tmp) / "long_memory_benchmark.db",
                args.cases_per_ability,
                args.noise_count,
                args.top_k,
                fast_hash,
                args.embedding_dim,
                args.weak_case_limit,
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
