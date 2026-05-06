from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.memory_training_run import run


def main() -> None:
    with TemporaryDirectory() as tmp:
        payload = run(
            Path(tmp) / "memory_training_run_smoke.db",
            fast_hash=True,
            top_k=4,
            feedback_repeats=2,
        )

    summaries = payload["summaries"]
    report = payload["report"]
    assert payload["ok"] is True
    assert payload["imports"]["v1"]["stored"] > 0
    assert payload["imports"]["v2"]["stored"] > 0
    assert payload["manifest_relations"]["relations_added"] > 0
    assert payload["feedback_applied_count"] > 0
    assert summaries["after_feedback"]["mean_term_score"] >= 0.8
    assert summaries["after_feedback"]["mean_source_score"] >= 0.6
    assert "after_feedback" in report["training_scores"]
    assert report["recommendations"]
    assert all("id" in item for item in report["weak_final_cases"])

    print(
        json.dumps(
            {
                "ok": True,
                "training_scores": report["training_scores"],
                "deltas": report["deltas"],
                "weak_final_case_ids": [item["id"] for item in report["weak_final_cases"]],
                "recommendations": report["recommendations"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
