from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_candidates import build_report  # noqa: E402
from eval.ogcf_projector_graph_maintenance_regression import setup_db  # noqa: E402


DB_PATH = REPO_ROOT / "experiments" / "ogcf_maintenance_priority_outcome_fixture.db"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_priority_outcome_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_priority_outcome_regression_report.md"


USEFUL_ACTIONS = {
    "exact_duplicate_group",
    "semantic_duplicate_group",
    "semantic_conflict_or_update_group",
    "stale_version_candidate",
}


def label_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    action = str(candidate.get("action") or "")
    useful = action in USEFUL_ACTIONS
    return {
        "candidate_id": str(candidate.get("id") or ""),
        "action": action,
        "label": "useful_review" if useful else "needs_more_evidence",
        "useful": useful,
        "reason": "controlled_fixture_label",
    }


def priority_score(candidate: dict[str, Any]) -> float:
    return float((candidate.get("maintenance_priority") or {}).get("priority_score") or candidate.get("confidence") or 0.0)


def evaluate_priority(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    labels = {label["candidate_id"]: label for label in (label_candidate(candidate) for candidate in candidates)}
    ranked = sorted(candidates, key=priority_score, reverse=True)
    useful_total = sum(1 for label in labels.values() if label["useful"])
    top_k = min(3, len(ranked))
    top = ranked[:top_k]
    top_useful = sum(1 for candidate in top if labels.get(str(candidate.get("id") or ""), {}).get("useful"))
    useful_scores = [
        priority_score(candidate)
        for candidate in ranked
        if labels.get(str(candidate.get("id") or ""), {}).get("useful")
    ]
    other_scores = [
        priority_score(candidate)
        for candidate in ranked
        if not labels.get(str(candidate.get("id") or ""), {}).get("useful")
    ]
    return {
        "schema": "ogcf_maintenance_priority_outcome_eval/v1",
        "candidate_count": len(candidates),
        "useful_total": useful_total,
        "top_k": top_k,
        "top_useful": top_useful,
        "precision_at_k": round(top_useful / max(1, top_k), 6),
        "useful_mean_priority": round(sum(useful_scores) / max(1, len(useful_scores)), 6),
        "other_mean_priority": round(sum(other_scores) / max(1, len(other_scores)), 6),
        "ranked": [
            {
                "candidate_id": str(candidate.get("id") or ""),
                "action": candidate.get("action"),
                "priority_score": priority_score(candidate),
                "label": labels.get(str(candidate.get("id") or ""), {}).get("label"),
                "useful": labels.get(str(candidate.get("id") or ""), {}).get("useful"),
            }
            for candidate in ranked
        ],
        "labels": list(labels.values()),
        "report_only": True,
        "mutates_db": False,
    }


def main() -> int:
    setup_db(DB_PATH)
    report = build_report(
        DB_PATH,
        n_clusters=4,
        rank_k=2,
        neighbors=4,
        random_baselines=2,
        semantic_threshold=0.90,
        jaccard_min=0.30,
        stale_jaccard_min=0.35,
        skip_geometry=False,
    )
    candidates = report.get("candidates") or []
    evaluation = evaluate_priority(candidates)
    priority_summary = report.get("maintenance_priority_summary") or {}
    checks = {
        "schema_ok": evaluation.get("schema") == "ogcf_maintenance_priority_outcome_eval/v1",
        "report_only": evaluation.get("report_only") is True and evaluation.get("mutates_db") is False,
        "has_prioritized_candidates": int(priority_summary.get("prioritized_candidate_count") or 0) >= 3,
        "has_useful_labels": int(evaluation.get("useful_total") or 0) >= 2,
        "top_precision_good": float(evaluation.get("precision_at_k") or 0.0) >= 0.66,
        "useful_priority_not_below_other": float(evaluation.get("useful_mean_priority") or 0.0)
        >= float(evaluation.get("other_mean_priority") or 0.0),
        "top_ids_match_summary": bool(priority_summary.get("top_candidate_ids"))
        and evaluation["ranked"][0]["candidate_id"] in priority_summary.get("top_candidate_ids"),
    }
    result = {
        "schema": "ogcf_maintenance_priority_outcome_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "maintenance_priority_summary": priority_summary,
        "evaluation": evaluation,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "mutates_db": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Priority Outcome Regression",
        "",
        f"Passed: **{result['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Evaluation", "", "```json", json.dumps(evaluation, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
