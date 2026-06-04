from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.ogcf_selector import augment_selector_features  # noqa: E402
from core.ogcf_signals import OGCFSignalProvider  # noqa: E402
from core.selector_runtime import selector_features_from_retrieval_context  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "ogcf_erg_signal_provider_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_erg_signal_provider_regression_report.md"


def retrieval_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "mem_core",
            "memory_id": "mem_core",
            "score": 0.93,
            "claim_scope_score": 0.84,
            "text_match_score": 0.82,
            "answer_type_score": 0.74,
            "authority_state": "standalone",
            "stored_contradiction_score": 0.0,
            "supersession_score": 0.0,
            "relation_supersession_score": 0.0,
            "text": "Core bridge memory: CSD and G-CL sector pressure share a projector boundary.",
        },
        {
            "id": "mem_halo",
            "memory_id": "mem_halo",
            "score": 0.86,
            "claim_scope_score": 0.76,
            "text_match_score": 0.70,
            "answer_type_score": 0.68,
            "authority_state": "standalone",
            "stored_contradiction_score": 0.0,
            "supersession_score": 0.0,
            "relation_supersession_score": 0.0,
            "text": "Halo bridge memory: projector graph neighbors should be reviewed without mutating policy.",
        },
    ]


def erg_meta() -> dict[str, Any]:
    return {
        "max_interaction_z": 0.0,
        "bridge_overload_score": 0.0,
        "loop_count": 0,
        "risk_regions": [
            {
                "clusters": "4-6-8",
                "interaction_z": 0.0,
                "omega_norm": 0.91,
                "C4": 1.72,
                "core_halo_slope": -0.13,
                "failure_mode": "erg_core_halo_review",
                "recommended_action": "review",
            }
        ],
        "bridge_clusters": [],
        "cluster_summary": [{"cluster_id": 4, "size": 12, "local_defect": 0.04}],
        "memory_cluster_map": {"mem_core": 4, "mem_halo": 4},
        "projector_distance_summary": {
            "edge_count": 6.0,
            "mean_distance": 0.7,
            "min_distance": 0.2,
            "max_distance": 1.4,
            "std_distance": 0.21,
        },
    }


def main() -> int:
    rows = retrieval_rows()
    provider = OGCFSignalProvider(erg_meta())
    signals = provider.signals_for_retrieval_rows(rows)
    base_features, base_diag = selector_features_from_retrieval_context(rows, condition_name="standard_budget144")
    augmented, diagnostics = augment_selector_features(base_features, rows, erg_meta(), base_diag)
    checks = {
        "erg_signals_exported": signals["ogcf_omega_norm"] == 0.91
        and signals["ogcf_core_halo_score"] == 1.72
        and signals["ogcf_core_halo_slope"] == -0.13
        and signals["ogcf_projector_graph_anomaly"] > 0.0,
        "selector_diagnostics_carry_erg": diagnostics["ogcf_omega_norm"] == 0.91
        and diagnostics["ogcf_core_halo_score"] == 1.72
        and diagnostics["ogcf_core_halo_slope"] == -0.13
        and diagnostics["ogcf_projector_graph_anomaly"] == signals["ogcf_projector_graph_anomaly"],
        "erg_report_only_does_not_raise_bridge": diagnostics["ogcf_bridge_overload_score"] == 0.0
        and diagnostics["ogcf_structural_pressure"] == 0.0,
        "erg_report_only_does_not_change_clc_features": augmented.memory_bad_rate == base_features.memory_bad_rate
        and augmented.probe_drop == base_features.probe_drop
        and augmented.csd_ratio == base_features.csd_ratio,
        "contradiction_peak_unchanged": diagnostics["adjusted_contradiction_peak"] == diagnostics.get("contradiction_peak", 0.0),
    }
    result = {
        "schema": "ogcf_erg_signal_provider_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "signals": signals,
        "diagnostics": {key: value for key, value in diagnostics.items() if key.startswith("ogcf")},
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF ERG Signal Provider Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Signals", "", "```json", json.dumps(signals, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
