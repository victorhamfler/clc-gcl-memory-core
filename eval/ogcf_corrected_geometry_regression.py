from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.ogcf_geometry import OGCFGeometryEngine  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_corrected_geometry_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_corrected_geometry_regression_report.md"


def orthonormal_basis(seed: int, dim: int = 6, rank: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.normal(size=(dim, rank)))
    return q[:, :rank]


def synthetic_embeddings() -> np.ndarray:
    rng = np.random.default_rng(20260602)
    centers = np.array(
        [
            [3.0, 0.0, 0.0, 0.8, 0.0, 0.2],
            [0.0, 3.0, 0.0, 0.2, 0.8, 0.0],
            [0.0, 0.0, 3.0, 0.0, 0.2, 0.8],
            [1.4, 1.4, 1.4, 0.5, 0.5, 0.5],
        ],
        dtype=float,
    )
    rows = []
    for center in centers:
        for _ in range(8):
            rows.append(center + rng.normal(scale=0.08, size=center.shape))
    return np.asarray(rows, dtype=np.float32)


def main() -> int:
    engine = OGCFGeometryEngine(n_clusters=4, rank_k=3, neighbors=20, random_baselines=3, seed=7)
    b_i = orthonormal_basis(1)
    b_j = orthonormal_basis(2)
    b_k = orthonormal_basis(3)
    q_ij, s_ij, m_ij = engine._polar_transport(b_i, b_j)
    q_jk, _, m_jk = engine._polar_transport(b_j, b_k)
    q_ik, _, m_ik = engine._polar_transport(b_i, b_k)
    raw_excess = engine._interaction_excess(m_ik, m_jk, m_ij)
    polar_excess = engine._interaction_excess(q_ik, q_jk, q_ij)
    geo = engine.analyze(synthetic_embeddings())
    loop = geo.loops[0] if geo.loops else None
    checks = {
        "raw_overlap_orientation": np.allclose(m_ij, b_j.T @ b_i),
        "raw_overlap_not_named_transport": not np.allclose(m_ij.T @ m_ij, np.eye(m_ij.shape[1]), atol=1e-3),
        "polar_transport_is_orthogonal": np.allclose(q_ij.T @ q_ij, np.eye(q_ij.shape[1]), atol=1e-6),
        "singular_values_are_principal_cosines": bool(np.all(s_ij >= -1e-9) and np.all(s_ij <= 1.0 + 1e-9)),
        "raw_and_polar_excess_are_separate": abs(raw_excess - polar_excess) > 1e-6,
        "engine_produces_loops": loop is not None,
        "loop_has_corrected_fields": bool(
            loop is not None
            and hasattr(loop, "raw_interaction_excess")
            and hasattr(loop, "polar_interaction_excess")
            and hasattr(loop, "polar_holonomy")
            and hasattr(loop, "mean_singular_value")
        ),
        "backward_compatible_aliases": bool(
            loop is not None
            and loop.interaction_excess == loop.raw_interaction_excess
            and loop.holonomy_raw == loop.polar_holonomy
            and loop.interaction_z == loop.raw_interaction_z
        ),
    }
    result = {
        "schema": "ogcf_corrected_geometry_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "transport": {
            "singular_values": [float(x) for x in s_ij],
            "raw_interaction_excess": float(raw_excess),
            "polar_interaction_excess": float(polar_excess),
        },
        "loop_sample": {
            "raw_interaction_excess": float(loop.raw_interaction_excess) if loop else None,
            "polar_interaction_excess": float(loop.polar_interaction_excess) if loop else None,
            "raw_interaction_z": float(loop.raw_interaction_z) if loop else None,
            "polar_interaction_z": float(loop.polar_interaction_z) if loop else None,
            "polar_holonomy": float(loop.polar_holonomy) if loop else None,
            "mean_singular_value": float(loop.mean_singular_value) if loop else None,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Corrected Geometry Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Transport", "", "```json", json.dumps(result["transport"], indent=2), "```"])
    lines.extend(["", "## Loop Sample", "", "```json", json.dumps(result["loop_sample"], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
