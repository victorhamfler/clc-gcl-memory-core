from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_review_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_rpg_rehearsal_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_rpg_rehearsal_calibration_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_bank(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Memory bank must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rehearsal_review_memory_bank/v1":
        raise ValueError(f"Unsupported memory bank schema: {value.get('schema')}")
    return value


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def cluster_label(cluster: dict[str, Any]) -> str:
    readiness = str(cluster.get("readiness") or "")
    key = str(cluster.get("key") or "")
    if readiness == "rehearsal_safe_evidence_ready" or key.endswith("|safe_to_review"):
        return "safe"
    if "stale" in key:
        return "stale_risk"
    if "bridge" in key:
        return "bridge_risk"
    if "semantic" in key:
        return "semantic_risk"
    if str(cluster.get("readiness") or "").startswith("blocked_"):
        return "blocked_risk"
    return "needs_review"


def metric_value(cluster: dict[str, Any], metric: str) -> float:
    summary = cluster.get("rpg_summary") if isinstance(cluster.get("rpg_summary"), dict) else {}
    return float(summary.get(metric) or 0.0)


def calibrate_bank(bank: dict[str, Any]) -> dict[str, Any]:
    clusters = [
        cluster
        for cluster in bank.get("clusters") or []
        if isinstance(cluster, dict)
        and isinstance(cluster.get("rpg_summary"), dict)
        and int((cluster.get("rpg_summary") or {}).get("annotation_count") or 0) > 0
    ]
    labeled = []
    for cluster in clusters:
        label = cluster_label(cluster)
        row = {
            "schema": "memory_maintenance_rpg_rehearsal_calibration_cluster/v1",
            "key": cluster.get("key"),
            "label": label,
            "readiness": cluster.get("readiness"),
            "support": cluster.get("support"),
            "run_count": cluster.get("run_count"),
            "target_mean_relation": metric_value(cluster, "target_mean_relation_mean"),
            "target_island_ratio": metric_value(cluster, "target_island_ratio_mean"),
            "sector_island_ratio": metric_value(cluster, "sector_island_ratio_mean"),
            "omega_norm": metric_value(cluster, "omega_norm_mean"),
            "target_sector_overlap_ratio": metric_value(cluster, "target_sector_overlap_ratio_mean"),
            "duplicate_contradiction_overlap": metric_value(cluster, "duplicate_contradiction_overlap_mean"),
            "active_deprecated_overlap": metric_value(cluster, "active_deprecated_overlap_mean"),
            "risk_flags": (cluster.get("rpg_summary") or {}).get("risk_flags") or {},
            "report_only": True,
        }
        labeled.append(row)

    safe = [row for row in labeled if row["label"] == "safe"]
    blocked = [row for row in labeled if row["label"] != "safe"]
    stale_or_bridge = [row for row in blocked if row["label"] in {"stale_risk", "bridge_risk"}]
    safe_relation_mean = mean([row["target_mean_relation"] for row in safe])
    blocked_relation_mean = mean([row["target_mean_relation"] for row in blocked])
    safe_island_mean = mean([row["target_island_ratio"] for row in safe])
    blocked_island_mean = mean([row["target_island_ratio"] for row in blocked])
    safe_overlap_mean = mean([row["active_deprecated_overlap"] for row in safe])
    stale_bridge_overlap_mean = mean([row["active_deprecated_overlap"] for row in stale_or_bridge])
    relation_threshold = round((safe_relation_mean + blocked_relation_mean) / 2.0, 6)
    island_threshold = round((safe_island_mean + blocked_island_mean) / 2.0, 6)
    predictions = []
    for row in labeled:
        predicted_safe = (
            row["target_mean_relation"] >= relation_threshold
            and row["target_island_ratio"] >= island_threshold
            and row["active_deprecated_overlap"] <= max(0.5, safe_overlap_mean + 0.5)
        )
        predictions.append(
            {
                "key": row["key"],
                "label": row["label"],
                "predicted": "safe" if predicted_safe else "risk_or_review",
                "correct": predicted_safe is (row["label"] == "safe"),
            }
        )
    correct = sum(1 for item in predictions if item["correct"])
    label_counts = Counter(row["label"] for row in labeled)
    return {
        "schema": "memory_maintenance_rpg_rehearsal_calibration/v1",
        "description": "Report-only calibration of RPG rehearsal metrics against symbolic rehearsal decisions.",
        "cluster_count": len(clusters),
        "label_counts": dict(sorted(label_counts.items())),
        "safe_relation_mean": round(safe_relation_mean, 6),
        "blocked_relation_mean": round(blocked_relation_mean, 6),
        "safe_target_island_mean": round(safe_island_mean, 6),
        "blocked_target_island_mean": round(blocked_island_mean, 6),
        "safe_active_deprecated_overlap_mean": round(safe_overlap_mean, 6),
        "stale_bridge_active_deprecated_overlap_mean": round(stale_bridge_overlap_mean, 6),
        "relation_threshold_probe": relation_threshold,
        "island_threshold_probe": island_threshold,
        "prediction_accuracy": round(correct / max(len(predictions), 1), 6),
        "predictions": predictions,
        "clusters": labeled,
        "ready_for_policy_use": False,
        "next_action": "collect_more_real_rehearsal_runs_before_using_rpg_policy"
        if len(clusters) < 8
        else "compare_against_real_maintenance_outcomes",
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Rehearsal Calibration",
        "",
        "Report-only calibration of RPG rehearsal metrics against symbolic review decisions.",
        "",
        f"Clusters: `{report['cluster_count']}`",
        f"Prediction accuracy probe: `{report['prediction_accuracy']}`",
        f"Ready for policy use: `{report['ready_for_policy_use']}`",
        f"Next action: `{report['next_action']}`",
        "",
        "## Means",
        "",
        "| metric | safe | blocked/risk |",
        "| --- | ---: | ---: |",
        f"| target relation | {report['safe_relation_mean']} | {report['blocked_relation_mean']} |",
        f"| target island | {report['safe_target_island_mean']} | {report['blocked_target_island_mean']} |",
        f"| active/deprecated overlap | {report['safe_active_deprecated_overlap_mean']} | {report['stale_bridge_active_deprecated_overlap_mean']} |",
        "",
        "## Clusters",
        "",
        "| key | label | relation | island | active/deprecated |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in report.get("clusters") or []:
        lines.append(
            f"| `{clean_cell(row.get('key'), 90)}` | `{row.get('label')}` | "
            f"{row.get('target_mean_relation')} | {row.get('target_island_ratio')} | "
            f"{row.get('active_deprecated_overlap')} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate RPG rehearsal metrics against rehearsal review outcomes.")
    parser.add_argument("--memory-bank", default=str(DEFAULT_BANK))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = calibrate_bank(load_bank(Path(args.memory_bank)))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "cluster_count": report["cluster_count"],
                "prediction_accuracy": report["prediction_accuracy"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
