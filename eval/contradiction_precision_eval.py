from __future__ import annotations

import argparse
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
THRESHOLD = 0.75


CASES = [
    {
        "id": "github_push_policy",
        "expected": True,
        "old": "Old policy: the assistant may push documentation updates to GitHub automatically after tests pass.",
        "new": "Correction: the assistant must not push documentation updates to GitHub automatically after tests pass.",
    },
    {
        "id": "durable_session_turns",
        "expected": True,
        "old": "Old memory rule: session turns should always become durable memories automatically.",
        "new": "Correction: session turns should not always become durable memories automatically.",
    },
    {
        "id": "embedding_reuse",
        "expected": True,
        "old": "Old geometry rule: OpenClaw vectors may be reused after changing embedding dimensions.",
        "new": "Correction: OpenClaw vectors must not be reused after changing embedding dimensions.",
    },
    {
        "id": "automatic_planning",
        "expected": True,
        "old": "Old planning rule: weekly planning summaries should always be created automatically.",
        "new": "Correction: weekly planning summaries should not always be created automatically.",
    },
    {
        "id": "add_confidence_scores",
        "expected": False,
        "old": "Agent memory should store evidence ids for every answer.",
        "new": "Correction: Agent memory should also store confidence scores for every answer.",
    },
    {
        "id": "gcl_dimension_addition",
        "expected": False,
        "old": "G-CL anchor drift should track curvature and orthogonal drift.",
        "new": "Correction note: G-CL anchor drift should also report effective dimension.",
    },
    {
        "id": "csd_documentation_examples",
        "expected": False,
        "old": "CSD diagnostics should normalize raw drift before calling novelty high.",
        "new": "Correction note: CSD documentation should include examples for normalized drift.",
    },
    {
        "id": "openclaw_detail_addition",
        "expected": False,
        "old": "OpenClaw geometry controller should keep the LCM database as the source of truth.",
        "new": "Correction: OpenClaw geometry controller should also record branch state snapshots.",
    },
]


def init_pipeline(root: Path, db_path: Path) -> MemoryPipeline:
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = init_pipeline(root, root / "contradiction_case.db")
        try:
            old = pipeline.ingest(case["old"], source=f"contradiction_precision/{case['id']}_old.md")
            new = pipeline.ingest(case["new"], source=f"contradiction_precision/{case['id']}_new.md")
            stats = pipeline.db.stats()
        finally:
            pipeline.close()
    predicted = float(new["contradiction"]) >= THRESHOLD
    protected = new["clc_state"] == "PROTECT" and new["gcl_action"] == "no_anchor_update"
    return {
        "id": case["id"],
        "expected": bool(case["expected"]),
        "predicted": predicted,
        "correct": predicted == bool(case["expected"]),
        "protected": protected,
        "old": {
            "clc_state": old["clc_state"],
            "recall": old["recall"],
            "csd_score": old["csd_score"],
            "domain_name": old["domain_name"],
        },
        "new": {
            "contradiction": new["contradiction"],
            "clc_state": new["clc_state"],
            "decision_reason": new["decision_reason"],
            "recall": new["recall"],
            "csd_score": new["csd_score"],
            "focus": new["focus"],
            "gcl_action": new["gcl_action"],
            "anchor_update_strength": new["anchor_update_strength"],
            "domain_name": new["domain_name"],
        },
        "stats": stats,
    }


def confusion(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["expected"] and row["predicted"])
    tn = sum(1 for row in rows if not row["expected"] and not row["predicted"])
    fp = sum(1 for row in rows if not row["expected"] and row["predicted"])
    fn = sum(1 for row in rows if row["expected"] and not row["predicted"])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    specificity = tn / max(1, tn + fp)
    accuracy = (tp + tn) / max(1, len(rows))
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "accuracy": round(accuracy, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CSD contradiction precision and false positive behavior")
    parser.add_argument("--min-precision", type=float, default=0.90)
    parser.add_argument("--min-recall", type=float, default=0.75)
    args = parser.parse_args()

    rows = [run_case(case) for case in CASES]
    metrics = confusion(rows)
    protected_true = sum(1 for row in rows if row["expected"] and row["protected"])
    true_count = sum(1 for row in rows if row["expected"])
    false_protected = sum(1 for row in rows if not row["expected"] and row["protected"])
    result = {
        "ok": (
            metrics["precision"] >= args.min_precision
            and metrics["recall"] >= args.min_recall
            and false_protected == 0
            and protected_true == true_count
        ),
        "threshold": THRESHOLD,
        "metrics": metrics,
        "protected_true": protected_true,
        "true_count": true_count,
        "false_protected": false_protected,
        "cases": rows,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
