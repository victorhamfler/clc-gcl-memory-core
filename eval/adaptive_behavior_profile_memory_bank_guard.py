from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Memory bank must be a JSON object: {path}")
    return value


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def contains_mutation_marker(bank: dict[str, Any]) -> bool:
    text = json.dumps(bank, sort_keys=True).lower()
    markers = (
        '"mutates_config": true',
        '"mutates_runtime": true',
        '"auto_promote": true',
        '"promoted": true',
        '"config_patch"',
        '"runtime_patch"',
        '"apply_to_config"',
    )
    return any(marker in text for marker in markers)


def build_guard(bank_path: Path) -> dict[str, Any]:
    bank = read_json(bank_path)
    issues: list[dict[str, Any]] = []
    clusters = [item for item in bank.get("clusters") or [] if isinstance(item, dict)]

    if bank.get("schema") != "adaptive_behavior_profile_memory_bank/v1":
        issues.append({"severity": "error", "reason": "bad_schema", "value": bank.get("schema")})
    if bank.get("report_only") is not True:
        issues.append({"severity": "error", "reason": "bank_not_report_only"})
    if bank.get("mutates_config") is not False or bank.get("mutates_runtime") is not False:
        issues.append({"severity": "error", "reason": "bank_mutation_flags"})
    if contains_mutation_marker(bank):
        issues.append({"severity": "error", "reason": "mutation_marker_present"})
    if not clusters:
        issues.append({"severity": "warning", "reason": "no_clusters"})

    ready_thresholds = bank.get("ready_thresholds") if isinstance(bank.get("ready_thresholds"), dict) else {}
    ready_profiles = int(ready_thresholds.get("ready_profiles") or 2)
    for cluster in clusters:
        readiness = normalize_text(cluster.get("readiness"))
        distinct_profiles = int(cluster.get("distinct_profiles") or 0)
        status_counts = cluster.get("status_counts") if isinstance(cluster.get("status_counts"), dict) else {}
        if readiness == "recurrence_ready" and distinct_profiles < ready_profiles:
            issues.append(
                {
                    "severity": "error",
                    "reason": "ready_cluster_without_required_profile_recurrence",
                    "key": cluster.get("key"),
                }
            )
        if readiness == "recurrence_ready" and int(status_counts.get("candidate") or 0) <= 0:
            issues.append(
                {
                    "severity": "error",
                    "reason": "ready_cluster_without_candidate_status",
                    "key": cluster.get("key"),
                }
            )
        if readiness == "hold" and distinct_profiles >= ready_profiles and int(status_counts.get("candidate") or 0) > 0:
            issues.append(
                {
                    "severity": "warning",
                    "reason": "recurring_candidate_still_hold",
                    "key": cluster.get("key"),
                }
            )

    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    ready_clusters = [cluster for cluster in clusters if normalize_text(cluster.get("readiness")) == "recurrence_ready"]
    return {
        "schema": "adaptive_behavior_profile_memory_bank_guard/v1",
        "ok": not errors,
        "readiness": "analysis_ready" if not errors else "blocked",
        "bank": str(bank_path),
        "cluster_count": len(clusters),
        "ready_cluster_count": len(ready_clusters),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
        "ready_clusters": [
            {
                "key": cluster.get("key"),
                "behavior_family": cluster.get("behavior_family"),
                "support": cluster.get("support"),
                "distinct_profiles": cluster.get("distinct_profiles"),
                "status_counts": cluster.get("status_counts"),
            }
            for cluster in ready_clusters
        ],
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }


def write_guard(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Profile Memory Bank Guard",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        f"Clusters: `{report['cluster_count']}`",
        f"Ready clusters: `{report['ready_cluster_count']}`",
        f"Errors: `{report['error_count']}`",
        f"Warnings: `{report['warning_count']}`",
        "",
        "## Ready Clusters",
        "",
        "```json",
        json.dumps(report["ready_clusters"], indent=2),
        "```",
        "",
        "## Issues",
        "",
        "```json",
        json.dumps(report["issues"], indent=2),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard adaptive behavior profile memory bank artifacts.")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_guard(args.bank)
    write_guard(report, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "json": str(args.out_json)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
