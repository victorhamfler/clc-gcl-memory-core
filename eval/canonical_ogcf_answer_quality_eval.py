from __future__ import annotations

import copy
import json
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicySelector  # noqa: E402
from core.models import DomainState, MemoryNode  # noqa: E402
from core.ogcf_selector import augment_selector_features  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.runtime import init_db  # noqa: E402
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_answer_quality_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_answer_quality_eval_report.md"


NAMESPACE = "agent:canonical-ogcf-answer-quality"


def canonical_config(enabled: bool) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "support_weight": 0.08,
        "duplicate_penalty": 0.18,
        "support_reference_count": 4,
        "lexical_backfill_enabled": enabled,
        "lexical_backfill_min_affinity": 0.75,
        "lexical_backfill_max_additions": 10,
    }


def make_pipeline(root: Path, *, canonical_enabled: bool) -> MemoryPipeline:
    db_path = root / ("answer_quality_canonical_on.db" if canonical_enabled else "answer_quality_canonical_off.db")
    init_db(ROOT, db_path)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        canonical_memory_config=canonical_config(canonical_enabled),
    )


def make_memory(
    memory_id: str,
    text: str,
    embedding: list[float],
    domain_id: str,
    *,
    created_at: str,
) -> MemoryNode:
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
        namespace=NAMESPACE,
    )


def seed_exact_miss_answer_case(pipeline: MemoryPipeline) -> None:
    query = "Hermes launch window is Thursday 10 AM."
    query_embedding = pipeline.encoder.embed(query)
    far_embedding = pipeline.encoder.embed("unrelated vector island for exact claim")
    distractor_domain = DomainState(
        id="dom_answer_distractors",
        name="Answer quality distractors",
        anchor_vector=query_embedding,
        namespace=NAMESPACE,
    )
    target_domain = DomainState(
        id="dom_answer_targets",
        name="Answer quality targets",
        anchor_vector=query_embedding,
        namespace=NAMESPACE,
    )
    pipeline.db.upsert_domain(distractor_domain)
    pipeline.db.upsert_domain(target_domain)
    for index in range(65):
        memory_id = f"mem_aq_distractor_{index:02d}"
        pipeline.db.insert_memory(
            make_memory(
                memory_id,
                f"Hermes launch window distractor note {index}.",
                query_embedding,
                distractor_domain.id,
                created_at=f"2026-05-24T10:{index % 60:02d}:00+00:00",
            )
        )
        pipeline.db.set_memory_source(memory_id, "answer_quality/distractors.md", index, metadata={"case": "exact_miss"})
    for index in range(3):
        memory_id = f"mem_aq_launch_target_{index}"
        pipeline.db.insert_memory(
            make_memory(
                memory_id,
                query,
                far_embedding,
                target_domain.id,
                created_at=f"2026-05-24T11:0{index}:00+00:00",
            )
        )
        pipeline.db.set_memory_source(memory_id, "answer_quality/launch_window.md", index, metadata={"case": "exact_miss"})


def seed_stale_current_case(pipeline: MemoryPipeline) -> dict[str, str]:
    agent_id = "answer-quality-agent"
    session_id = "answer-quality-session"
    old = pipeline.teach(
        "Victor currently prefers espresso.",
        source="answer_quality/drink_v1.md",
        namespace=NAMESPACE,
        session_id=session_id,
        agent_id=agent_id,
        domain="food_drink",
        memory_type="preference",
        store_session=True,
    )["memory"]["memory_id"]
    current = pipeline.correct(
        "Victor currently prefers sparkling water, not espresso.",
        target_memory_ids=[old],
        source="answer_quality/drink_v2.md",
        namespace=NAMESPACE,
        session_id=session_id,
        agent_id=agent_id,
        domain="food_drink",
        memory_type="preference",
        store_session=True,
        relation_type="corrects",
    )["correction_memory"]["memory_id"]
    return {"old_drink": old, "current_drink": current}


def seed_bridge_case(pipeline: MemoryPipeline) -> dict[str, str]:
    ids: dict[str, str] = {}
    for index in range(3):
        taught = pipeline.teach(
            "Hermes uses selector outcome logs for adaptive memory routing.",
            source=f"answer_quality/bridge_{index}.md",
            namespace=NAMESPACE,
            agent_id="answer-quality-agent",
            domain="selector_bridge",
            memory_type="semantic_note",
            store_session=False,
        )
        ids[f"bridge_{index}"] = taught["memory"]["memory_id"]
    return ids


def bridge_meta(memory_ids: list[str]) -> dict[str, Any]:
    return {
        "max_interaction_z": 2.81,
        "bridge_overload_score": 0.937,
        "loop_count": 10,
        "risk_regions": [
            {
                "clusters": "15-31-59",
                "interaction_z": 2.81,
                "failure_mode": "bridge_overload",
                "recommended_action": "split_cluster",
            }
        ],
        "bridge_clusters": [{"cluster_id": 15, "size": 25, "unique_domains": 25}],
        "cluster_summary": [{"cluster_id": 15, "size": 25, "local_defect": 0.05, "top_domain": "dom_bridge"}],
        "memory_cluster_map": {memory_id: 15 for memory_id in memory_ids},
    }


def answer_contains(answer: str, terms: list[str]) -> bool:
    lowered = answer.lower()
    return all(term.lower() in lowered for term in terms)


