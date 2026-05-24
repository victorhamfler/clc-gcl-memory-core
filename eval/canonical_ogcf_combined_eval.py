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
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "canonical_ogcf_combined_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_ogcf_combined_eval_report.md"
DUPLICATE_ORIGIN_JSON = REPO_ROOT / "experiments" / "ogcf_duplicate_origin_and_dedup_effect_results.json"


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


def canonical_config(enabled: bool, *, lexical_backfill_enabled: bool = True) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "support_weight": 0.08,
        "duplicate_penalty": 0.18,
        "support_reference_count": 4,
        "lexical_backfill_enabled": lexical_backfill_enabled,
        "lexical_backfill_min_affinity": 0.75,
        "lexical_backfill_max_additions": 10,
    }


def exact_miss_rows(canonical_enabled: bool) -> list[dict[str, Any]]:
    query = "Hermes exact canonical backfill target."
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "canonical_ogcf_combined.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        pipeline = MemoryPipeline(
            root=root,
            db_path=db_path,
            embedding_config={"backend": "hash", "dim": 128},
            canonical_memory_config=canonical_config(canonical_enabled, lexical_backfill_enabled=True),
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
            far_embedding = pipeline.encoder.embed("canonical target far from query vector")
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
            rows = pipeline.retrieve(query, top_k=5)
        finally:
            pipeline.close()
    return rows


def bridge_meta() -> dict[str, Any]:
    return {
        "max_interaction_z": 2.81,
        "bridge_overload_score": 0.937,
        "loop_count": 10,
        "risk_regions": [
            {
                "clusters": "15-31-59",
                "interaction_z": 2.81,
                "interaction_excess": 2.81,
                "failure_mode": "bridge_overload",
                "recommended_action": "split_cluster",
                "cluster_sizes": "25-3-1",
            }
        ],
        "bridge_clusters": [{"cluster_id": 15, "size": 25, "unique_domains": 25}],
        "cluster_summary": [
            {"cluster_id": 15, "size": 25, "local_defect": 0.05, "top_domain": "dom_bridge"}
        ],
        "memory_cluster_map": {
            "mem_bridge_1": 15,
            "mem_bridge_2": 15,
            "mem_bridge_3": 15,
        },
    }


def clean_meta() -> dict[str, Any]:
    return {
        "max_interaction_z": 0.0,
        "bridge_overload_score": 0.0,
        "loop_count": 0,
        "risk_regions": [],
        "bridge_clusters": [],
        "cluster_summary": [],
        "memory_cluster_map": {},
    }


def base_row(
    memory_id: str,
    score: float,
    text: str,
    *,
    support_count: int = 1,
    is_keeper: bool = True,
    stale: bool = False,
    current: bool = False,
    contradiction: float = 0.0,
) -> dict[str, Any]:
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "score": score,
        "cosine": score,
        "text": text,
        "text_match_score": 0.9,
        "claim_scope_score": 0.9,
        "stored_contradiction_score": contradiction,
        "supersession_score": -0.45 if stale else (0.45 if current else 0.0),
        "relation_supersession_score": -0.45 if stale else (0.45 if current else 0.0),
        "source_reliability": 0.0,
        "domain_reliability": 0.0,
        "authority_state": "superseded" if stale else ("current" if current else "standalone"),
        "canonical_claim_key": f"claim::{text.lower()}",
        "canonical_keeper_memory_id": memory_id if is_keeper else "mem_keeper",
        "canonical_support_count": support_count,
        "canonical_duplicate_count": max(0, support_count - 1),
        "canonical_is_keeper": is_keeper,
        "canonical_support_bonus": 0.08 * min(1.0, support_count / 4.0) if is_keeper and support_count > 1 else 0.0,
        "canonical_duplicate_penalty": 0.0 if is_keeper else 0.18 * min(1.0, support_count / 4.0),
        "canonical_score_adjustment": (
            0.08 * min(1.0, support_count / 4.0)
            if is_keeper and support_count > 1
            else -0.18 * min(1.0, support_count / 4.0)
            if not is_keeper
            else 0.0
        ),
    }


