from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.models import DomainState, MemoryNode  # noqa: E402
from core.runtime import init_db, resolve_embedding_cache_path, runtime_embedding_config  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import utc_now  # noqa: E402


DEFAULT_DB = REPO_ROOT / "experiments" / "rich_gemma_canonical_ogcf_fixture.db"
DEFAULT_RAW_DB = REPO_ROOT / "experiments" / "rich_gemma_raw_canonical_ogcf_fixture.db"
DEFAULT_QUERIES = REPO_ROOT / "experiments" / "rich_gemma_canonical_ogcf_queries.json"
NAMESPACE = "agent:rich-gemma-canonical-ogcf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a richer Gemma-backed DB for canonical + OGCF shadow tests.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--queries-json", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument(
        "--raw-embeddings",
        action="store_true",
        help="Store unnormalized Gemma embeddings for OGCF geometry tests.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def pipeline(db_path: Path, *, raw_embeddings: bool) -> MemoryPipeline:
    config = load_config(ROOT)
    embedding_config = resolve_embedding_cache_path(ROOT, runtime_embedding_config(config))
    if raw_embeddings and embedding_config:
        embedding_config = dict(embedding_config)
        embedding_config["normalize"] = False
    init_db(ROOT, db_path)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_dim=int(config.get("embedding_dim") or 768),
        top_k=int(config.get("top_k") or 8),
        embedding_config=embedding_config,
        retrieval_weights=config.get("retrieval_weights"),
        symbolic_config=config.get("symbolic"),
        claim_scope_config=config.get("claim_scope"),
        answer_type_config=config.get("answer_type"),
        retrieval_signal_config=config.get("retrieval_signals"),
        evidence_state_config=config.get("evidence_states"),
        canonical_memory_config={"enabled": True, "support_reference_count": 6},
        clc_thresholds=config.get("thresholds"),
    )


def make_domain(pipe: MemoryPipeline, domain_id: str, name: str) -> None:
    anchor = pipe.encoder.embed(name)
    pipe.db.upsert_domain(DomainState(id=domain_id, name=name, anchor_vector=anchor, namespace=NAMESPACE))


def add_memory(
    pipe: MemoryPipeline,
    memory_id: str,
    text: str,
    *,
    domain_id: str,
    memory_type: str = "semantic_note",
    importance: float = 0.72,
    confidence: float = 0.78,
    source: str = "rich_gemma_fixture.md",
    chunk_index: int = 0,
) -> str:
    embedding = pipe.encoder.embed(text)
    pipe._ensure_embedding_signature(embedding)
    now = utc_now()
    pipe.db.insert_memory(
        MemoryNode(
            id=memory_id,
            text=text,
            embedding=embedding,
            domain_id=domain_id,
            memory_type=memory_type,
            importance=importance,
            stability=0.12,
            confidence=confidence,
            csd_score=0.0,
            surprise=0.0,
            recall_score=1.0,
            curiosity=0.0,
            focus=0.55,
            clc_state="RECALL",
            created_at=now,
            updated_at=now,
            namespace=NAMESPACE,
        )
    )
    pipe.db.set_memory_source(memory_id, source, chunk_index, metadata={"fixture": "rich_gemma_canonical_ogcf"})
    return memory_id


