from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.maintenance import memory_review, record_memory_improvement, weak_memories
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def project(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "memory_id",
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
        )
    }


def score(checks: dict[str, bool]) -> dict[str, Any]:
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    return {
        "ok": passed == total,
        "passed": passed,
        "total": total,
        "score": round(passed / max(1, total), 4),
        "checks": checks,
    }


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "mechanism_component_eval.db")
        try:
            base = pipeline.ingest(
                "Agent memory component eval: store durable project decisions with evidence ids and source labels.",
                source="agent_memory/base.md",
            )
            near = pipeline.ingest(
                "Agent memory component eval: store durable project decisions with evidence ids, source labels, and confidence.",
                source="agent_memory/near.md",
            )
            old_policy = pipeline.ingest(
                "Old policy memory: the assistant may push repository updates automatically after tests pass.",
                source="agent_memory/old_policy.md",
            )
            direct_correction = pipeline.ingest(
                "Correction: the assistant must not push repository updates automatically after tests pass.",
                source="agent_memory/direct_correction.md",
            )
            old_preference = pipeline.ingest(
                "User profile memory: the user wants long detailed explanations by default.",
                source="agent_memory/old_preference.md",
            )
            subtle_correction = pipeline.ingest(
                "Current preference: the user wants short direct explanations unless they ask for detail.",
                source="agent_memory/subtle_preference.md",
            )
            additive = pipeline.ingest(
                "Updated policy: Memory API should also expose consolidation source inspection endpoints.",
                source="agent_memory/additive.md",
            )
            gcl_base = pipeline.ingest(
                "G-CL component eval: anchor drift should track orthogonal drift, curvature, and effective dimension.",
                source="G-CL_SKILL.md",
            )
            gcl_compatible = pipeline.ingest(
                "G-CL component eval: anchor drift should track orthogonal drift, curvature, effective dimension, and stability.",
                source="G-CL_SKILL.md",
            )
            csd_base = pipeline.ingest(
                "CSD component eval: novelty density should normalize raw semantic drift before surprise is high.",
                source="CSD_SKILL.md",
            )
            weak_items = weak_memories(pipeline.db, limit=5)
            target_for_improvement = weak_items[0]["memory_id"] if weak_items else base["memory_id"]
            maintenance_update = record_memory_improvement(
                pipeline,
                target_for_improvement,
                "Clarify the memory with source-aware maintenance context and keep the original evidence intact.",
                agent_id="mechanism_eval_agent",
            )
            review = memory_review(pipeline.db, weak_limit=5)
            domains = [
                {
                    "name": domain.name,
                    "memory_count": domain.memory_count,
                    "effective_dimension": round(domain.effective_dimension, 4),
                    "drift_ema": round(domain.drift_ema, 6),
                    "curvature_ema": round(domain.curvature_ema, 6),
                    "stability": round(domain.stability, 6),
                }
                for domain in pipeline.db.list_domains()
            ]
            stats = pipeline.db.stats()
            relations = pipeline.db.relation_counts()
        finally:
            pipeline.close()

    cases = {
        "base": project(base),
        "near": project(near),
        "old_policy": project(old_policy),
        "direct_correction": project(direct_correction),
        "old_preference": project(old_preference),
        "subtle_correction": project(subtle_correction),
        "additive": project(additive),
        "gcl_base": project(gcl_base),
        "gcl_compatible": project(gcl_compatible),
        "csd_base": project(csd_base),
        "maintenance_update": project(maintenance_update["improvement_memory"]),
    }
    clc_checks = {
        "new_memory_splits_domain": base["clc_state"] == "SPLIT_DOMAIN",
        "near_memory_uses_known_context": near["clc_state"] in {"RECALL", "FOCUS", "LIGHT_UPDATE"} and near["recall"] > 0.65,
        "direct_contradiction_protects": direct_correction["clc_state"] == "PROTECT",
        "subtle_contradiction_protects": subtle_correction["clc_state"] == "PROTECT",
        "additive_update_not_protected": additive["clc_state"] != "PROTECT",
        "maintenance_update_is_non_protective": maintenance_update["improvement_memory"]["clc_state"] != "PROTECT",
    }
    csd_checks = {
        "direct_contradiction_high": direct_correction["contradiction"] > 0.75,
        "subtle_contradiction_high": subtle_correction["contradiction"] > 0.75,
        "additive_contradiction_low": additive["contradiction"] < 0.25,
        "near_memory_less_novel_than_base": near["csd_score"] < base["csd_score"],
        "csd_symbolic_domain_detected": csd_base["domain_name"] == "CSD",
        "maintenance_review_finds_weak_or_ok": bool(review["recommendations"]),
    }
    gcl_checks = {
        "base_creates_domain": base["gcl_action"] == "create_domain",
        "compatible_memory_updates_anchor": near["gcl_action"] == "anchor_update" and near["anchor_update_strength"] > 0.0,
        "direct_protect_blocks_anchor": direct_correction["gcl_action"] == "no_anchor_update" and direct_correction["anchor_update_strength"] == 0.0,
        "subtle_protect_blocks_anchor": subtle_correction["gcl_action"] == "no_anchor_update" and subtle_correction["anchor_update_strength"] == 0.0,
        "gcl_symbolic_domain_detected": gcl_base["domain_name"] == "G-CL",
        "effective_dimension_grows": max((domain["effective_dimension"] for domain in domains), default=1.0) > 1.0,
        "drift_or_curvature_tracked": max((domain["drift_ema"] + domain["curvature_ema"] for domain in domains), default=0.0) > 0.0,
        "maintenance_update_relation_created": any(row["relation_type"] == "updates" for row in relations),
    }
    component_scores = {
        "CLC": score(clc_checks),
        "CSD": score(csd_checks),
        "G-CL": score(gcl_checks),
    }
    result = {
        "ok": all(component["ok"] for component in component_scores.values()),
        "component_scores": component_scores,
        "cases": cases,
        "domains": domains,
        "maintenance": {
            "target_memory_id": target_for_improvement,
            "review_recommendations": review["recommendations"],
            "relations": relations,
        },
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