def strip_canonical(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped = []
    for row in rows:
        stripped.append({key: value for key, value in row.items() if not key.startswith("canonical_")})
    return stripped


def run_selector_mode(
    rows: list[dict[str, Any]],
    *,
    canonical_enabled: bool,
    ogcf_enabled: bool,
    ogcf_meta: dict[str, Any],
) -> dict[str, Any]:
    mode_rows = copy.deepcopy(rows if canonical_enabled else strip_canonical(rows))
    features, diagnostics = selector_features_from_retrieval_context(
        mode_rows,
        condition_name="standard_budget144",
    )
    if ogcf_enabled:
        features, diagnostics = augment_selector_features(features, mode_rows, ogcf_meta, diagnostics)
    decision = CLCPolicySelector().select(features)
    return {
        "features": asdict(features),
        "diagnostics": diagnostics,
        "decision": asdict(decision),
        "top_memory_id": mode_rows[0].get("memory_id") or mode_rows[0].get("id") if mode_rows else None,
        "top_text": mode_rows[0].get("text") if mode_rows else "",
        "memory_ids": [row.get("memory_id") or row.get("id") for row in mode_rows],
    }


def run_four_modes(rows: list[dict[str, Any]], *, ogcf_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": run_selector_mode(rows, canonical_enabled=False, ogcf_enabled=False, ogcf_meta=ogcf_meta),
        "canonical": run_selector_mode(rows, canonical_enabled=True, ogcf_enabled=False, ogcf_meta=ogcf_meta),
        "ogcf": run_selector_mode(rows, canonical_enabled=False, ogcf_enabled=True, ogcf_meta=ogcf_meta),
        "combined": run_selector_mode(rows, canonical_enabled=True, ogcf_enabled=True, ogcf_meta=ogcf_meta),
    }


def exact_miss_case() -> dict[str, Any]:
    off_rows = exact_miss_rows(False)
    on_rows = exact_miss_rows(True)
    result = {
        "canonical_off": run_four_modes(off_rows, ogcf_meta=clean_meta()),
        "canonical_on": run_four_modes(on_rows, ogcf_meta=clean_meta()),
        "raw_retrieval": {
            "canonical_off_ids": [row["memory_id"] for row in off_rows],
            "canonical_on_ids": [row["memory_id"] for row in on_rows],
            "canonical_on_top": {
                key: on_rows[0].get(key)
                for key in (
                    "memory_id",
                    "score",
                    "cosine",
                    "text",
                    "canonical_support_count",
                    "canonical_is_keeper",
                    "canonical_score_adjustment",
                )
            }
            if on_rows
            else {},
        },
    }
    return result


def duplicate_clutter_case() -> dict[str, Any]:
    rows = [
        base_row("mem_keeper", 0.86, "Victor prefers the green terminal theme.", support_count=5, is_keeper=True),
        base_row("mem_dup_1", 0.84, "Victor prefers the green terminal theme.", support_count=5, is_keeper=False),
        base_row("mem_dup_2", 0.83, "Victor prefers the green terminal theme.", support_count=5, is_keeper=False),
        base_row("mem_dup_3", 0.82, "Victor prefers the green terminal theme.", support_count=5, is_keeper=False),
    ]
    return run_four_modes(rows, ogcf_meta=clean_meta())


def bridge_supported_case() -> dict[str, Any]:
    rows = [
        base_row("mem_bridge_1", 0.92, "Hermes uses selector outcome logs.", support_count=8, is_keeper=True),
        base_row("mem_bridge_2", 0.90, "Hermes uses selector outcome logs.", support_count=8, is_keeper=True),
        base_row("mem_bridge_3", 0.88, "Hermes uses selector outcome logs.", support_count=8, is_keeper=True),
    ]
    return run_four_modes(rows, ogcf_meta=bridge_meta())


def stale_conflict_case() -> dict[str, Any]:
    rows = [
        base_row("mem_old", 0.88, "Victor's current drink is coffee.", support_count=7, is_keeper=True, stale=True),
        base_row("mem_current", 0.86, "Victor's current drink is water.", support_count=7, is_keeper=True, current=True),
    ]
    return run_four_modes(rows, ogcf_meta=clean_meta())


def load_duplicate_origin_summary() -> dict[str, Any]:
    if not DUPLICATE_ORIGIN_JSON.exists():
        return {"available": False, "path": str(DUPLICATE_ORIGIN_JSON)}
    data = json.loads(DUPLICATE_ORIGIN_JSON.read_text(encoding="utf-8"))
    original = data.get("original_db_maintenance") or data.get("original") or {}
    exact_unique = data.get("exact_unique_db_maintenance") or data.get("exact_unique_shadow") or {}
    return {
        "available": True,
        "path": str(DUPLICATE_ORIGIN_JSON),
        "duplicate_origin": data.get("duplicate_origin", {}),
        "exact_unique_shadow_db": data.get("exact_unique_shadow_db", {}),
        "original": original,
        "exact_unique_shadow": exact_unique,
        "checks": data.get("checks", {}),
    }


def main() -> int:
    cases = {
        "exact_miss": exact_miss_case(),
        "duplicate_clutter": duplicate_clutter_case(),
        "bridge_supported": bridge_supported_case(),
        "stale_conflict": stale_conflict_case(),
    }
    duplicate_origin = load_duplicate_origin_summary()

    exact_ids_off = cases["exact_miss"]["raw_retrieval"]["canonical_off_ids"]
    exact_ids_on = cases["exact_miss"]["raw_retrieval"]["canonical_on_ids"]
    duplicate = cases["duplicate_clutter"]
    bridge = cases["bridge_supported"]
    stale = cases["stale_conflict"]

    checks = {
        "canonical_recovers_exact_miss_target": bool(exact_ids_on)
        and exact_ids_on[0].startswith("mem_target")
        and not any(memory_id.startswith("mem_target") for memory_id in exact_ids_off),
        "canonical_exact_miss_support_attached": cases["exact_miss"]["raw_retrieval"]["canonical_on_top"].get(
            "canonical_support_count"
        )
        == 3,
        "duplicate_clutter_exposed_by_canonical": duplicate["canonical"]["diagnostics"].get(
            "canonical_duplicate_pressure", 0.0
        )
        >= 0.7,
        "duplicate_clutter_pressure_absent_when_canonical_off": duplicate["base"]["diagnostics"].get(
            "canonical_duplicate_pressure", 1.0
        )
        == 0.0,
        "ogcf_adds_bridge_risk_after_canonical": bridge["combined"]["features"]["memory_bad_rate"]
        > bridge["canonical"]["features"]["memory_bad_rate"]
        and bridge["ogcf"]["features"]["memory_bad_rate"] > bridge["base"]["features"]["memory_bad_rate"],
        "combined_keeps_canonical_and_ogcf_signals": bridge["combined"]["diagnostics"].get(
            "canonical_confidence_signal", 0.0
        )
        > 0.0
        and bridge["combined"]["diagnostics"].get("ogcf_bridge_overload_score", 0.0) > 0.5,
        "canonical_does_not_overtrust_stale_conflict": stale["canonical"]["diagnostics"].get(
            "canonical_confidence_credit", 1.0
        )
        == 0.0
        and stale["canonical"]["diagnostics"].get("stale_current_conflict", 0.0) > 0.0,
    }
    if duplicate_origin.get("available"):
        original_summary = duplicate_origin.get("original", {})
        shadow_summary = duplicate_origin.get("exact_unique_shadow", {})
        original_total = int(
            original_summary.get("candidate_total", original_summary.get("candidate_count", 0)) or 0
        )
        shadow_total = int(
            shadow_summary.get("candidate_total", shadow_summary.get("candidate_count", 0)) or 0
        )
        checks["exact_unique_shadow_reduces_ogcf_maintenance_noise"] = shadow_total < original_total

    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "cases": cases,
        "duplicate_origin_summary": duplicate_origin,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    report = [
        "# Canonical + OGCF Combined Eval",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "## Checks",
        "",
    ]
    for name, ok in checks.items():
        report.append(f"- `{name}`: {ok}")
    report.extend(
        [
            "",
            "## Main Findings",
            "",
            "- Canonical retrieval recovers an exact textual claim missed by vector search and attaches support metadata.",
            "- Canonical duplicate metadata exposes clutter to the selector instead of deleting provenance.",
            "- OGCF bridge overload still increases risk after canonical support is present, so the methods are complementary.",
            "- Canonical support credit is withheld in stale/current conflict contexts.",
            "",
            "## Output",
            "",
            f"- JSON: `{OUT_JSON}`",
        ]
    )
    OUT_MD.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
