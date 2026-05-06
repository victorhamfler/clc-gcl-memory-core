from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.maintenance import domain_health_report, memory_review
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def by_name(domains: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((domain for domain in domains if domain["name"] == name), {})


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "gcl_domain_health_eval.db")
        try:
            gcl_results = [
                pipeline.ingest(
                    "G-CL health eval: domain anchors should update only for compatible memories.",
                    source="G-CL_SKILL.md",
                ),
                pipeline.ingest(
                    "G-CL health eval: domain anchors should track compatible drift, curvature, and stability.",
                    source="G-CL_SKILL.md",
                ),
                pipeline.ingest(
                    "G-CL health eval: effective dimension should reveal growing domain complexity.",
                    source="G-CL_SKILL.md",
                ),
                pipeline.ingest(
                    "G-CL health eval: stable domains can be consolidated when drift stays controlled.",
                    source="G-CL_SKILL.md",
                ),
            ]
            old = pipeline.ingest(
                "Old G-CL health rule: protected contradictions should still update the domain anchor.",
                source="G-CL_SKILL.md",
            )
            correction = pipeline.ingest(
                "Correction: G-CL protected contradictions must not update the domain anchor.",
                source="G-CL_SKILL.md",
            )
            csd = pipeline.ingest(
                "CSD health eval: sparse novelty diagnostics need more examples before a domain can be trusted.",
                source="CSD_SKILL.md",
            )
            health = domain_health_report(pipeline.db)
            review = memory_review(pipeline.db, weak_limit=4)
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    gcl_domain = by_name(health["domains"], "G-CL")
    csd_domain = by_name(health["domains"], "CSD")
    checks = {
        "health_report_ok": health["ok"] is True,
        "gcl_domain_present": bool(gcl_domain),
        "gcl_metrics_present": all(
            key in gcl_domain
            for key in (
                "effective_dimension",
                "drift_ema",
                "curvature_ema",
                "stability",
                "memory_count",
                "recommended_action",
            )
        ),
        "gcl_detects_protected_or_corrected_state": gcl_domain.get("recommended_action") == "protect_and_review",
        "gcl_counts_contradiction_or_protect": (
            gcl_domain.get("contradiction_count", 0) > 0 or gcl_domain.get("protected_count", 0) > 0
        ),
        "correction_blocked_anchor_update": correction["gcl_action"] == "no_anchor_update",
        "compatible_stream_updates_or_creates_domain": any(
            item["gcl_action"] in {"create_domain", "anchor_update"} for item in gcl_results
        ),
        "csd_sparse_action_available": csd_domain.get("recommended_action") in {"seed_or_merge", "monitor", "add_examples"},
        "health_recommendations_present": bool(health["recommendations"]),
        "memory_review_embeds_domain_health": review.get("domain_health", {}).get("domain_count") == health["domain_count"],
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "gcl_results": gcl_results,
        "old": old,
        "correction": correction,
        "csd": csd,
        "gcl_domain_health": gcl_domain,
        "csd_domain_health": csd_domain,
        "health": health,
        "review_recommendations": review["recommendations"],
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
