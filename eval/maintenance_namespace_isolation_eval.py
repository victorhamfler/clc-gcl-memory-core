from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.consolidation import consolidation_plan, create_consolidation_summaries
from core.maintenance import improvement_plan, memory_review, weak_memories
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def ids(rows: list[dict]) -> set[str]:
    return {str(row.get("memory_id")) for row in rows if row.get("memory_id")}


def group_ids(plan: dict) -> set[str]:
    return {
        str(memory_id)
        for group in plan.get("candidate_groups", [])
        for memory_id in group.get("memory_ids", [])
    }


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "maintenance_namespace_isolation.db")
        try:
            alpha_ids = []
            beta_ids = []
            global_ids = []
            for idx in range(4):
                alpha = pipeline.teach(
                    f"Alpha maintenance stable note {idx}: Alpha memory review should stay in the alpha namespace.",
                    source=f"maintenance_ns/alpha_{idx}.md",
                    agent_id="alpha",
                    namespace="agent:alpha",
                    store_session=False,
                )
                beta = pipeline.teach(
                    f"Beta maintenance stable note {idx}: Beta memory review should stay in the beta namespace.",
                    source=f"maintenance_ns/beta_{idx}.md",
                    agent_id="beta",
                    namespace="agent:beta",
                    store_session=False,
                )
                alpha_ids.append(alpha["memory"]["memory_id"])
                beta_ids.append(beta["memory"]["memory_id"])
            for idx in range(2):
                global_memory = pipeline.teach(
                    f"Global maintenance stable note {idx}: Shared guidance can be included only when requested.",
                    source=f"maintenance_ns/global_{idx}.md",
                    namespace="global",
                    store_session=False,
                )
                global_ids.append(global_memory["memory"]["memory_id"])

            beta_wrong = pipeline.teach(
                "Beta weak policy: Beta may ignore source labels during maintenance.",
                source="maintenance_ns/beta_wrong.md",
                agent_id="beta",
                namespace="agent:beta",
                store_session=False,
            )
            beta_correction = pipeline.correct(
                "Beta maintenance policy: Beta must preserve source labels during maintenance.",
                target_memory_ids=[beta_wrong["memory"]["memory_id"]],
                target_query="Beta maintenance source labels",
                source="maintenance_ns/beta_correction.md",
                agent_id="beta",
                namespace="agent:beta",
                store_session=False,
            )

            alpha_review = memory_review(pipeline.db, weak_limit=10, namespace="agent:alpha")
            beta_review = memory_review(pipeline.db, weak_limit=10, namespace="agent:beta")
            alpha_weak = weak_memories(pipeline.db, limit=20, include_resolved=True, namespace="agent:alpha")
            beta_weak = weak_memories(pipeline.db, limit=20, include_resolved=True, namespace="agent:beta")
            alpha_plan = consolidation_plan(pipeline.db, min_domain_memories=2, namespace="agent:alpha")
            beta_plan = consolidation_plan(pipeline.db, min_domain_memories=2, namespace="agent:beta")
            alpha_with_global_plan = consolidation_plan(
                pipeline.db,
                min_domain_memories=2,
                namespace="agent:alpha",
                include_global=True,
            )
            alpha_created = create_consolidation_summaries(
                pipeline,
                min_domain_memories=2,
                max_groups=1,
                namespace="agent:alpha",
            )
            alpha_improvement_plan = improvement_plan(pipeline.db, limit=10, namespace="agent:alpha")
            beta_improvement_plan = improvement_plan(pipeline.db, limit=10, namespace="agent:beta", include_global=False)
            summary_ids = [item["summary_memory_id"] for item in alpha_created["created_summaries"]]
            summarized_sources = pipeline.db.summarized_memories_for_sources(summary_ids, limit=20)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    alpha_plan_ids = group_ids(alpha_plan)
    beta_plan_ids = group_ids(beta_plan)
    alpha_with_global_ids = group_ids(alpha_with_global_plan)
    alpha_weak_ids = ids(alpha_weak)
    beta_weak_ids = ids(beta_weak)
    alpha_summary_source_ids = ids(summarized_sources)
    checks = {
        "alpha_review_domains_only_alpha": all(domain["namespace"] == "agent:alpha" for domain in alpha_review["domains"]),
        "beta_review_domains_only_beta": all(domain["namespace"] == "agent:beta" for domain in beta_review["domains"]),
        "alpha_review_does_not_show_beta_weak": not (set(beta_ids) & ids(alpha_review["weak_memories"])),
        "alpha_weak_excludes_beta": not (set(beta_ids) & alpha_weak_ids),
        "beta_weak_includes_beta_resolution": beta_wrong["memory"]["memory_id"] in beta_weak_ids,
        "alpha_consolidation_only_alpha": bool(alpha_plan_ids) and alpha_plan_ids <= set(alpha_ids),
        "beta_consolidation_only_beta": bool(beta_plan_ids) and beta_plan_ids <= set(beta_ids),
        "alpha_consolidation_excludes_beta": not (set(beta_ids) & alpha_plan_ids),
        "alpha_include_global_can_see_global": bool(set(global_ids) & alpha_with_global_ids),
        "alpha_created_summary_namespace_alpha": all(item["namespace"] == "agent:alpha" for item in alpha_created["created_summaries"]),
        "alpha_summary_sources_only_alpha": bool(alpha_summary_source_ids) and alpha_summary_source_ids <= set(alpha_ids),
        "alpha_improvement_plan_excludes_beta": not (set(beta_ids) & ids(alpha_improvement_plan["items"])),
        "beta_improvement_plan_excludes_alpha": not (set(alpha_ids) & ids(beta_improvement_plan["items"])),
        "beta_correction_created": bool(beta_correction["relations"] and beta_correction["feedback"]),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "alpha_ids": alpha_ids,
        "beta_ids": beta_ids,
        "global_ids": global_ids,
        "beta_wrong_id": beta_wrong["memory"]["memory_id"],
        "alpha_review": alpha_review,
        "beta_review": beta_review,
        "alpha_plan": alpha_plan,
        "beta_plan": beta_plan,
        "alpha_with_global_plan": alpha_with_global_plan,
        "alpha_created": alpha_created,
        "summarized_sources": summarized_sources,
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
