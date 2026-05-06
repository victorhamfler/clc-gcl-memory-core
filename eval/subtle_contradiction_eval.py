from __future__ import annotations

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
        "id": "push_only_when_asked",
        "expected": True,
        "old": "Agent publishing policy: the assistant may push repository updates automatically after tests pass.",
        "new": "Updated policy: the assistant pushes repository updates only when the user asks for upload.",
    },
    {
        "id": "profile_prefers_short",
        "expected": True,
        "old": "User profile: the user wants long detailed explanations by default.",
        "new": "Current preference: the user wants short direct explanations unless they ask for detail.",
    },
    {
        "id": "durable_memory_opt_in",
        "expected": True,
        "old": "Session rule: every chat turn always becomes durable memory.",
        "new": "Updated rule: chat turns become durable memory only when explicitly remembered.",
    },
    {
        "id": "api_endpoint_addition",
        "expected": False,
        "old": "Memory API should expose ask, teach, correct, and feedback endpoints.",
        "new": "Updated policy: Memory API should also expose consolidation endpoints.",
    },
    {
        "id": "evidence_addition",
        "expected": False,
        "old": "Answers should include evidence ids and confidence.",
        "new": "Current rule: answers should include evidence ids, confidence, and source context.",
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
        pipeline = init_pipeline(root, root / "subtle_contradiction.db")
        try:
            old = pipeline.ingest(case["old"], source=f"subtle/{case['id']}_old.md")
            new = pipeline.ingest(case["new"], source=f"subtle/{case['id']}_new.md")
        finally:
            pipeline.close()
    predicted = float(new["contradiction"]) >= THRESHOLD
    return {
        "id": case["id"],
        "expected": case["expected"],
        "predicted": predicted,
        "correct": predicted == case["expected"],
        "protected": new["clc_state"] == "PROTECT",
        "old": {
            "memory_id": old["memory_id"],
            "clc_state": old["clc_state"],
            "recall": old["recall"],
        },
        "new": {
            "memory_id": new["memory_id"],
            "contradiction": new["contradiction"],
            "clc_state": new["clc_state"],
            "decision_reason": new["decision_reason"],
            "recall": new["recall"],
            "gcl_action": new["gcl_action"],
        },
    }


def main() -> None:
    rows = [run_case(case) for case in CASES]
    tp = sum(1 for row in rows if row["expected"] and row["predicted"])
    tn = sum(1 for row in rows if not row["expected"] and not row["predicted"])
    fp = sum(1 for row in rows if not row["expected"] and row["predicted"])
    fn = sum(1 for row in rows if row["expected"] and not row["predicted"])
    result = {
        "ok": fp == 0 and fn == 0,
        "threshold": THRESHOLD,
        "metrics": {
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "accuracy": round((tp + tn) / max(1, len(rows)), 4),
        },
        "cases": rows,
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
