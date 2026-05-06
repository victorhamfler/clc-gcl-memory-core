from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.maintenance import domain_health_report, memory_review, weak_memories
from core.pipeline import MemoryPipeline
from core.runtime import create_pipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


def init_pipeline(root: Path, db_path: Path, use_config_embedding: bool) -> MemoryPipeline:
    if use_config_embedding:
        return create_pipeline(ROOT, db_path=db_path)
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def text_blob(answer: dict[str, Any]) -> str:
    chunks = [str(answer.get("answer") or "")]
    chunks.extend(str(item.get("text_preview") or "") for item in answer.get("evidence") or [])
    chunks.extend(str(item.get("text_preview") or "") for item in answer.get("stale") or [])
    return "\n".join(chunks).lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Namespaced agent workflow smoke.")
    parser.add_argument("--use-config-embedding", action="store_true", help="Use config.yaml embedding backend instead of hash.")
    args = parser.parse_args()
    config = load_config(ROOT)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "agent_namespace_workflow.db"
        pipeline = init_pipeline(root, db_path, args.use_config_embedding)
        try:
            namespace = "agent:manual_test_alpha"
            beta_namespace = "agent:manual_test_beta"
            global_rule = pipeline.teach(
                "Global agent operating rule: agents should preserve source labels, evidence ids, and namespace boundaries.",
                source="manual/global_rules.md",
                namespace="global",
                store_session=False,
            )
            alpha_1 = pipeline.teach(
                "Alpha agent profile: Alpha supports project planning, memory review, and careful GitHub upload policy.",
                source="manual/alpha_profile.md",
                agent_id="alpha_manual",
                namespace=namespace,
                store_session=False,
            )
            alpha_2 = pipeline.teach(
                "Alpha private task rule: Alpha may prepare GitHub commits but must not upload unless the user explicitly asks.",
                source="manual/alpha_policy.md",
                agent_id="alpha_manual",
                namespace=namespace,
                store_session=False,
            )
            beta = pipeline.teach(
                "Beta private label: Beta uses the codename Blue Quartz for isolated beta-only checks.",
                source="manual/beta_profile.md",
                agent_id="beta_manual",
                namespace=beta_namespace,
                store_session=False,
            )
            alpha_answer = pipeline.ask(
                "What GitHub upload policy should Alpha follow?",
                agent_id="alpha_manual",
                namespace=namespace,
                include_global=True,
                store_session=True,
            )
            beta_asks_alpha = pipeline.ask(
                "What GitHub upload policy should Alpha follow?",
                agent_id="beta_manual",
                namespace=beta_namespace,
                include_global=False,
                store_session=False,
            )
            correction = pipeline.correct(
                "Alpha GitHub upload policy: Alpha must never upload to GitHub automatically; upload only after explicit user instruction.",
                target_memory_ids=[alpha_2["memory"]["memory_id"]],
                target_query="Alpha GitHub upload policy",
                source="manual/alpha_policy_correction.md",
                agent_id="alpha_manual",
                namespace=namespace,
                store_session=False,
            )
            corrected_answer = pipeline.ask(
                "What GitHub upload policy should Alpha follow now?",
                agent_id="alpha_manual",
                namespace=namespace,
                include_global=True,
                store_session=False,
            )
            review = memory_review(pipeline.db, weak_limit=6)
            weak = weak_memories(pipeline.db, limit=6, include_resolved=True)
            health = domain_health_report(pipeline.db)
            alpha_domains = pipeline.db.list_domains(namespaces=[namespace])
            beta_domains = pipeline.db.list_domains(namespaces=[beta_namespace])
            stats = pipeline.db.stats()
        finally:
            pipeline.close()

    alpha_text = text_blob(alpha_answer)
    beta_alpha_text = text_blob(beta_asks_alpha)
    corrected_text = text_blob(corrected_answer)
    checks = {
        "embedding_backend_expected": (
            stats["embedding_signature"]["backend"] == "wsl_llama_cpp"
            if args.use_config_embedding
            else stats["embedding_signature"]["backend"] == "hash"
        ),
        "configured_embedding_dim_used_when_requested": (
            stats["vector_dimensions"] == [int((config.get("embedding") or {}).get("dim") or config.get("embedding_dim") or 768)]
            if args.use_config_embedding
            else stats["vector_dimensions"] == [128]
        ),
        "global_rule_stored_global": global_rule["namespace"] == "global",
        "alpha_memories_stored_alpha": alpha_1["namespace"] == namespace and alpha_2["namespace"] == namespace,
        "beta_memory_stored_beta": beta["namespace"] == beta_namespace,
        "alpha_answer_sees_alpha_policy": "github" in alpha_text and "explicitly asks" in alpha_text,
        "beta_does_not_see_alpha_policy": "github" not in beta_alpha_text and "explicitly asks" not in beta_alpha_text,
        "correction_links_old_policy": bool(correction["relations"] and correction["feedback"]),
        "corrected_answer_prefers_current_policy": "must never upload" in corrected_text and "automatic" in corrected_text,
        "corrected_answer_mentions_stale_context": bool(corrected_answer.get("stale")),
        "alpha_domains_are_alpha": bool(alpha_domains) and all(domain.namespace == namespace for domain in alpha_domains),
        "beta_domains_are_beta": bool(beta_domains) and all(domain.namespace == beta_namespace for domain in beta_domains),
        "domain_health_has_namespaces": all(domain.get("namespace") for domain in health["domains"]),
        "review_reports_domain_health": review.get("domain_health", {}).get("domain_count") == health["domain_count"],
        "resolved_weak_contains_old_policy": any(
            item["memory_id"] == alpha_2["memory"]["memory_id"] and item["resolved"] for item in weak
        ),
    }
    result = {
        "ok": all(checks.values()),
        "mode": "config_embedding" if args.use_config_embedding else "hash",
        "checks": checks,
        "answers": {
            "alpha": alpha_answer["answer"],
            "beta_asks_alpha": beta_asks_alpha["answer"],
            "corrected": corrected_answer["answer"],
        },
        "memory_ids": {
            "global": global_rule["memory"]["memory_id"],
            "alpha_profile": alpha_1["memory"]["memory_id"],
            "alpha_policy": alpha_2["memory"]["memory_id"],
            "beta_profile": beta["memory"]["memory_id"],
            "correction": correction["correction_memory"]["memory_id"],
        },
        "domain_health": health,
        "review_recommendations": review["recommendations"],
        "resolved_weak": [item for item in weak if item.get("resolved")],
        "stats": stats,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
