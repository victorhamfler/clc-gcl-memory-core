from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chunking import load_texts_from_file
from core.runtime import create_pipeline, pipeline_stats


V1_DIR = ROOT / "test_corpora" / "agent_memory_v1"
V2_DIR = ROOT / "test_corpora" / "agent_memory_v2"
MANIFEST_PATH = ROOT / "test_corpora" / "agent_memory_manifest.json"

QUERY_CASES = [
    {
        "id": "agent_name",
        "query": "What is the current agent name?",
        "v1_terms": ["NovaDesk"],
        "v2_terms": ["LoomGuide"],
        "stale_terms": ["NovaDesk"],
        "expected_sources_v1": ["agent_profile"],
        "expected_sources_v2": ["updates_v2", "corrections_v2"],
        "conflict": True,
    },
    {
        "id": "github_policy",
        "query": "Can the assistant push documentation updates to GitHub automatically?",
        "v1_terms": ["automatically", "documentation updates"],
        "v2_terms": ["must not push", "explicitly asks", "local until"],
        "stale_terms": ["automatically"],
        "expected_sources_v1": ["conflicts_v1", "tool_rules"],
        "expected_sources_v2": ["updates_v2", "corrections_v2"],
        "conflict": True,
    },
    {
        "id": "project_priority",
        "query": "What should Atlas Loom prioritize before a chat interface?",
        "v1_terms": ["chat interface"],
        "v2_terms": ["memory diagnostics", "feedback experiments", "adaptation tests"],
        "stale_terms": ["chat interface before memory diagnostics"],
        "expected_sources_v1": ["conflicts_v1", "project_memory"],
        "expected_sources_v2": ["updates_v2", "corrections_v2", "new_tasks_v2"],
        "conflict": True,
    },
    {
        "id": "user_preferences",
        "query": "What are Mira's preferences for Git commits and GitHub uploads?",
        "v1_terms": ["Windows PowerShell", "does not want Git commits made from WSL", "unless explicitly instructed"],
        "v2_terms": ["GitHub uploads happen only when Mira explicitly asks", "Windows PowerShell"],
        "stale_terms": [],
        "expected_sources_v1": ["user_profile", "tool_rules"],
        "expected_sources_v2": ["user_preferences_v2", "user_profile", "tool_rules"],
        "conflict": False,
    },
    {
        "id": "adaptation_workflow",
        "query": "How should the memory system test adaptation after instructions change?",
        "v1_terms": ["temporary databases", "feedback"],
        "v2_terms": ["temporary memory database", "v2", "stale", "adaptive ranking"],
        "stale_terms": [],
        "expected_sources_v1": ["project_memory", "task_playbook"],
        "expected_sources_v2": ["adaptation_protocol_v2", "new_tasks_v2"],
        "conflict": False,
    },
]


def corpus_files(path: Path) -> list[Path]:
    return sorted(file for file in path.glob("*.md") if file.is_file())


def import_corpus(pipeline, files: list[Path], max_words: int, overlap_words: int) -> dict[str, Any]:
    imported = []
    for file in files:
        texts = load_texts_from_file(file, max_words=max_words, overlap_words=overlap_words)
        result = pipeline.ingest_batch(texts, source=str(file))
        imported.append(
            {
                "file": str(file),
                "chunks": len(texts),
                "stored": result["stored"],
                "skipped": result["skipped"],
                "errors": result["errors"],
            }
        )
    return {
        "files": len(files),
        "chunks": sum(item["chunks"] for item in imported),
        "stored": sum(item["stored"] for item in imported),
        "skipped": sum(item["skipped"] for item in imported),
        "errors": sum(item["errors"] for item in imported),
        "items": imported,
    }


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def apply_manifest_relations(pipeline, manifest: dict[str, Any]) -> dict[str, Any]:
    sources = [item["source"] for item in pipeline.db.source_counts()]
    added = []
    missing = []
    for relation in manifest.get("supersession_relations", []):
        source = find_source_by_suffix(sources, relation.get("source"))
        targets = [find_source_by_suffix(sources, target) for target in relation.get("targets", [])]
        targets = [target for target in targets if target]
        if not source or not targets:
            missing.append(
                {
                    "source": relation.get("source"),
                    "targets": relation.get("targets", []),
                    "resolved_source": source,
                    "resolved_targets": targets,
                }
            )
            continue
        source_ids = pipeline.db.memory_ids_for_source(source)
        target_ids = []
        for target in targets:
            target_ids.extend(pipeline.db.memory_ids_for_source(target))
        for source_id in source_ids:
            for target_id in target_ids:
                pipeline.db.add_relation(
                    source_id,
                    target_id,
                    str(relation.get("relation_type") or "supersedes"),
                    float(relation.get("weight") or 1.0),
                )
                added.append({"source_memory_id": source_id, "target_memory_id": target_id})
    return {
        "manifest": str(MANIFEST_PATH),
        "relations_requested": len(manifest.get("supersession_relations", [])),
        "relations_added": len(added),
        "missing": missing,
    }


def find_source_by_suffix(sources: list[str], suffix: str | None) -> str | None:
    if not suffix:
        return None
    normalized_suffix = normalize_source(suffix)
    for source in sources:
        if normalize_source(source).endswith(normalized_suffix):
            return source
    return None


def normalize_source(source: str) -> str:
    return str(source or "").replace("\\", "/").lower()


