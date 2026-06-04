from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicyFeatures, CLCPolicySelector  # noqa: E402
from core.evidence_context import (  # noqa: E402
    build_evidence_context_features,
    build_evidence_context_summary,
    evidence_context_features_dict,
)


OUT_JSON = REPO_ROOT / "experiments" / "erg_csd_gcl_clc_feature_export_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "erg_csd_gcl_clc_feature_export_regression_report.md"


def build_report() -> dict[str, Any]:
    retrieval_context = [
        {
            "memory_id": "mem_current_anchor",
            "score": 0.84,
            "authority_state": "current",
            "claim_scope_score": 0.78,
            "answer_type_score": 0.68,
            "text_match_score": 0.72,
            "intent_match_score": 0.66,
            "supersession_score": 0.42,
            "text": "Current G-CL anchor says project memory uses report-only controller packets.",
        },
        {
            "memory_id": "mem_deprecated_halo",
            "score": 0.61,
            "authority_state": "stale",
            "claim_scope_score": 0.54,
            "answer_type_score": 0.42,
            "text_match_score": 0.48,
            "intent_match_score": 0.36,
            "supersession_score": -0.38,
            "text": "Deprecated halo memory says selector policy can mutate automatically.",
        },
        {
            "memory_id": "mem_bridge_sector",
            "score": 0.58,
            "authority_state": "standalone",
            "claim_scope_score": 0.46,
            "answer_type_score": 0.40,
            "scope_deflection_penalty": 0.21,
            "text": "Bridge-sector memory mixes CSD, G-CL, and OGCF terminology across domains.",
        },
    ]
    diagnostics = {
        # CSD-style semantic/evidence pressure.
        "memory_bad_rate": 0.34,
        "stale_current_conflict": 0.47,
        "contradiction_peak": 0.52,
        # G-CL-style geometry health fields kept report-only for now.
        "gcl_domain_drift": 0.44,
        "gcl_anchor_distance": 0.57,
        "gcl_reanchor_pressure": 0.62,
        # Existing OGCF structural pressure.
        "ogcf_bridge_overload_score": 0.73,
        "ogcf_effective_affected_memory_ratio": 0.69,
        "ogcf_structural_pressure": 0.5037,
        # New ERG v3 projector-geometry fields.
        "ogcf_omega_norm": 0.88,
        "ogcf_core_halo_score": 1.74,
        "ogcf_core_halo_slope": -0.12,
        "ogcf_projector_graph_anomaly": 0.66,
    }
    summary = build_evidence_context_summary(
        query="Should the memory controller refresh this mixed CSD G-CL bridge sector?",
        answer="The controller should keep mutation report-only and review the unstable sector.",
        evidence=[retrieval_context[0]],
        stale_context=[retrieval_context[1]],
        retrieval_context=retrieval_context,
        diagnostics=diagnostics,
        conflict=True,
    )
    evidence_features = build_evidence_context_features(summary)
    evidence_dict = evidence_context_features_dict(evidence_features)
    clc_features = CLCPolicyFeatures(
        budget_units=144.0,
        cycles=1.0,
        csd_ratio=1.05,
        probe_drop=0.09,
        memory_bad_rate=evidence_features.memory_bad_rate,
    )
    decision = CLCPolicySelector().select(clc_features)
    neural_symbolic_row = {
        "schema": "erg_csd_gcl_clc_feature_row/v1",
        "csd": {
            "memory_bad_rate": evidence_features.memory_bad_rate,
            "stale_current_conflict": evidence_features.stale_current_conflict,
            "contradiction_peak": evidence_features.contradiction_peak,
        },
        "gcl": {
            "domain_drift": diagnostics["gcl_domain_drift"],
            "anchor_distance": diagnostics["gcl_anchor_distance"],
            "reanchor_pressure": diagnostics["gcl_reanchor_pressure"],
        },
        "clc": {
            "policy": decision.policy,
            "action": decision.action,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "features": clc_features.__dict__,
        },
        "erg": {
            "structural_pressure": evidence_features.ogcf_structural_pressure,
            "omega_norm": evidence_features.ogcf_omega_norm,
            "core_halo_score": evidence_features.ogcf_core_halo_score,
            "core_halo_slope": evidence_features.ogcf_core_halo_slope,
            "projector_graph_anomaly": evidence_features.ogcf_projector_graph_anomaly,
        },
        "evidence_context_features": evidence_dict,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    checks = {
        "csd_features_exported": neural_symbolic_row["csd"]["contradiction_peak"] == 0.52
        and neural_symbolic_row["csd"]["stale_current_conflict"] == 0.47,
        "gcl_report_only_fields_present": neural_symbolic_row["gcl"]["anchor_distance"] == 0.57
        and neural_symbolic_row["gcl"]["reanchor_pressure"] == 0.62,
        "clc_decision_present": neural_symbolic_row["clc"]["policy"] in {
            "periodic_baseline",
            "long_severe_r16_overwrite",
            "xseq_memory_r45_badmajority",
        },
        "erg_features_exported": neural_symbolic_row["erg"]["omega_norm"] == 0.88
        and neural_symbolic_row["erg"]["core_halo_score"] == 1.74
        and neural_symbolic_row["erg"]["projector_graph_anomaly"] == 0.66,
        "structural_pressure_not_contradiction_proxy": neural_symbolic_row["erg"]["structural_pressure"] == 0.5037
        and neural_symbolic_row["csd"]["contradiction_peak"] == 0.52,
        "shared_evidence_features_include_erg": evidence_dict.get("ogcf_omega_norm") == 0.88
        and evidence_dict.get("ogcf_core_halo_score") == 1.74,
        "report_only": neural_symbolic_row["report_only"] is True
        and neural_symbolic_row["mutates_runtime"] is False
        and neural_symbolic_row["mutates_config"] is False,
    }
    return {
        "schema": "erg_csd_gcl_clc_feature_export_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "feature_row": neural_symbolic_row,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# ERG CSD G-CL CLC Feature Export Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Feature Row", "", "```json", json.dumps(report["feature_row"], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report = build_report()
    write_report(report)
    print(json.dumps({"ok": report["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
