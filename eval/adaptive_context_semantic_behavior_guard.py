from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_SCORER = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_scorer_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_context_semantic_behavior_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return loaded


def build_report(scorer_path: Path) -> dict[str, Any]:
    scorer = read_json(scorer_path)
    holdout = (scorer.get("evaluations") or {}).get("adaptive_behavior_holdout") or {}
    weighted = holdout.get("weighted") or {}
    semantic = weighted.get("semantic_hybrid") or {}
    symbolic = weighted.get("symbolic_health_baseline") or {}
    behavior_config = scorer.get("behavior_config") or {}
    semantic_accuracy = float(semantic.get("accuracy", 0.0))
    symbolic_accuracy = float(symbolic.get("accuracy", 1.0))
    semantic_brier = float(semantic.get("brier", 1.0))
    symbolic_brier = float(symbolic.get("brier", 0.0))
    checks = {
        "schema_ok": scorer.get("schema") == "adaptive_context_semantic_behavior_scorer/v1",
        "scorer_ok": scorer.get("ok") is True,
        "report_only": scorer.get("mutates_runtime") is False and scorer.get("mutates_config") is False,
        "config_schema_ok": behavior_config.get("schema") == "adaptive_behavior_config/v1",
        "has_superfamilies": bool(behavior_config.get("superfamilies")),
        "has_behavior_holdout": int(holdout.get("groups") or 0) > 0 and int(holdout.get("test_count") or 0) > 0,
        "semantic_beats_symbolic_accuracy": semantic_accuracy > symbolic_accuracy,
        "semantic_beats_symbolic_brier": semantic_brier < symbolic_brier,
    }
    readiness = "promotion_candidate" if all(checks.values()) else "blocked"
    return {
        "schema": "adaptive_context_semantic_behavior_guard/v1",
        "description": "Report-only guard for semantic behavior-family scorer promotion readiness.",
        "ok": all(checks.values()),
        "readiness": readiness,
        "scorer_path": str(scorer_path),
        "checks": checks,
        "metrics": {
            "semantic_accuracy": semantic_accuracy,
            "symbolic_accuracy": symbolic_accuracy,
            "semantic_brier": semantic_brier,
            "symbolic_brier": symbolic_brier,
        },
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Context Semantic Behavior Guard",
        "",
        "This guard is report-only. It does not promote runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Readiness: `{report['readiness']}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(report.get("metrics"), indent=2),
        "```",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard semantic behavior scorer promotion readiness.")
    parser.add_argument("--scorer", default=str(DEFAULT_SCORER))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    report = build_report(Path(args.scorer))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(json.dumps({"ok": report["ok"], "readiness": report["readiness"], "metrics": report["metrics"], "json": str(Path(args.out_json)), "markdown": str(Path(args.out_md))}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
