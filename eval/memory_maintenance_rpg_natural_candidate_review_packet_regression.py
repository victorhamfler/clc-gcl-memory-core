from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.memory_maintenance_rpg_natural_candidate_review_packet import LABEL_OPTIONS, build_packet  # noqa: E402


OUT_DIR = REPO_ROOT / "experiments"
NATURAL_JSON = OUT_DIR / "memory_maintenance_rpg_natural_candidate_calibration_results.json"
OUT_JSON = OUT_DIR / "memory_maintenance_rpg_natural_candidate_review_packet_regression_results.json"
OUT_MD = OUT_DIR / "memory_maintenance_rpg_natural_candidate_review_packet_regression_report.md"


def ensure_natural_report() -> dict:
    if not NATURAL_JSON.exists():
        subprocess.run(
            [sys.executable, str(ROOT / "eval" / "memory_maintenance_rpg_natural_candidate_calibration.py")],
            cwd=str(ROOT),
            check=True,
            timeout=300,
        )
    value = json.loads(NATURAL_JSON.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def main() -> int:
    packet = build_packet(ensure_natural_report(), per_class=3)
    items = [item for item in packet.get("items") or [] if isinstance(item, dict)]
    classes = set(packet.get("class_counts") or {})
    checks = {
        "schema_ok": packet.get("schema") == "memory_maintenance_rpg_natural_candidate_review_packet/v1",
        "has_items": packet.get("packet_item_count") == len(items) and len(items) > 0,
        "has_representative_classes": "near_duplicate_like" in classes
        and any(label in classes for label in ("stale_or_update_like", "bridge_like", "cross_domain_related")),
        "labels_are_blank_for_review": all(item.get("review_label") == "" for item in items),
        "allowed_labels_present": packet.get("allowed_labels") == LABEL_OPTIONS
        and all(item.get("allowed_labels") == LABEL_OPTIONS for item in items),
        "rpg_metrics_present": all(
            float(item.get("rpg_target_relation") or 0.0) > 0.0
            and float(item.get("rpg_target_island_ratio") or 0.0) > 0.0
            for item in items
        ),
        "not_policy_ready": packet.get("ready_for_policy_use") is False
        and packet.get("promotion_ready") is False,
        "mutation_never_allowed": packet.get("mutation_allowed") is False
        and all(item.get("mutation_allowed") is False for item in items),
        "report_only": packet.get("report_only") is True
        and packet.get("mutates_db") is False
        and packet.get("mutates_runtime") is False
        and packet.get("mutates_config") is False,
    }
    result = {
        "schema": "memory_maintenance_rpg_natural_candidate_review_packet_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "packet": packet,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance RPG Natural Candidate Review Packet Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
