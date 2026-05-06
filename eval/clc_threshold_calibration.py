from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
BASE_THRESHOLDS = {
    "new": 1.5,
    "recall_low": 0.45,
    "recall_mid": 0.65,
    "recall_high": 0.82,
    "contradiction": 0.75,
    "domain_shift": 0.60,
    "focus": 0.68,
    "information_gain": 0.45,
}


SEQUENCE = [
    {
        "id": "new_domain",
        "text": "Agent memory should store durable user profile facts with evidence ids and source labels.",
        "source": "calibration/agent_memory_base.md",
        "expected": {"SPLIT_DOMAIN"},
    },
    {
        "id": "near_duplicate",
        "text": "Agent memory should store durable user profile facts with evidence ids, source labels, and confidence.",
        "source": "calibration/agent_memory_near.md",
        "expected": {"RECALL", "LIGHT_UPDATE", "FOCUS"},
    },
    {
        "id": "correction",
        "text": "Updated policy: the assistant pushes repository updates only when the user asks for upload.",
        "source": "calibration/agent_memory_correction.md",
        "expected": {"PROTECT"},
    },
    {
        "id": "new_mechanism",
        "text": "CSD diagnostics should compare novelty density against local semantic geometry before labeling surprise.",
        "source": "calibration/csd_new.md",
        "expected": {"SPLIT_DOMAIN", "EXPLORE"},
    },
    {
        "id": "gcl_detail",
        "text": "G-CL should track anchor drift, curvature, orthogonal drift, and effective dimension during updates.",
        "source": "calibration/gcl_detail.md",
        "expected": {"SPLIT_DOMAIN", "EXPLORE", "FOCUS"},
    },
]


def init_pipeline(root: Path, db_path: Path, thresholds: dict[str, float]) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(
        root=root,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        clc_thresholds=thresholds,
    )


def run_profile(thresholds: dict[str, float]) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "clc_calibration.db", thresholds)
        rows = []
        try:
            pipeline.ingest(
                "Old publishing policy: the assistant may push repository updates automatically after tests pass.",
                source="calibration/old_policy.md",
            )
            for case in SEQUENCE:
                item = pipeline.ingest(case["text"], source=case["source"])
                rows.append(
                    {
                        "id": case["id"],
                        "expected": sorted(case["expected"]),
                        "state": item["clc_state"],
                        "correct": item["clc_state"] in case["expected"],
                        "decision_reason": item["decision_reason"],
                        "recall": item["recall"],
                        "csd_score": item["csd_score"],
                        "contradiction": item["contradiction"],
                        "focus": item["focus"],
                    }
                )
        finally:
            pipeline.close()
    correct = sum(1 for row in rows if row["correct"])
    focus_count = sum(1 for row in rows if row["state"] == "FOCUS")
    protect_count = sum(1 for row in rows if row["state"] == "PROTECT")
    score = correct - max(0, focus_count - 2) * 0.2 + protect_count * 0.1
    return {
        "thresholds": thresholds,
        "score": round(score, 4),
        "correct": correct,
        "total": len(rows),
        "focus_count": focus_count,
        "protect_count": protect_count,
        "rows": rows,
    }


def main() -> None:
    profiles = [BASE_THRESHOLDS]
    for new, focus, information_gain in itertools.product((1.35, 1.5, 1.65), (0.64, 0.68, 0.72), (0.40, 0.45, 0.50)):
        candidate = dict(BASE_THRESHOLDS)
        candidate["new"] = new
        candidate["focus"] = focus
        candidate["information_gain"] = information_gain
        profiles.append(candidate)
    results = [run_profile(profile) for profile in profiles]
    results.sort(key=lambda row: (row["score"], row["correct"], -row["focus_count"]), reverse=True)
    best = results[0]
    baseline = run_profile(BASE_THRESHOLDS)
    result = {
        "ok": best["correct"] >= baseline["correct"],
        "baseline": baseline,
        "best": best,
        "top_profiles": results[:5],
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
