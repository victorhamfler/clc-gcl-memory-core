from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.ogcf_geometry import OGCFGeometryEngine  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_erg_curvature_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_erg_curvature_regression_report.md"


def planted_operator(dim: int = 16) -> tuple[np.ndarray, np.ndarray, np.ndarray, set[int]]:
    rng = np.random.default_rng(20260604)
    q, _ = np.linalg.qr(rng.normal(size=(dim, dim)))
    spectrum = np.linspace(4.0, 0.35, dim)
    operator = q @ np.diag(spectrum) @ q.T
    operator = 0.5 * (operator + operator.T)

    constraint_a = np.zeros((dim, dim), dtype=float)
    constraint_b = np.zeros((dim, dim), dtype=float)
    core = {0, 1, 2, 3}
    halo = {4, 5, 6, 7}
    for idx in core:
        constraint_a[idx, idx] = 1.0
    for idx in halo:
        constraint_a[idx, idx] = 0.35
    for idx in core:
        j = 4 + idx
        constraint_b[idx, j] = 1.0
        constraint_b[j, idx] = 1.0
    constraint_b[1, 2] = 0.45
    constraint_b[2, 1] = 0.45
    return operator, constraint_a, constraint_b, core


def clustered_embeddings() -> np.ndarray:
    rng = np.random.default_rng(20260604)
    centers = np.array(
        [
            [3.0, 0.0, 0.0, 0.5, 0.0, 0.0],
            [0.0, 3.0, 0.0, 0.0, 0.5, 0.0],
            [0.0, 0.0, 3.0, 0.0, 0.0, 0.5],
            [1.5, 1.5, 0.2, 0.4, 0.4, 0.0],
        ],
        dtype=float,
    )
    rows = []
    for center in centers:
        for _ in range(10):
            rows.append(center + rng.normal(scale=0.07, size=center.shape))
    return np.asarray(rows, dtype=np.float32)


def projector_graph_separation(engine: OGCFGeometryEngine) -> dict[str, Any]:
    rng = np.random.default_rng(90210)
    dim = 12
    rank = 4
    centers = []
    for seed in (1, 2, 3):
        local_rng = np.random.default_rng(seed)
        q, _ = np.linalg.qr(local_rng.normal(size=(dim, rank)))
        centers.append(q)
    projectors = []
    cosine_centroids = []
    labels = []
    for label, basis in enumerate(centers):
        for _ in range(4):
            noise = rng.normal(scale=0.08, size=basis.shape)
            q, _ = np.linalg.qr(basis + noise)
            projectors.append(engine._projector(q[:, :rank]))
            cosine_centroids.append(np.mean(q[:, :rank], axis=1))
            labels.append(label)
    within_projector = []
    across_projector = []
    within_cosine = []
    across_cosine = []
    for i in range(len(projectors)):
        for j in range(i + 1, len(projectors)):
            projector_distance = engine.projector_distance(projectors[i], projectors[j])
            denom = max(float(np.linalg.norm(cosine_centroids[i]) * np.linalg.norm(cosine_centroids[j])), 1e-12)
            cosine_distance = 1.0 - float(np.dot(cosine_centroids[i], cosine_centroids[j]) / denom)
            if labels[i] == labels[j]:
                within_projector.append(projector_distance)
                within_cosine.append(cosine_distance)
            else:
                across_projector.append(projector_distance)
                across_cosine.append(cosine_distance)
    projector_margin = float(np.mean(across_projector) - np.mean(within_projector))
    cosine_margin = float(np.mean(across_cosine) - np.mean(within_cosine))
    return {
        "within_projector_mean": round(float(np.mean(within_projector)), 6),
        "across_projector_mean": round(float(np.mean(across_projector)), 6),
        "projector_margin": round(projector_margin, 6),
        "within_cosine_mean": round(float(np.mean(within_cosine)), 6),
        "across_cosine_mean": round(float(np.mean(across_cosine)), 6),
        "cosine_margin": round(cosine_margin, 6),
        "projector_beats_cosine_margin": projector_margin > cosine_margin,
    }


def write_report(result: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF ERG Curvature Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in result["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Curvature", "", "```json", json.dumps(result["curvature"], indent=2), "```"])
    lines.extend(["", "## Projector Graph", "", "```json", json.dumps(result["projector_graph"], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    engine = OGCFGeometryEngine(rank_k=5, seed=20260604)
    operator, constraint_a, constraint_b, planted_core = planted_operator()
    curvature = engine.projector_curvature(
        operator,
        constraint_a,
        constraint_b,
        delta=0.08,
        alpha=0.8,
        rank_k=5,
    )
    sectors = curvature["sectors"]
    graph = projector_graph_separation(engine)
    analyzed = OGCFGeometryEngine(n_clusters=4, rank_k=3, neighbors=12, random_baselines=2, seed=11).analyze(
        clustered_embeddings()
    )
    top_activity = set(sectors["top_activity_indices"][:4])
    c4 = float(sectors.get("C4", 0.0))
    c8 = float(sectors.get("C8", 0.0))
    c12 = float(sectors.get("C12", 0.0))
    checks = {
        "projector_is_symmetric": float(curvature["symmetry_error"]) < 1e-8,
        "projector_is_idempotent": float(curvature["idempotence_error"]) < 1e-8,
        "spectral_gap_positive": float(curvature["spectral_gap"]) > 1e-6,
        "omega_nonzero": float(curvature["omega_norm"]) > 1e-6,
        "activity_localizes_planted_core": len(top_activity & planted_core) >= 2,
        "core_halo_enrichment_present": bool(sectors["core_halo_present"]),
        "core_halo_profile_descends": c4 > c8 > c12 > 1.0,
        "projector_graph_separates_domains": graph["across_projector_mean"] > graph["within_projector_mean"],
        "projector_graph_beats_cosine_margin": bool(graph["projector_beats_cosine_margin"]),
        "analyze_exports_projector_distance_summary": float(
            analyzed.projector_distance_summary.get("edge_count", 0.0)
        )
        > 0.0
        and float(analyzed.projector_distance_summary.get("mean_distance", 0.0)) > 0.0,
        "analyze_exports_projector_graph_edges": len(analyzed.projector_graph_edges) > 0
        and "projector_distance" in analyzed.projector_graph_edges[0],
    }
    result = {
        "schema": "ogcf_erg_curvature_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "curvature": {
            "omega_norm": round(float(curvature["omega_norm"]), 12),
            "spectral_gap": round(float(curvature["spectral_gap"]), 12),
            "idempotence_error": round(float(curvature["idempotence_error"]), 12),
            "symmetry_error": round(float(curvature["symmetry_error"]), 12),
            "top_activity_indices": sectors["top_activity_indices"],
            "C4": c4,
            "C6": float(sectors.get("C6", 0.0)),
            "C8": c8,
            "C12": c12,
            "core_halo_slope": sectors["core_halo_slope"],
            "core_halo_present": sectors["core_halo_present"],
        },
        "projector_graph": graph,
        "analyze_projector_distance_summary": analyzed.projector_distance_summary,
        "analyze_projector_graph_edge_sample": analyzed.projector_graph_edges[:5],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    write_report(result)
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
