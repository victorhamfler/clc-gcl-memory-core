from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_REVIEW_SEPARATION = REPO_ROOT / "experiments" / "controller_packet_review_separation_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_bridge_separator_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read review-separation artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return loaded


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_bridge_rule(analysis: dict[str, Any]) -> dict[str, Any]:
    features = analysis.get("features") if isinstance(analysis.get("features"), dict) else {}
    positive_intents = sorted(str(item) for item in features.get("candidate_intents") or [] if str(item) != "unknown")
    negative_intents = sorted(str(item) for item in features.get("review_intents") or [] if str(item) != "unknown")
    positive_labels = sorted(str(item) for item in features.get("candidate_only_labels") or [])
    negative_labels = sorted(str(item) for item in features.get("review_only_labels") or [])
    intent_separation = bool(set(features.get("candidate_only_intents") or []) or set(features.get("review_only_intents") or []))
    support_total = int(analysis.get("candidate_support") or 0) + int(analysis.get("review_support") or 0)
    source_log_min = min(int(analysis.get("candidate_source_log_count") or 0), int(analysis.get("review_source_log_count") or 0))
    return {
        "id": f"bridge_separator_{analysis.get('candidate_id')}_{analysis.get('review_id')}",
        "candidate_id": analysis.get("candidate_id"),
        "review_id": analysis.get("review_id"),
        "positive_intents": positive_intents,
        "negative_intents": negative_intents,
        "positive_labels": positive_labels,
        "negative_labels": negative_labels,
        "intent_separation": intent_separation,
        "support_total": support_total,
        "source_log_min": source_log_min,
        "rule": {
            "positive_when": {
                "ogcf_meta_present": True,
                "intent_in": positive_intents,
                "feedback_label_in": positive_labels,
            },
            "negative_when": {
                "ogcf_meta_present": True,
                "intent_in": negative_intents,
                "feedback_label_in": negative_labels,
            },
        },
        "readiness": "holdout_ready"
        if support_total >= 8 and source_log_min >= 2 and positive_labels and negative_labels
        else "collect_more",
        "promotion_ready": False,
        "promotion_blocker": "report-only separator candidate; needs holdout replay before runtime use",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_report(review_separation_path: Path) -> dict[str, Any]:
    artifact = read_json(review_separation_path)
    analyses = [item for item in artifact.get("analyses") or [] if isinstance(item, dict)]
    bridge_analyses = [
        item
        for item in analyses
        if item.get("recommended_action") == "train_or_calibrate_bridge_intent_separator_before_promotion"
        and item.get("candidate_kind") == "ogcf_bridge_behavior_candidate"
    ]
    separators = [build_bridge_rule(item) for item in bridge_analyses]
    return {
        "schema": "controller_packet_bridge_separator/v1",
        "description": "Report-only candidate separator for useful OGCF bridge warnings vs OGCF false positives.",
        "ok": bool(separators),
        "source_review_separation": str(review_separation_path),
        "analysis_count": len(analyses),
        "bridge_analysis_count": len(bridge_analyses),
        "separator_count": len(separators),
        "separators": separators,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Bridge Separator",
        "",
        "This report is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Separators: `{report['separator_count']}`",
        "",
        "| id | readiness | positive intents | negative intents | positive labels | negative labels |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["separators"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                item["id"],
                item["readiness"],
                clean_cell(", ".join(item["positive_intents"])),
                clean_cell(", ".join(item["negative_intents"])),
                clean_cell(", ".join(item["positive_labels"])),
                clean_cell(", ".join(item["negative_labels"])),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build report-only OGCF bridge separator candidates.")
    parser.add_argument("--review-separation", type=Path, default=DEFAULT_REVIEW_SEPARATION)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.review_separation)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "separator_count": report["separator_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