def seed_fixture(pipe: MemoryPipeline) -> dict[str, Any]:
    domains = {
        "dom_selector": "selector controller architecture",
        "dom_weather": "weather radar methods",
        "dom_drink": "victor drink preferences",
        "dom_project": "hermes project memory",
        "dom_robot": "robot procedure memory",
        "dom_calendar": "calendar scheduling memory",
        "dom_location": "location profile memory",
        "dom_ogcf": "OGCF geometry memory",
        "dom_bridge_a": "bridge router finance",
        "dom_bridge_b": "bridge router weather",
        "dom_bridge_c": "bridge router project",
        "dom_bridge_d": "bridge router robotics",
        "dom_bridge_e": "bridge router personal profile",
        "dom_bridge_f": "bridge router maintenance",
    }
    for domain_id, name in domains.items():
        make_domain(pipe, domain_id, name)

    refs: dict[str, Any] = {}
    idx = 0

    # Clean repeated support: canonical should confidently protect these.
    selector_claim = "Cedar Map uses selector outcome logs for adaptive memory routing."
    refs["selector_support"] = []
    for i in range(8):
        refs["selector_support"].append(
            add_memory(
                pipe,
                f"mem_selector_support_{i:02d}",
                selector_claim,
                domain_id="dom_selector",
                memory_type="design_rule",
                importance=0.82,
                confidence=0.84,
                chunk_index=idx,
            )
        )
        idx += 1

    weather_claim = "Use AccuWeather radar for Victor's local weather checks."
    refs["weather_support"] = []
    for i in range(6):
        refs["weather_support"].append(
            add_memory(
                pipe,
                f"mem_weather_support_{i:02d}",
                weather_claim,
                domain_id="dom_weather",
                memory_type="procedure",
                importance=0.78,
                confidence=0.82,
                chunk_index=idx,
            )
        )
        idx += 1

    # Duplicate pressure: many exact repeats should expose canonical duplicate pressure.
    duplicate_claim = "Victor backup beverage note says coffee and green tea are old preferences."
    refs["duplicate_pressure"] = []
    for i in range(10):
        refs["duplicate_pressure"].append(
            add_memory(
                pipe,
                f"mem_duplicate_pressure_{i:02d}",
                duplicate_claim,
                domain_id="dom_drink",
                memory_type="preference",
                importance=0.65 if i else 0.88,
                confidence=0.68 if i else 0.86,
                chunk_index=idx,
            )
        )
        idx += 1

    # Stale/current corrections.
    old_drink = add_memory(
        pipe,
        "mem_drink_old_espresso",
        "Victor currently prefers espresso in the morning and green tea in the afternoon.",
        domain_id="dom_drink",
        memory_type="preference",
        importance=0.7,
        confidence=0.72,
        chunk_index=idx,
    )
    idx += 1
    current_drink = add_memory(
        pipe,
        "mem_drink_current_water",
        "Correction: Victor currently prefers sparkling water and decaf, not espresso or green tea.",
        domain_id="dom_drink",
        memory_type="preference",
        importance=0.9,
        confidence=0.92,
        chunk_index=idx,
    )
    idx += 1
    pipe.db.add_relation(current_drink, old_drink, "corrects", 1.0)
    refs["drink_correction"] = {"old": old_drink, "current": current_drink}

    old_project = add_memory(
        pipe,
        "mem_project_old_name",
        "The old project codename was North Lantern before the memory selector work changed direction.",
        domain_id="dom_project",
        memory_type="semantic_note",
        chunk_index=idx,
    )
    idx += 1
    current_project = add_memory(
        pipe,
        "mem_project_current_name",
        "The current project codename is Cedar Map for the adaptive memory selector work.",
        domain_id="dom_project",
        memory_type="semantic_note",
        importance=0.86,
        confidence=0.88,
        chunk_index=idx,
    )
    idx += 1
    pipe.db.add_relation(current_project, old_project, "updates", 1.0)
    refs["project_update"] = {"old": old_project, "current": current_project}

    # Bridge memories: semantically similar bridge-router phrasing across many domains.
    bridge_templates = [
        ("dom_bridge_a", "Finance bridge router note: Aurelia bridge links budget risk, memory confidence, and selector refresh policy."),
        ("dom_bridge_b", "Weather bridge router note: Aurelia bridge links radar source choice, forecast uncertainty, and selector refresh policy."),
        ("dom_bridge_c", "Project bridge router note: Aurelia bridge links codename evidence, outcome logs, and selector refresh policy."),
        ("dom_bridge_d", "Robotics bridge router note: Aurelia bridge links actuator status, procedure drift, and selector refresh policy."),
        ("dom_bridge_e", "Profile bridge router note: Aurelia bridge links user preference changes, stale claims, and selector refresh policy."),
        ("dom_bridge_f", "Maintenance bridge router note: Aurelia bridge links duplicate cleanup, OGCF geometry, and selector refresh policy."),
    ]
    refs["bridge"] = []
    for round_idx in range(4):
        for domain_id, text in bridge_templates:
            refs["bridge"].append(
                add_memory(
                    pipe,
                    f"mem_bridge_{round_idx}_{domain_id}",
                    f"{text} Shared bridge token set: aurelia nexus routing diagnostic.",
                    domain_id=domain_id,
                    memory_type="semantic_note",
                    importance=0.74,
                    confidence=0.76,
                    chunk_index=idx,
                )
            )
            idx += 1

    # Diverse non-bridge context so geometry has real alternatives.
    diverse = [
        ("dom_robot", "Robot arm procedure: calibrate joint zero before running the warehouse pick routine.", "procedure"),
        ("dom_robot", "Robot safety memory: stop the actuator test if torque oscillation exceeds the allowed margin.", "procedure"),
        ("dom_calendar", "Calendar memory: the weekly review belongs on Friday afternoon unless Victor moves it.", "semantic_note"),
        ("dom_location", "Location profile memory: Victor usually asks for local weather around his current city.", "semantic_note"),
        ("dom_ogcf", "OGCF geometry checks cluster loops, bridge overload, and local defect pressure in memory embeddings.", "design_rule"),
        ("dom_ogcf", "Unnormalized embedding geometry is useful as an OGCF ablation for bridge interpretation.", "design_rule"),
        ("dom_selector", "Selector policy chooses protect, verified refresh, or XSEQ refresh from retrieval-derived features.", "design_rule"),
        ("dom_weather", "Weather model note: Meteoblue is useful for high-resolution forecast models, not radar-first checks.", "semantic_note"),
        ("dom_drink", "Victor avoids using stale drink notes when a correction explicitly supersedes the old preference.", "preference"),
        ("dom_project", "Hermes agent reports should include policy distributions and failure cases for selector development.", "procedure"),
    ]
    refs["diverse"] = []
    for i, (domain_id, text, memory_type) in enumerate(diverse):
        refs["diverse"].append(
            add_memory(
                pipe,
                f"mem_diverse_{i:02d}",
                text,
                domain_id=domain_id,
                memory_type=memory_type,
                chunk_index=idx,
            )
        )
        idx += 1

    return refs


