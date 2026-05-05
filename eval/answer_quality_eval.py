from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.models import DomainState, MemoryNode
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB, utc_now


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def make_memory(memory_id: str, text: str, embedding: list[float], domain_id: str) -> MemoryNode:
    now = utc_now()
    return MemoryNode(
        id=memory_id,
        text=text,
        embedding=embedding,
        domain_id=domain_id,
        memory_type="design_rule",
        importance=0.7,
        stability=0.0,
        confidence=0.8,
        csd_score=0.0,
        surprise=0.0,
        recall_score=1.0,
        curiosity=0.0,
        focus=0.5,
        clc_state="RECALL",
        created_at=now,
        updated_at=now,
    )


def add_seed_memory(
    pipeline: MemoryPipeline,
    memory_id: str,
    text: str,
    source: str,
    domain_id: str,
    embedding_query: str,
) -> None:
    memory = make_memory(memory_id, text, pipeline.encoder.embed(embedding_query), domain_id)
    pipeline.db.insert_memory(memory)
    pipeline.db.set_memory_source(memory.id, source, 0)


def score_terms(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower) / len(terms)


def score_case(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    text = str(answer.get("answer") or "")
    evidence_ids = [str(item.get("memory_id") or "") for item in answer.get("evidence") or []]
    stale_ids = [str(item.get("memory_id") or "") for item in answer.get("stale") or []]
    expected_evidence = [str(item) for item in case.get("expected_evidence", [])]
    expected_stale = [str(item) for item in case.get("expected_stale", [])]
    forbidden_terms = [str(item) for item in case.get("forbidden_terms", [])]

    term_score = score_terms(text, case.get("expected_terms", []))
    forbidden_score = 1.0 - score_terms(text, forbidden_terms) if forbidden_terms else 1.0
    evidence_score = 1.0 if all(memory_id in evidence_ids for memory_id in expected_evidence) else 0.0
    top_evidence_score = 1.0 if expected_evidence and evidence_ids[:1] == expected_evidence[:1] else evidence_score
    stale_score = 1.0 if all(memory_id in stale_ids for memory_id in expected_stale) else (1.0 if not expected_stale else 0.0)
    conflict_score = 1.0 if bool(answer.get("conflict")) == bool(case.get("expect_conflict", False)) else 0.0
    confidence_ok = 1.0 if float(answer.get("confidence") or 0.0) >= float(case.get("min_confidence", 0.0)) else 0.0
    context_blob = "\n".join(item.get("content") or "" for item in answer.get("session_context") or [])
    context_forbidden_score = 1.0 - score_terms(context_blob, case.get("forbidden_context_terms", [])) if case.get("forbidden_context_terms") else 1.0

    weighted = (
        0.25 * term_score
        + 0.20 * top_evidence_score
        + 0.15 * evidence_score
        + 0.12 * forbidden_score
        + 0.10 * stale_score
        + 0.08 * conflict_score
        + 0.05 * confidence_ok
        + 0.05 * context_forbidden_score
    )
    return {
        "id": case["id"],
        "query": case["query"],
        "score": round(weighted, 4),
        "term_score": round(term_score, 4),
        "forbidden_score": round(forbidden_score, 4),
        "evidence_score": round(evidence_score, 4),
        "top_evidence_score": round(top_evidence_score, 4),
        "stale_score": round(stale_score, 4),
        "conflict_score": round(conflict_score, 4),
        "confidence_ok": round(confidence_ok, 4),
        "context_forbidden_score": round(context_forbidden_score, 4),
        "answer": answer["answer"],
        "confidence": answer["confidence"],
        "conflict": answer["conflict"],
        "evidence_ids": evidence_ids,
        "stale_ids": stale_ids,
        "session_context": answer.get("session_context") or [],
    }


def main() -> None:
    cases: list[dict[str, Any]] = []
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "answer_quality_eval.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            domain = DomainState(
                id="dom_agent_memory",
                name="agent_memory",
                anchor_vector=pipeline.encoder.embed("agent memory policy identity project label"),
                memory_count=0,
            )
            pipeline.db.upsert_domain(domain)

            github_query = "Can the assistant push documentation updates to GitHub automatically?"
            add_seed_memory(
                pipeline,
                "mem_old_github_policy",
                "Old repository policy: the assistant may push small documentation updates automatically after local tests pass. These conflict seeds are not final truth.",
                str(root / "agent_memory_v1" / "conflicts_v1.md"),
                domain.id,
                github_query,
            )
            add_seed_memory(
                pipeline,
                "mem_current_github_policy",
                "Correction: the assistant must not push to GitHub automatically. GitHub uploads happen only when Mira explicitly asks.",
                str(root / "agent_memory_v2" / "corrections_v2.md"),
                domain.id,
                github_query,
            )
            pipeline.db.add_relation("mem_current_github_policy", "mem_old_github_policy", "corrects", 1.0)

            name_query = "What is the current agent name?"
            add_seed_memory(
                pipeline,
                "mem_old_agent_name",
                "Old identity memory: the agent name was NovaDesk. This is historical but no longer current.",
                str(root / "agent_memory_v1" / "agent_profile.md"),
                domain.id,
                name_query,
            )
            add_seed_memory(
                pipeline,
                "mem_current_agent_name",
                "Correction: the current agent name is LoomGuide, not NovaDesk.",
                str(root / "agent_memory_v2" / "updates_v2.md"),
                domain.id,
                name_query,
            )
            pipeline.db.add_relation("mem_current_agent_name", "mem_old_agent_name", "supersedes", 1.0)

            label = pipeline.teach(
                "Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment.",
                source="agent_training_v1/project_label.md",
                agent_id="agent_quality",
                store_session=True,
            )
            session_id = label["session_id"]
            pipeline.teach(
                "GitHub policy memory: the assistant must not push to GitHub automatically unless Mira explicitly asks.",
                source="agent_training_v1/github_policy.md",
                session_id=session_id,
                agent_id="agent_quality",
                store_session=True,
            )
            pipeline.ask("What is Cerulean Keystone?", top_k=2, session_id=session_id, agent_id="agent_quality", store_session=True)
            pipeline.ask(github_query, top_k=2, session_id=session_id, agent_id="agent_quality", store_session=True)

            cases = [
                {
                    "id": "current_policy",
                    "query": github_query,
                    "answer": pipeline.ask(github_query, top_k=3),
                    "expected_terms": ["must not push", "explicitly asks"],
                    "forbidden_terms": ["may push small documentation updates automatically"],
                    "expected_evidence": ["mem_current_github_policy"],
                    "expected_stale": ["mem_old_github_policy"],
                    "expect_conflict": True,
                    "min_confidence": 0.50,
                },
                {
                    "id": "current_agent_name",
                    "query": name_query,
                    "answer": pipeline.ask(name_query, top_k=3),
                    "expected_terms": ["LoomGuide"],
                    "forbidden_terms": ["the agent name was NovaDesk"],
                    "expected_evidence": ["mem_current_agent_name"],
                    "expected_stale": ["mem_old_agent_name"],
                    "expect_conflict": True,
                    "min_confidence": 0.50,
                },
                {
                    "id": "session_label_followup",
                    "query": "What should I remember about that label?",
                    "answer": pipeline.ask(
                        "What should I remember about that label?",
                        top_k=3,
                        session_id=session_id,
                        agent_id="agent_quality",
                        store_session=True,
                    ),
                    "expected_terms": ["Cerulean Keystone", "adaptive memory brain"],
                    "forbidden_terms": ["must not push to GitHub"],
                    "forbidden_context_terms": ["GitHub policy memory", "push to GitHub automatically"],
                    "expected_evidence": [label["memory"]["memory_id"]],
                    "expected_stale": [],
                    "expect_conflict": False,
                    "min_confidence": 0.45,
                },
            ]
            scored = [score_case(case, case["answer"]) for case in cases]
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    mean_score = sum(item["score"] for item in scored) / len(scored)
    result = {
        "ok": mean_score >= 0.85 and all(item["score"] >= 0.75 for item in scored),
        "mean_score": round(mean_score, 4),
        "cases": scored,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
