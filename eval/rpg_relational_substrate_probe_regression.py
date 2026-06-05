from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.rpg_memory import RPGMemoryRecord, run_rpg_memory_probe  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "rpg_relational_substrate_probe_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "rpg_relational_substrate_probe_regression_report.md"


def fixture_records() -> list[RPGMemoryRecord]:
    rows = [
        RPGMemoryRecord(
            memory_id="dup_keep",
            text="Duplicate same fact: Victor stores alpha route in memory.",
            domain="project",
            source="direct_user",
            timestamp="2026-06-04T12:00:00Z",
            authority=1.0,
            status="active",
            retrieval_count=9,
            embedding=(3.0, 0.0, 0.0, 0.15, 0.0, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="dup_extra",
            text="Duplicate same fact: Victor stores alpha route in memory.",
            domain="project",
            source="direct_user",
            timestamp="2026-06-04T12:01:00Z",
            authority=0.95,
            status="active",
            retrieval_count=8,
            embedding=(2.96, 0.02, 0.0, 0.16, 0.0, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="current_pref",
            text="Current preference: Victor now uses beta route for the project.",
            domain="profile",
            source="direct_user",
            timestamp="2026-06-04T12:02:00Z",
            authority=1.0,
            status="active",
            retrieval_count=7,
            embedding=(0.0, 3.0, 0.05, 0.0, 0.2, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="stale_pref",
            text="Old stale preference: Victor used alpha route before the update.",
            domain="profile",
            source="old_agent_inference",
            timestamp="2026-05-01T12:02:00Z",
            authority=0.2,
            status="deprecated",
            retrieval_count=6,
            embedding=(0.02, 2.7, 0.25, 0.0, 0.2, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="bridge_csd_gcl",
            text="Bridge note connects CSD contradiction pressure and G-CL domain curvature.",
            domain="bridge",
            source="maintenance_probe",
            timestamp="2026-06-04T12:03:00Z",
            authority=0.5,
            status="active",
            retrieval_count=4,
            embedding=(1.55, 1.55, 0.3, 0.35, 0.35, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="bridge_erg_selector",
            text="Bridge note connects ERG projector graph review and selector policy.",
            domain="bridge",
            source="maintenance_probe",
            timestamp="2026-06-04T12:04:00Z",
            authority=0.5,
            status="active",
            retrieval_count=4,
            embedding=(1.5, 1.45, 0.35, 0.4, 0.3, 0.0),
        ),
        RPGMemoryRecord(
            memory_id="robotics_safety",
            text="Robotics controller uses torque and actuator current safety limits.",
            domain="robotics",
            source="project_doc",
            timestamp="2026-06-04T12:05:00Z",
            authority=0.8,
            status="active",
            retrieval_count=3,
            embedding=(0.0, 0.0, 3.0, 0.0, 0.0, 0.25),
        ),
        RPGMemoryRecord(
            memory_id="robotics_current",
            text="Robotics actuator current checks must stay separate from memory routing.",
            domain="robotics",
            source="project_doc",
            timestamp="2026-06-04T12:06:00Z",
            authority=0.8,
            status="active",
            retrieval_count=2,
            embedding=(0.0, 0.0, 2.92, 0.0, 0.0, 0.35),
        ),
        RPGMemoryRecord(
            memory_id="style_evidence",
            text="Assistant style should be concise and evidence backed.",
            domain="style",
            source="direct_user",
            timestamp="2026-06-04T12:07:00Z",
            authority=0.9,
            status="active",
            retrieval_count=5,
            embedding=(0.0, 0.0, 0.0, 3.0, 0.0, 0.2),
        ),
        RPGMemoryRecord(
            memory_id="tool_timestamp",
            text="Tool results should be timestamped before memory write.",
            domain="tools",
            source="system_rule",
            timestamp="2026-06-04T12:08:00Z",
            authority=0.85,
            status="active",
            retrieval_count=2,
            embedding=(0.0, 0.0, 0.0, 0.0, 3.0, 0.2),
        ),
    ]
    return rows


def write_report(result: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# RPG Relational Substrate Probe Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in result["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Probe", "", "```json", json.dumps(result["probe"], indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    probe = run_rpg_memory_probe(fixture_records(), rank_k=4)
    pair_reports = {item["pair_name"]: item for item in probe["constraint_pair_reports"]}
    active_deprecated = pair_reports.get("active_vs_deprecated") or {}
    duplicate_contradiction = pair_reports.get("duplicate_vs_contradiction") or {}
    domain_pair = next((item for item in pair_reports.values() if item["pair_name"].endswith("_vs_recency")), {})
    all_pairs = list(pair_reports.values())
    substrate_symmetry_error = float(probe.get("substrate_symmetry_error", 1.0))
    checks = {
        "schema_ok": probe.get("schema") == "rpg_memory_relational_substrate_probe/v1",
        "report_only": probe.get("report_only") is True
        and probe.get("mutates_db") is False
        and probe.get("mutates_runtime") is False
        and probe.get("mutates_config") is False,
        "substrate_normalized": abs(float(probe.get("substrate_fro_norm") or 0.0) - 1.0) < 1e-9,
        "substrate_symmetric": substrate_symmetry_error < 1e-12,
        "constraint_pairs_present": {"active_vs_deprecated", "source_authority_vs_retrieval", "duplicate_vs_contradiction"}.issubset(
            set(pair_reports)
        )
        and bool(domain_pair),
        "projectors_stable": all(
            float(item.get("idempotence_error", 1.0)) < 1e-10
            and float(item.get("symmetry_error", 1.0)) < 1e-10
            and float(item.get("spectral_gap") or 0.0) > 0.0
            for item in all_pairs
        ),
        "island_signal_present": float(probe.get("max_island_ratio") or 0.0) > 1.0,
        "curvature_activity_present": float(probe.get("max_omega_norm") or 0.0) > 0.0,
        "active_deprecated_sees_deprecated_status": "deprecated" in (active_deprecated.get("sector_statuses") or []),
        "duplicate_contradiction_sees_stale_or_duplicate": any(
            memory_id in (duplicate_contradiction.get("sector_memory_ids") or [])
            for memory_id in ("dup_keep", "dup_extra", "stale_pref")
        ),
        "domain_recency_has_coherent_sector": float(domain_pair.get("island_ratio") or 0.0) > 1.0
        and len(domain_pair.get("sector_memory_ids") or []) >= 3,
    }
    result = {
        "schema": "rpg_relational_substrate_probe_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "probe": probe,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_db": False,
        "mutates_config": False,
    }
    write_report(result)
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
