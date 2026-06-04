from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.ogcf_maintenance_review_label_eval import build_eval  # noqa: E402
from eval.ogcf_maintenance_review_queue import build_label_template, build_review_queue  # noqa: E402


OUT_REPORT = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_loop_fixture_candidates.json"
OUT_QUEUE = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_loop_queue.json"
OUT_LABELS = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_loop_labels.json"
OUT_JSON = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_loop_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "ogcf_maintenance_review_label_loop_regression_report.md"


def candidate(
    candidate_id: str,
    action: str,
    *,
    confidence: float,
    priority: float,
    candidate_ids: list[str] | None = None,
) -> dict:
    return {
        "id": candidate_id,
        "action": action,
        "recommendation": "review",
        "keeper_memory_id": f"keep_{candidate_id}",
        "candidate_memory_ids": candidate_ids or [f"cand_{candidate_id}"],
        "support": 2,
        "confidence": confidence,
        "sample_text": f"fixture sample for {candidate_id}",
        "maintenance_priority": {
            "schema": "ogcf_maintenance_priority/v1",
            "priority_score": priority,
            "report_only": True,
            "mutates_db": False,
        },
    }


def fixture_report() -> dict:
    return {
        "schema": "ogcf_maintenance_candidates/v1",
        "candidate_count": 4,
        "candidate_counts": {
            "exact_duplicate_group": 1,
            "semantic_conflict_or_update_group": 1,
            "bridge_cluster_review": 1,
            "semantic_duplicate_group": 1,
        },
        "maintenance_priority_summary": {
            "schema": "ogcf_maintenance_priority_summary/v1",
            "candidate_count": 4,
            "prioritized_candidate_count": 4,
            "readiness": "ready_for_review",
            "report_only": True,
            "mutates_db": False,
        },
        "mutates_db": False,
        "candidates": [
            candidate("exact:alpha", "exact_duplicate_group", confidence=0.98, priority=0.96),
            candidate("stale:beta", "semantic_conflict_or_update_group", confidence=0.78, priority=0.88),
            candidate("bridge:gamma", "bridge_cluster_review", confidence=0.52, priority=0.62),
            candidate("semantic:delta", "semantic_duplicate_group", confidence=0.50, priority=0.58),
        ],
    }


def fixture_labels() -> dict:
    return {
        "schema": "ogcf_maintenance_review_labels/v1",
        "labels": [
            {
                "candidate_id": "exact:alpha",
                "label": "useful_review",
                "reviewer": "regression",
                "reason": "duplicate cleanup preserves information",
            },
            {
                "candidate_id": "stale:beta",
                "label": "useful_review",
                "reviewer": "regression",
                "reason": "temporal update conflict needs review",
            },
            {
                "candidate_id": "bridge:gamma",
                "label": "needs_more_evidence",
                "reviewer": "regression",
                "reason": "bridge cluster pressure is plausible but not actionable",
            },
            {
                "candidate_id": "semantic:delta",
                "label": "noisy_review",
                "reviewer": "regression",
                "reason": "low-priority paraphrase is not useful maintenance work",
            },
        ],
        "report_only": True,
        "mutates_db": False,
    }


def main() -> int:
    report = fixture_report()
    labels = fixture_labels()
    queue = build_review_queue(report, source_path=str(OUT_REPORT))
    template = build_label_template(queue)
    evaluation = build_eval(report, labels, top_k=3)
    checks = {
        "queue_schema_ok": queue.get("schema") == "ogcf_maintenance_review_queue/v1",
        "queue_sorted_by_priority": [item["candidate_id"] for item in queue["items"][:2]] == ["exact:alpha", "stale:beta"],
        "template_schema_ok": template.get("schema") == "ogcf_maintenance_review_labels/v1",
        "template_has_all_candidates": len(template.get("labels") or []) == len(report["candidates"]),
        "eval_schema_ok": evaluation.get("schema") == "ogcf_maintenance_review_label_eval/v1",
        "eval_has_useful_and_negative": evaluation.get("useful_count") == 2 and evaluation.get("negative_count") == 1,
        "top_precision_good": float(evaluation.get("precision_at_k") or 0.0) >= 0.66,
        "priority_separates_useful": evaluation.get("priority_separates_useful") is True,
        "no_high_priority_negative": not evaluation.get("high_priority_negative_ids"),
        "report_only": queue.get("report_only") is True
        and evaluation.get("report_only") is True
        and report.get("mutates_db") is False,
    }
    result = {
        "schema": "ogcf_maintenance_review_label_loop_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "queue": queue,
        "label_template": template,
        "labels": labels,
        "evaluation": evaluation,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_QUEUE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    OUT_LABELS.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# OGCF Maintenance Review Label Loop Regression",
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