def summarize_ask(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": answer.get("answer"),
        "confidence": answer.get("confidence"),
        "conflict": answer.get("conflict"),
        "evidence": [
            {
                "memory_id": row.get("memory_id"),
                "authority_state": row.get("authority_state"),
                "score": row.get("score"),
                "canonical_support_count": row.get("canonical_support_count"),
                "canonical_is_keeper": row.get("canonical_is_keeper"),
                "text": row.get("text"),
            }
            for row in answer.get("evidence", [])
        ],
        "raw_results": [
            {
                "memory_id": row.get("memory_id"),
                "authority_state": row.get("authority_state"),
                "score": row.get("score"),
                "cosine": row.get("cosine"),
                "text_match_score": row.get("text_match_score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "canonical_support_count": row.get("canonical_support_count"),
                "canonical_is_keeper": row.get("canonical_is_keeper"),
                "canonical_score_adjustment": row.get("canonical_score_adjustment"),
                "text": row.get("text"),
            }
            for row in answer.get("raw_results", [])[:8]
        ],
        "stale_context": [
            {
                "memory_id": row.get("memory_id"),
                "authority_state": row.get("authority_state"),
                "score": row.get("score"),
                "text": row.get("text"),
            }
            for row in answer.get("stale_context", [])
        ],
    }


def selector_summary(rows: list[dict[str, Any]], *, ogcf_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    features, diagnostics = selector_features_from_retrieval_context(rows, condition_name="standard_budget144")
    base_features = copy.deepcopy(features)
    if ogcf_meta:
        features, diagnostics = augment_selector_features(features, rows, ogcf_meta, diagnostics)
    decision = CLCPolicySelector().select(features)
    return {
        "base_features": asdict(base_features),
        "features": asdict(features),
        "diagnostics": diagnostics,
        "decision": asdict(decision),
    }


def run_pipeline_case(canonical_enabled: bool) -> dict[str, Any]:
    with TemporaryDirectory(prefix="canonical_ogcf_answer_quality_") as raw_tmp:
        pipeline = make_pipeline(Path(raw_tmp), canonical_enabled=canonical_enabled)
        try:
            seed_exact_miss_answer_case(pipeline)
            refs = seed_stale_current_case(pipeline)
            bridge_refs = seed_bridge_case(pipeline)

            launch = pipeline.ask(
                "Hermes launch window is Thursday 10 AM.",
                top_k=5,
                namespace=NAMESPACE,
                include_global=False,
            )
            drink = pipeline.ask(
                "What drink does Victor currently prefer?",
                top_k=5,
                namespace=NAMESPACE,
                include_global=False,
            )
            bridge = pipeline.ask(
                "How does Hermes use selector outcome logs?",
                top_k=5,
                namespace=NAMESPACE,
                include_global=False,
            )
            bridge_rows = bridge.get("raw_results", [])[:5]
            bridge_ids = [value for value in bridge_refs.values()]
            return {
                "canonical_enabled": canonical_enabled,
                "refs": {**refs, **bridge_refs},
                "launch": summarize_ask(launch),
                "drink": summarize_ask(drink),
                "bridge": summarize_ask(bridge),
                "selector": {
                    "launch": selector_summary(launch.get("raw_results", [])[:5]),
                    "drink": selector_summary(drink.get("raw_results", [])[:5]),
                    "bridge_base": selector_summary(bridge_rows),
                    "bridge_ogcf": selector_summary(bridge_rows, ogcf_meta=bridge_meta(bridge_ids)),
                },
            }
        finally:
            pipeline.close()


def main() -> int:
    canonical_off = run_pipeline_case(False)
    canonical_on = run_pipeline_case(True)

    launch_off_ids = [row["memory_id"] for row in canonical_off["launch"]["raw_results"]]
    launch_on_ids = [row["memory_id"] for row in canonical_on["launch"]["raw_results"]]
    launch_on_top = canonical_on["launch"]["raw_results"][0] if canonical_on["launch"]["raw_results"] else {}
    drink_on_evidence_ids = [row["memory_id"] for row in canonical_on["drink"]["evidence"]]
    drink_current_id = canonical_on["refs"]["current_drink"]
    bridge_base = canonical_on["selector"]["bridge_base"]
    bridge_ogcf = canonical_on["selector"]["bridge_ogcf"]

    checks = {
        "canonical_improves_exact_miss_answer": answer_contains(canonical_on["launch"]["answer"] or "", ["Thursday", "10 AM"])
        and not any(memory_id.startswith("mem_aq_launch_target") for memory_id in launch_off_ids)
        and bool(launch_on_ids)
        and launch_on_ids[0].startswith("mem_aq_launch_target"),
        "canonical_support_visible_in_answer_evidence": int(launch_on_top.get("canonical_support_count") or 0) == 3
        and bool(launch_on_top.get("canonical_is_keeper", False)),
        "current_claim_answer_uses_authoritative_memory": answer_contains(
            canonical_on["drink"]["answer"] or "", ["sparkling water"]
        )
        and drink_current_id in drink_on_evidence_ids,
        "stale_context_preserved_for_current_claim": any(
            row.get("memory_id") == canonical_on["refs"]["old_drink"]
            for row in canonical_on["drink"].get("stale_context", [])
        ),
        "ogcf_adds_bridge_warning_signal": bridge_ogcf["features"]["memory_bad_rate"]
        > bridge_base["features"]["memory_bad_rate"]
        and bridge_ogcf["diagnostics"].get("ogcf_bridge_overload_score", 0.0) > 0.5
        and bridge_ogcf["diagnostics"].get("ogcf_affected_memory_ratio", 0.0) > 0.0,
    }

    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "canonical_off": canonical_off,
        "canonical_on": canonical_on,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# Canonical + OGCF Answer Quality Eval",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "## Checks",
        "",
    ]
    for key, value in checks.items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Canonical retrieval is evaluated at the answer level, not only as a ranking feature.",
            "- The stale/current case checks that current evidence is used while stale context remains available.",
            "- OGCF is evaluated as a warning/control signal over answer retrieval context, not as a text generator.",
            "",
            "## Output",
            "",
            f"- JSON: `{OUT_JSON}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
