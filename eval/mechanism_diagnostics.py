from __future__ import annotations

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


def project(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "domain_name",
        "memory_type",
        "clc_state",
        "decision_reason",
        "csd_score",
        "csd_density",
        "contradiction",
        "surprise",
        "recall",
        "curiosity",
        "focus",
        "gcl_action",
        "combined_drift",
        "orthogonal_drift",
        "curvature",
        "anchor_update_strength",
    ]
    return {key: item.get(key) for key in keys}


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "mechanism_diagnostics.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            base = pipeline.ingest(
                "The memory system should store agent project decisions with evidence ids and stable retrieval context.",
                source="agent_memory/base.md",
            )
            similar = pipeline.ingest(
                "The memory system should remember agent project decisions with evidence ids, stable retrieval context, and test outcomes.",
                source="agent_memory/similar.md",
            )
            old_policy = pipeline.ingest(
                "Old repository policy: the assistant may push documentation updates to GitHub automatically after tests pass.",
                source="agent_memory/old_policy.md",
            )
            correction = pipeline.ingest(
                "Correction: the assistant must not push documentation updates to GitHub automatically after tests pass.",
                source="agent_memory/correction.md",
            )
            gcl = pipeline.ingest(
                "G-CL anchor drift memory geometry should track orthogonal drift, curvature, and effective dimension for stable continual learning.",
                source="G-CL_SKILL.md",
            )
            csd = pipeline.ingest(
                "CSD contradiction novelty density diagnostics should normalize raw drift against constraint geometry before calling a result surprising.",
                source="CSD_SKILL.md",
            )
            stats = pipeline.db.stats()
            domains = [
                {
                    "id": domain.id,
                    "name": domain.name,
                    "memory_count": domain.memory_count,
                    "effective_dimension": round(domain.effective_dimension, 4),
                    "drift_ema": round(domain.drift_ema, 6),
                    "curvature_ema": round(domain.curvature_ema, 6),
                    "stability": round(domain.stability, 6),
                }
                for domain in pipeline.db.list_domains()
            ]
        finally:
            pipeline.close()

    checks = {
        "first_memory_creates_domain": base["gcl_action"] == "create_domain" and base["clc_state"] == "SPLIT_DOMAIN",
        "similar_memory_recalls_domain": similar["recall"] > 0.70 and similar["csd_score"] < base["csd_score"],
        "similar_memory_updates_anchor": similar["gcl_action"] == "anchor_update" and similar["anchor_update_strength"] > 0.0,
        "correction_detects_contradiction": correction["contradiction"] > 0.75 and correction["clc_state"] == "PROTECT",
        "protect_blocks_anchor_update": correction["gcl_action"] == "no_anchor_update" and correction["anchor_update_strength"] == 0.0,
        "symbolic_domains_split": {domain["name"] for domain in domains} >= {"agent_memory", "G-CL", "CSD"},
        "effective_dimension_tracked": all(domain["effective_dimension"] >= 1.0 for domain in domains),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "cases": {
            "base": project(base),
            "similar": project(similar),
            "old_policy": project(old_policy),
            "correction": project(correction),
            "gcl": project(gcl),
            "csd": project(csd),
        },
        "stats": stats,
        "domains": domains,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
