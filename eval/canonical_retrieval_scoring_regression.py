from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.models import DomainState, MemoryNode  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB, utc_now  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "canonical_retrieval_scoring_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_retrieval_scoring_regression_report.md"


def make_memory(
    memory_id: str,
    text: str,
    embedding: list[float],
    domain_id: str,
    *,
    importance: float,
    confidence: float,
    created_at: str,
) -> MemoryNode:
    return MemoryNode(
        id=memory_id,
        text=text,
        embedding=embedding,
        domain_id=domain_id,
        memory_type="semantic_note",
        importance=importance,
        stability=0.0,
        confidence=confidence,
        csd_score=0.0,
        surprise=0.0,
        recall_score=1.0,
        curiosity=0.0,
        focus=0.5,
        clc_state="RECALL",
        created_at=created_at,
        updated_at=created_at,
    )


def main() -> int:
    query = "canonical support counts for hermes memory"
    duplicate_text = "Hermes memory uses canonical support counts."
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "canonical_retrieval.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(
            root=root,
            db_path=db_path,
            embedding_config={"backend": "hash", "dim": 128},
            canonical_memory_config={
                "enabled": True,
                "support_weight": 0.08,
                "duplicate_penalty": 0.18,
                "support_reference_count": 4,
            },
        )
        try:
            embedding = pipeline.encoder.embed(duplicate_text)
            domain = DomainState(id="dom_project", name="ProjectMemory", anchor_vector=embedding, memory_count=5)
            pipeline.db.upsert_domain(domain)
            rows = [
                ("mem_dup_old_a", 0.4, 0.5, "2026-05-24T10:00:00+00:00"),
                ("mem_dup_old_b", 0.5, 0.5, "2026-05-24T10:01:00+00:00"),
                ("mem_dup_old_c", 0.5, 0.6, "2026-05-24T10:02:00+00:00"),
                ("mem_dup_keeper", 0.9, 0.9, "2026-05-24T10:03:00+00:00"),
            ]
            for memory_id, importance, confidence, created_at in rows:
                pipeline.db.insert_memory(
                    make_memory(
                        memory_id,
                        duplicate_text,
                        embedding,
                        domain.id,
                        importance=importance,
                        confidence=confidence,
                        created_at=created_at,
                    )
                )
            related = make_memory(
                "mem_related",
                "Hermes memory keeps support metadata for repeated facts.",
                pipeline.encoder.embed("Hermes memory keeps support metadata for repeated facts."),
                domain.id,
                importance=0.6,
                confidence=0.7,
                created_at="2026-05-24T10:04:00+00:00",
            )
            pipeline.db.insert_memory(related)
            retrieved = pipeline.retrieve(query, top_k=5)
        finally:
            pipeline.close()

    by_id = {row["memory_id"]: row for row in retrieved}
    duplicate_rows = [row for row in retrieved if row["memory_id"].startswith("mem_dup")]
    keeper = by_id.get("mem_dup_keeper", {})
    duplicate_nonkeepers = [row for row in duplicate_rows if row["memory_id"] != "mem_dup_keeper"]
    checks = {
        "keeper_retrieved": bool(keeper),
        "keeper_has_support_count": int(keeper.get("canonical_support_count") or 0) == 4,
        "keeper_has_positive_adjustment": float(keeper.get("canonical_score_adjustment") or 0.0) > 0.0,
        "nonkeepers_penalized": bool(duplicate_nonkeepers)
        and all(float(row.get("canonical_score_adjustment") or 0.0) < 0.0 for row in duplicate_nonkeepers),
        "keeper_ranks_above_duplicate_rows": bool(keeper)
        and all(float(keeper["score"]) > float(row["score"]) for row in duplicate_nonkeepers),
        "support_metadata_present": bool(keeper)
        and keeper.get("canonical_keeper_memory_id") == "mem_dup_keeper"
        and int(keeper.get("canonical_duplicate_count") or 0) == 3,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "retrieved": [
            {
                "memory_id": row["memory_id"],
                "score": row["score"],
                "canonical_support_count": row.get("canonical_support_count"),
                "canonical_keeper_memory_id": row.get("canonical_keeper_memory_id"),
                "canonical_is_keeper": row.get("canonical_is_keeper"),
                "canonical_support_bonus": row.get("canonical_support_bonus"),
                "canonical_duplicate_penalty": row.get("canonical_duplicate_penalty"),
                "canonical_score_adjustment": row.get("canonical_score_adjustment"),
                "text": row["text"],
            }
            for row in retrieved
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical Retrieval Scoring Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "```json\n"
        + json.dumps(result, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
