from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


DOCS = [
    (
        "agent_memory",
        "Agent memory retrieval should use topic filtered session context for vague follow up questions. "
        "Agent memory should promote session turns into durable memory only when selected.",
    ),
    (
        "CSD",
        "CSD contradiction diagnostics should protect anchors when direct negating corrections appear. "
        "CSD diagnostics should normalize raw semantic drift before calling novelty high. "
        "CSD surprise combines novelty, density, contradiction, and domain shift.",
    ),
    (
        "G-CL",
        "G-CL anchor drift should update domain anchors only for compatible learning. "
        "G-CL geometry should track orthogonal drift, curvature, and effective dimension.",
    ),
    (
        "OpenClaw",
        "OpenClaw geometry controller should keep LCM as the source of truth. "
        "OpenClaw geometry controller should use a read heavy companion geometry database.",
    ),
]


CASES = [
    {
        "id": "agent_memory_followups",
        "query": "How should agent memory retrieval handle vague follow up questions?",
        "expected": ["topic filtered session context", "follow up questions"],
        "forbidden": ["promote session turns"],
    },
    {
        "id": "csd_novelty",
        "query": "How should CSD decide whether novelty is high?",
        "expected": ["normalize raw semantic drift", "novelty high"],
        "forbidden": ["protect anchors", "domain shift"],
    },
    {
        "id": "gcl_geometry",
        "query": "What should G-CL geometry track for domain stability?",
        "expected": ["orthogonal drift", "curvature", "effective dimension"],
        "forbidden": ["compatible learning"],
    },
    {
        "id": "openclaw_source",
        "query": "What should the OpenClaw geometry controller use as the source of truth?",
        "expected": ["LCM", "source of truth"],
        "forbidden": ["read heavy companion"],
    },
]


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def score_terms(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower) / len(terms)


def run(top_k: int) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "answer_specificity.db")
        try:
            for idx, (domain, text) in enumerate(DOCS):
                result = pipeline.ingest(text, source=f"answer_specificity/{domain}/doc_{idx:02d}.md")
                pipeline.db.set_memory_source(result["memory_id"], f"answer_specificity/{domain}/doc_{idx:02d}.md", 0)
            rows = []
            for case in CASES:
                answer = pipeline.ask(case["query"], top_k=top_k)
                text = answer["answer"]
                rows.append(
                    {
                        "id": case["id"],
                        "query": case["query"],
                        "answer": text,
                        "expected_score": round(score_terms(text, case["expected"]), 4),
                        "forbidden_score": round(score_terms(text, case["forbidden"]), 4),
                        "evidence": answer["evidence"],
                    }
                )
            stats = pipeline.db.stats()
        finally:
            pipeline.close()
    summary = {
        "mean_expected_score": round(sum(row["expected_score"] for row in rows) / len(rows), 4),
        "mean_forbidden_score": round(sum(row["forbidden_score"] for row in rows) / len(rows), 4),
        "exact_answer_count": sum(1 for row in rows if row["expected_score"] == 1.0 and row["forbidden_score"] == 0.0),
    }
    return {
        "ok": summary["mean_expected_score"] >= 0.95 and summary["mean_forbidden_score"] == 0.0,
        "summary": summary,
        "cases": rows,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate extractive answer specificity against adjacent evidence")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    payload = run(args.top_k)
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
