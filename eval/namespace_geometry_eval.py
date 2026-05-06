from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def compact_domain(domain) -> dict:
    return {
        "id": domain.id,
        "name": domain.name,
        "namespace": domain.namespace,
        "memory_count": domain.memory_count,
        "effective_dimension": round(domain.effective_dimension, 4),
        "drift_ema": round(domain.drift_ema, 6),
        "curvature_ema": round(domain.curvature_ema, 6),
    }


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "namespace_geometry_eval.db")
        try:
            global_gcl = pipeline.ingest(
                "G-CL namespace geometry eval: global anchor keeps shared geometry rules.",
                source="G-CL_SKILL.md",
                namespace="global",
            )
            alpha_gcl_1 = pipeline.ingest(
                "G-CL namespace geometry eval: alpha anchor stores alpha-only geometry preferences.",
                source="G-CL_SKILL.md",
                namespace="agent:alpha",
            )
            alpha_gcl_2 = pipeline.ingest(
                "G-CL namespace geometry eval: alpha anchor tracks compatible alpha drift and curvature.",
                source="G-CL_SKILL.md",
                namespace="agent:alpha",
            )
            beta_gcl = pipeline.ingest(
                "G-CL namespace geometry eval: beta anchor stores beta-only geometry preferences.",
                source="G-CL_SKILL.md",
                namespace="agent:beta",
            )
            global_domain = pipeline.db.get_domain(global_gcl["domain_id"])
            alpha_domain = pipeline.db.get_domain(alpha_gcl_1["domain_id"])
            beta_domain = pipeline.db.get_domain(beta_gcl["domain_id"])
            alpha_domains = pipeline.db.list_domains(namespaces=["agent:alpha"])
            beta_domains = pipeline.db.list_domains(namespaces=["agent:beta"])
            global_domains = pipeline.db.list_domains(namespaces=["global"])
            all_domains = pipeline.db.list_domains()
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    domain_ids = {
        "global": global_gcl["domain_id"],
        "alpha_first": alpha_gcl_1["domain_id"],
        "alpha_second": alpha_gcl_2["domain_id"],
        "beta": beta_gcl["domain_id"],
    }
    checks = {
        "global_domain_is_global": global_domain is not None and global_domain.namespace == "global",
        "alpha_domain_is_alpha": alpha_domain is not None and alpha_domain.namespace == "agent:alpha",
        "beta_domain_is_beta": beta_domain is not None and beta_domain.namespace == "agent:beta",
        "same_symbolic_domain_has_distinct_namespace_rows": len({domain_ids["global"], domain_ids["alpha_first"], domain_ids["beta"]}) == 3,
        "alpha_second_reuses_alpha_anchor": domain_ids["alpha_second"] == domain_ids["alpha_first"],
        "alpha_does_not_update_global_anchor_count": global_domain is not None and global_domain.memory_count == 1,
        "filtered_alpha_domains_only_alpha": all(domain.namespace == "agent:alpha" for domain in alpha_domains),
        "filtered_beta_domains_only_beta": all(domain.namespace == "agent:beta" for domain in beta_domains),
        "filtered_global_domains_only_global": all(domain.namespace == "global" for domain in global_domains),
        "all_three_namespaces_have_gcl_domains": {"global", "agent:alpha", "agent:beta"} <= {
            domain.namespace for domain in all_domains if domain.name == "G-CL"
        },
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "domain_ids": domain_ids,
        "ingest": {
            "global": global_gcl,
            "alpha_first": alpha_gcl_1,
            "alpha_second": alpha_gcl_2,
            "beta": beta_gcl,
        },
        "domains": [compact_domain(domain) for domain in all_domains],
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