def score_terms(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    lower = text.lower()
    hits = sum(1 for term in terms if term.lower() in lower)
    return hits / len(terms)


def score_sources(results: list[dict[str, Any]], expected_sources: list[str]) -> float:
    if not expected_sources:
        return 0.0
    sources = [str(item.get("source") or "").lower() for item in results]
    hits = 0
    for expected in expected_sources:
        if any(expected.lower() in source for source in sources):
            hits += 1
    return hits / len(expected_sources)


def evaluate(pipeline, top_k: int, phase: str) -> list[dict[str, Any]]:
    rows = []
    for case in QUERY_CASES:
        results = pipeline.retrieve(case["query"], top_k=top_k)
        joined = "\n".join(item["text"] for item in results)
        expected_terms = case["v2_terms"] if phase in {"after_v2", "after_feedback"} else case["v1_terms"]
        expected_sources = case["expected_sources_v2"] if phase in {"after_v2", "after_feedback"} else case["expected_sources_v1"]
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                "conflict": case["conflict"],
                "term_score": round(score_terms(joined, expected_terms), 4),
                "source_score": round(score_sources(results, expected_sources), 4),
                "v1_score": round(score_terms(joined, case["v1_terms"]), 4),
                "v2_score": round(score_terms(joined, case["v2_terms"]), 4),
                "stale_score": round(score_terms(joined, case["stale_terms"]), 4),
                "top": [
                    {
                        "memory_id": item["memory_id"],
                        "score": item["score"],
                        "feedback_score": item.get("feedback_score"),
                        "feedback_count": item.get("feedback_count"),
                        "domain_reliability": item.get("domain_reliability"),
                        "source_reliability": item.get("source_reliability"),
                        "supersession_score": item.get("supersession_score"),
                        "relation_supersession_score": item.get("relation_supersession_score"),
                        "source": item.get("source"),
                        "text_preview": item["text"][:240],
                    }
                    for item in results
                ],
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [row for row in rows if row["conflict"]]
    stable = [row for row in rows if not row["conflict"]]
    return {
        "mean_term_score": round(sum(row["term_score"] for row in rows) / len(rows), 4),
        "mean_source_score": round(sum(row["source_score"] for row in rows) / len(rows), 4),
        "conflict_v2_preference": round(sum(row["v2_score"] >= row["v1_score"] for row in conflicts) / len(conflicts), 4),
        "stable_term_score": round(sum(row["term_score"] for row in stable) / len(stable), 4),
    }


def apply_adaptation_feedback(pipeline, rows: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    applied = []
    for row in rows:
        case = next(item for item in QUERY_CASES if item["id"] == row["id"])
        for item in row["top"]:
            source = str(item.get("source") or "").lower()
            is_v2 = any(expected.lower() in source for expected in case["expected_sources_v2"])
            is_v1_stale = case["conflict"] and any(expected.lower() in source for expected in case["expected_sources_v1"])
            if is_v2:
                for _ in range(repeats):
                    pipeline.db.add_retrieval_feedback(
                        item["memory_id"],
                        "useful",
                        query=row["query"],
                        rating=1.0,
                        retrieval_score=item["score"],
                        metadata={"experiment": "agent_corpus", "phase": "prefer_v2"},
                    )
                applied.append({"memory_id": item["memory_id"], "label": "useful", "query_id": row["id"]})
            elif is_v1_stale:
                for _ in range(repeats):
                    pipeline.db.add_retrieval_feedback(
                        item["memory_id"],
                        "stale",
                        query=row["query"],
                        rating=-0.75,
                        retrieval_score=item["score"],
                        metadata={"experiment": "agent_corpus", "phase": "downrank_v1"},
                    )
                applied.append({"memory_id": item["memory_id"], "label": "stale", "query_id": row["id"]})
    return applied


def run(db_path: Path, max_words: int, overlap_words: int, top_k: int, feedback_repeats: int) -> dict[str, Any]:
    start = time.perf_counter()
    pipeline = create_pipeline(ROOT, db_path=db_path)
    try:
        v1_import = import_corpus(pipeline, corpus_files(V1_DIR), max_words, overlap_words)
        after_v1 = evaluate(pipeline, top_k=top_k, phase="after_v1")
        v2_import = import_corpus(pipeline, corpus_files(V2_DIR), max_words, overlap_words)
        manifest_relations = apply_manifest_relations(pipeline, load_manifest())
        after_v2 = evaluate(pipeline, top_k=top_k, phase="after_v2")
        feedback = apply_adaptation_feedback(pipeline, after_v2, repeats=feedback_repeats)
        after_feedback = evaluate(pipeline, top_k=top_k, phase="after_feedback")
        stats = pipeline_stats(pipeline)
    finally:
        pipeline.close()
    return {
        "ok": True,
        "elapsed_sec": round(time.perf_counter() - start, 6),
        "database": str(db_path),
        "imports": {"v1": v1_import, "v2": v2_import},
        "manifest_relations": manifest_relations,
        "summaries": {
            "after_v1": summarize(after_v1),
            "after_v2": summarize(after_v2),
            "after_feedback": summarize(after_feedback),
        },
        "feedback_applied": feedback,
        "cases": {
            "after_v1": after_v1,
            "after_v2": after_v2,
            "after_feedback": after_feedback,
        },
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a temporary DB on synthetic agent knowledge and test adaptation")
    parser.add_argument("--db-path", default=None, help="Optional DB path. Defaults to a temporary DB.")
    parser.add_argument("--max-words", type=int, default=90)
    parser.add_argument("--overlap-words", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--feedback-repeats", type=int, default=3)
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
        if not db_path.is_absolute():
            db_path = ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        payload = run(db_path, args.max_words, args.overlap_words, args.top_k, args.feedback_repeats)
    else:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_corpus.db"
            payload = run(db_path, args.max_words, args.overlap_words, args.top_k, args.feedback_repeats)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
