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
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "canonical_lexical_backfill_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_lexical_backfill_regression_report.md"


def make_memory(memory_id: str, text: str, embedding: list[float], domain_id: str, created_at: str) -> MemoryNode:
    return MemoryNode(
        id=memory_id,
        text=text,
        embedding=embedding,
        domain_id=domain_id,
        memory_type="semantic_note",
        importance=0.5,
        stability=0.0,
        confidence=0.7,
        csd_score=0.0,
        surprise=0.0,
        recall_score=1.0,
        curiosity=0.0,
        focus=0.5,
        clc_state="RECALL",
        created_at=created_at,
        updated_at=created_at,
    )


def run_case(enabled: bool) -> list[dict]:
    query = "Hermes exact canonical backfill target."
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "canonical_backfill.db"
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
                "lexical_backfill_enabled": enabled,
                "lexical_backfill_min_affinity": 0.75,
                "lexical_backfill_max_additions": 10,
            },
        )
        try:
            query_embedding = pipeline.encoder.embed(query)
            distractor_domain = DomainState(id="dom_distractors", name="Distractors", anchor_vector=query_embedding)
            target_domain = DomainState(id="dom_target", name="Target", anchor_vector=query_embedding)
            pipeline.db.upsert_domain(distractor_domain)
            pipeline.db.upsert_domain(target_domain)
            for index in range(65):
                pipeline.db.insert_memory(
                    make_memory(
                        f"mem_distractor_{index:02d}",
                        f"Vector-near unrelated distractor {index}.",
                        query_embedding,
                        distractor_domain.id,
                        f"2026-05-24T11:{index % 60:02d}:00+00:00",
                    )
                )
            far_embedding = pipeline.encoder.embed("totally different lexical island")
            for index in range(3):
                pipeline.db.insert_memory(
                    make_memory(
                        f"mem_target_{index}",
                        query,
                        far_embedding,
                        target_domain.id,
                        f"2026-05-24T12:0{index}:00+00:00",
                    )
                )
            pipeline.db.insert_memory(
                make_memory(
                    "mem_other_namespace",
                    query,
                    far_embedding,
                    target_domain.id,
                    "2026-05-24T12:10:00+00:00",
                )
            )
            pipeline.db.conn.execute(
                "UPDATE memories SET namespace='other_ns' WHERE id='mem_other_namespace'"
            )
            pipeline.db.conn.commit()
            rows = pipeline.retrieve(query, top_k=5)
        finally:
            pipeline.close()
    return rows


def main() -> int:
    without_backfill = run_case(False)
    with_backfill = run_case(True)
    without_ids = [row["memory_id"] for row in without_backfill]
    with_ids = [row["memory_id"] for row in with_backfill]
    target_rows = [row for row in with_backfill if row["memory_id"].startswith("mem_target")]
    target = target_rows[0] if target_rows else {}
    checks = {
        "target_missing_without_backfill": not any(memory_id.startswith("mem_target") for memory_id in without_ids),
        "target_recovered_with_backfill": bool(target_rows),
        "target_ranks_first_with_backfill": bool(with_ids) and with_ids[0].startswith("mem_target"),
        "canonical_support_attached": int(target.get("canonical_support_count") or 0) == 3,
        "canonical_adjustment_positive": float(target.get("canonical_score_adjustment") or 0.0) > 0.0,
        "cross_namespace_support_excluded": target.get("canonical_keeper_memory_id") != "mem_other_namespace",
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "without_backfill": [
            {"memory_id": row["memory_id"], "score": row["score"], "text": row["text"]}
            for row in without_backfill
        ],
        "with_backfill": [
            {
                "memory_id": row["memory_id"],
                "score": row["score"],
                "cosine": row["cosine"],
                "canonical_support_count": row.get("canonical_support_count"),
                "canonical_keeper_memory_id": row.get("canonical_keeper_memory_id"),
                "canonical_is_keeper": row.get("canonical_is_keeper"),
                "canonical_score_adjustment": row.get("canonical_score_adjustment"),
                "text": row["text"],
            }
            for row in with_backfill
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Canonical Lexical Backfill Regression\n\n"
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
