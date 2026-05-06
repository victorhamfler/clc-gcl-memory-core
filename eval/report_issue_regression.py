from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline


def main() -> None:
    with TemporaryDirectory() as tmp:
        pipeline = MemoryPipeline(
            ROOT,
            Path(tmp) / "report_issue_regression.db",
            embedding_dim=128,
            embedding_config={"backend": "hash", "dim": 128},
        )
        pipeline.db.init_schema(ROOT / "storage" / "schema.sql")
        try:
            payload = run_checks(pipeline)
        finally:
            pipeline.close()
    print(json.dumps(payload, indent=2))


def run_checks(pipeline: MemoryPipeline) -> dict:
    namespace = "agent:hermes"
    checks: dict[str, bool] = {}

    ingested = pipeline.ingest(
        "Ingest test: Mercury is the smallest planet.",
        source="report_ingest",
        namespace=namespace,
    )
    row = pipeline.db.conn.execute(
        "SELECT id, namespace FROM memories WHERE id=?",
        (ingested["memory_id"],),
    ).fetchone()
    source = pipeline.db.get_memory_source(ingested["memory_id"])
    checks["ingest_persists_memory"] = bool(row and row["namespace"] == namespace)
    checks["ingest_records_source"] = bool(source and source["source"] == "report_ingest")

    batch = pipeline.ingest_batch(
        [
            "Batch fact 1: Neptune has the strongest winds in the solar system.",
            "Batch fact 2: Venus is the hottest planet in the solar system.",
        ],
        source="report_batch",
        namespace=namespace,
    )
    checks["ingest_batch_stores_memories"] = batch["stored"] == 2
    checks["ingest_batch_has_memories_alias"] = len(batch.get("memories") or []) == 2

    for text in (
        "G-CL maintains domain geometry, anchor vectors, drift, curvature, and stability for memory domains.",
        "G-CL geometry tracks angular drift and orthogonal movement between new memories and domain anchors.",
        "G-CL anchors should update carefully and avoid changing during protected contradictions.",
        "G-CL API results should expose effective dimension, curvature ema, drift ema, and anchor update strength.",
    ):
        pipeline.teach(text, source="report_gcl", agent_id="hermes", namespace=namespace, store_session=False)
    gcl_answer = pipeline.ask("What does G-CL maintain?", namespace=namespace, include_global=False, top_k=5)
    checks["gcl_ask_returns_evidence"] = len(gcl_answer["evidence"]) > 0
    checks["ask_evidence_includes_namespace"] = all(item.get("namespace") == namespace for item in gcl_answer["evidence"])

    target = pipeline.teach(
        "G-CL mistakenly says Barcelona is the capital of Spain.",
        source="report_target",
        agent_id="hermes",
        namespace=namespace,
        store_session=False,
    )["memory"]
    correction = pipeline.correct(
        "Madrid is the capital of Spain.",
        target_memory_ids=[target["memory_id"]],
        source="report_correction",
        agent_id="hermes",
        namespace=namespace,
        store_session=False,
    )["correction_memory"]
    checks["correction_uses_semantic_domain"] = correction["domain_name"] == "general"
    checks["correction_not_ignored_by_default"] = correction["clc_state"] != "IGNORE"

    conflict_namespace = "agent:conflict"
    pipeline.teach(
        "Barcelona is the capital of Spain.",
        source="report_spain_a",
        agent_id="hermes",
        namespace=conflict_namespace,
        store_session=False,
    )
    pipeline.teach(
        "Madrid is the capital of Spain.",
        source="report_spain_b",
        agent_id="hermes",
        namespace=conflict_namespace,
        store_session=False,
    )
    conflict_answer = pipeline.ask(
        "What is the capital of Spain?",
        namespace=conflict_namespace,
        include_global=False,
        top_k=5,
    )
    checks["query_time_conflict_detected"] = conflict_answer["conflict"] is True
    checks["live_conflict_details_returned"] = bool(conflict_answer.get("live_conflicts"))

    forced = pipeline.teach(
        "This memory should be protected by operator priority override.",
        agent_id="hermes",
        namespace=namespace,
        store_session=False,
        force_clc_state="PROTECT",
    )["memory"]
    high = pipeline.teach(
        "High priority memories should not disappear behind IGNORE gating.",
        agent_id="hermes",
        namespace=namespace,
        store_session=False,
        priority="high",
    )["memory"]
    checks["force_clc_state_supported"] = forced["clc_state"] == "PROTECT"
    checks["priority_high_not_ignored"] = high["clc_state"] != "IGNORE"

    ok = all(checks.values())
    if not ok:
        raise AssertionError({key: value for key, value in checks.items() if not value})
    return {
        "ok": ok,
        "checks": checks,
        "gcl_answer": {
            "confidence": gcl_answer["confidence"],
            "evidence_count": len(gcl_answer["evidence"]),
            "evidence_namespaces": [item.get("namespace") for item in gcl_answer["evidence"]],
        },
        "correction": {
            "target_domain": target["domain_name"],
            "correction_domain": correction["domain_name"],
            "correction_clc": correction["clc_state"],
        },
        "conflict": {
            "conflict": conflict_answer["conflict"],
            "live_conflicts": conflict_answer.get("live_conflicts"),
        },
        "priority": {
            "forced_state": forced["clc_state"],
            "high_priority_state": high["clc_state"],
        },
    }


if __name__ == "__main__":
    main()
