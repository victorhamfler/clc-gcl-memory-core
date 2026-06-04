from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_candidates_results.json"
DEFAULT_LABELS_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_review_labels_template.json"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_eval_report.md"

USEFUL_LABELS = {
    "useful_review",
    "correct_duplicate",
    "correct_stale",
    "correct_conflict_update",
    "correct_bridge_review",
}
NEGATIVE_LABELS = {
    "noisy_review",
    "clean_memory",
    "false_positive",
    "unsafe_to_act",
}
NEUTRAL_LABELS = {
    "needs_more_evidence",
    "already_resolved",
    "",
}


def load_json_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    if text[0] in "[{":
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def priority_score(candidate: dict[str, Any]) -> float:
    priority = candidate.get("maintenance_priority") if isinstance(candidate.get("maintenance_priority"), dict) else {}
    return float(priority.get("priority_score") or candidate.get("confidence") or 0.0)


def normalize_labels(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        labels = raw.get("labels")
        if isinstance(labels, list):
            return [item for item in labels if isinstance(item, dict)]
        if raw.get("candidate_id"):
            return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def label_class(label: str) -> str:
    value = str(label or "").strip().lower()
    if value in USEFUL_LABELS:
        return "useful"
    if value in NEGATIVE_LABELS:
        return "negative"
    if value in NEUTRAL_LABELS:
        return "neutral"
    return "unknown"


def build_eval(candidates_report: dict[str, Any], labels_raw: Any, *, top_k: int = 5) -> dict[str, Any]:
    labels = normalize_labels(labels_raw)
    label_by_id = {
        str(item.get("candidate_id") or "").strip(): {
            **item,
            "label": str(item.get("label") or "").strip().lower(),
            "label_class": label_class(str(item.get("label") or "")),
        }
        for item in labels
        if str(item.get("candidate_id") or "").strip()
    }
    candidates = [
        item
        for item in (candidates_report.get("candidates") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip() in label_by_id
    ]
    ranked = sorted(candidates, key=priority_score, reverse=True)
    k = min(max(1, int(top_k)), max(1, len(ranked)))
    top = ranked[:k]
    useful_scores = []
    negative_scores = []
    neutral_scores = []
    unknown_labels = []
    rows = []
    for candidate in ranked:
        candidate_id = str(candidate.get("id") or "").strip()
        label = label_by_id[candidate_id]
        cls = str(label.get("label_class") or "unknown")
        score = priority_score(candidate)
        if cls == "useful":
            useful_scores.append(score)
        elif cls == "negative":
            negative_scores.append(score)
        elif cls == "neutral":
            neutral_scores.append(score)
        else:
            unknown_labels.append(label.get("label"))
        rows.append(
            {
                "candidate_id": candidate_id,
                "action": candidate.get("action"),
                "priority_score": round(score, 6),
                "label": label.get("label"),
                "label_class": cls,
                "reviewer": label.get("reviewer"),
                "reason": label.get("reason"),
            }
        )
    top_useful = sum(
        1
        for candidate in top
        if label_by_id[str(candidate.get("id") or "").strip()].get("label_class") == "useful"
    )
    top_negative = sum(
        1
        for candidate in top
        if label_by_id[str(candidate.get("id") or "").strip()].get("label_class") == "negative"
    )
    useful_mean = sum(useful_scores) / len(useful_scores) if useful_scores else 0.0
    negative_mean = sum(negative_scores) / len(negative_scores) if negative_scores else 0.0
    return {
        "schema": "ogcf_maintenance_review_label_eval/v1",
        "source_report_schema": candidates_report.get("schema"),
        "candidate_count": len(candidates_report.get("candidates") or []),
        "labeled_count": len(candidates),
        "useful_count": len(useful_scores),
        "negative_count": len(negative_scores),
        "neutral_count": len(neutral_scores),
        "unknown_label_count": len(unknown_labels),
        "top_k": k,
        "top_useful": top_useful,
        "top_negative": top_negative,
        "precision_at_k": round(top_useful / k, 6) if ranked else 0.0,
        "negative_at_k": round(top_negative / k, 6) if ranked else 0.0,
        "useful_mean_priority": round(useful_mean, 6),
        "negative_mean_priority": round(negative_mean, 6),
        "priority_separates_useful": useful_mean >= negative_mean if useful_scores and negative_scores else None,
        "high_priority_negative_ids": [
            row["candidate_id"]
            for row in rows
            if row["label_class"] == "negative" and float(row["priority_score"] or 0.0) >= 0.85
        ],
        "ranked": rows,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_eval(report: dict[str, Any], checks: dict[str, bool], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ogcf_maintenance_review_label_eval_report/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "evaluation": report,
        "report_only": True,
        "mutates_db": False,
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Review Label Eval",
        "",
        f"Passed: **{payload['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Evaluation", "", "```json", json.dumps(report, indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate reviewed OGCF maintenance labels against priority ranking.")
    parser.add_argument("--candidates-json", default=str(DEFAULT_CANDIDATES_JSON))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS_JSON))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-labels", type=int, default=1)
    parser.add_argument("--require-negative", action="store_true")
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    candidates_report = json.loads(Path(args.candidates_json).read_text(encoding="utf-8"))
    labels_raw = load_json_or_jsonl(Path(args.labels))
    evaluation = build_eval(candidates_report, labels_raw, top_k=args.top_k)
    has_negative = int(evaluation.get("negative_count") or 0) > 0
    checks = {
        "schema_ok": evaluation.get("schema") == "ogcf_maintenance_review_label_eval/v1",
        "report_only": evaluation.get("report_only") is True and evaluation.get("mutates_db") is False,
        "enough_labels": int(evaluation.get("labeled_count") or 0) >= int(args.min_labels),
        "has_useful_label": int(evaluation.get("useful_count") or 0) > 0,
        "negative_requirement_met": (not args.require_negative) or has_negative,
        "no_unknown_labels": int(evaluation.get("unknown_label_count") or 0) == 0,
        "no_high_priority_negative": not evaluation.get("high_priority_negative_ids"),
        "priority_separation_ok": evaluation.get("priority_separates_useful") in {True, None},
    }
    write_eval(evaluation, checks, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": all(checks.values()),
                "checks": checks,
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