def write_queries(path: Path) -> None:
    queries = [
        {"case_id": "clean_selector_support", "query": "How does Cedar Map handle memory routing?"},
        {"case_id": "clean_weather_support", "query": "What radar method should Victor use for weather checks?"},
        {"case_id": "drink_current", "query": "What does Victor currently prefer to drink?"},
        {"case_id": "drink_old", "query": "What did Victor used to drink?"},
        {"case_id": "duplicate_pressure", "query": "What does the backup beverage note say?"},
        {"case_id": "project_current", "query": "What is the current project codename?"},
        {"case_id": "project_old", "query": "What was the old project codename?"},
        {"case_id": "bridge_weather", "query": "How does Aurelia bridge connect weather uncertainty to selector refresh policy?"},
        {"case_id": "bridge_profile", "query": "How does Aurelia bridge connect user preference changes to selector refresh policy?"},
        {"case_id": "bridge_ogcf", "query": "How does OGCF geometry detect bridge overload in memory embeddings?"},
        {"case_id": "robot_procedure", "query": "What should the robot do before the warehouse pick routine?"},
        {"case_id": "calendar", "query": "When is the weekly review usually scheduled?"},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"queries": queries}, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    db_path = (DEFAULT_RAW_DB if args.raw_embeddings and args.db_path == DEFAULT_DB else args.db_path).resolve()
    if db_path.exists():
        if not args.overwrite:
            raise FileExistsError(f"{db_path} exists; pass --overwrite to rebuild")
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    pipe = pipeline(db_path, raw_embeddings=bool(args.raw_embeddings))
    try:
        refs = seed_fixture(pipe)
        stats = pipe.db.stats()
    finally:
        pipe.close()
    write_queries(args.queries_json.resolve())
    out = {
        "ok": True,
        "db_path": str(db_path),
        "queries_json": str(args.queries_json.resolve()),
        "namespace": NAMESPACE,
        "raw_embeddings": bool(args.raw_embeddings),
        "stats": stats,
        "refs": refs,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
