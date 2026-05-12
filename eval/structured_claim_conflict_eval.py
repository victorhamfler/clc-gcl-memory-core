from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


SCHEMA_PATH = ROOT / "storage" / "schema.sql"


CASES = [
    {
        "id": "agent_name",
        "old": "Agent name is NovaDesk.",
        "new": "Correction: the current agent name is LoomGuide, not NovaDesk.",
        "expect_protect": True,
    },
    {
        "id": "github_policy",
        "old": "GitHub uploads may happen automatically after documentation updates.",
        "new": "Current policy: GitHub uploads happen only when Mira explicitly asks; the assistant must not push automatically.",
        "expect_protect": True,
    },
    {
        "id": "owner_change",
        "old": "Atlas Loom owner is Mira.",
        "new": "Correction: Atlas Loom owner is Victor, not Mira.",
        "expect_protect": True,
    },
    {
        "id": "additive_policy_detail",
        "old": "Current policy: GitHub uploads happen only when Mira explicitly asks.",
        "new": "Current policy also includes reporting local file paths before upload.",
        "expect_protect": False,
    },
]


def run_case(case: dict) -> dict:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / f"{case['id']}.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()

        pipeline = MemoryPipeline(root=root, db_path=db_path, embedding_config={"backend": "hash", "dim": 128})
        try:
            old = pipeline.ingest(case["old"], source=f"structured_claims/{case['id']}_old.md")
            new = pipeline.ingest(case["new"], source=f"structured_claims/{case['id']}_new.md")
        finally:
            pipeline.close()
    return {
        "id": case["id"],
        "old_state": old["clc_state"],
        "new_state": new["clc_state"],
        "contradiction": new["contradiction"],
        "ok": (new["clc_state"] == "PROTECT") if case["expect_protect"] else (new["clc_state"] != "PROTECT"),
    }


def main() -> None:
    results = [run_case(case) for case in CASES]
    checks = {
        "all_cases_pass": all(item["ok"] for item in results),
        "structured_conflicts_protected": all(
            item["new_state"] == "PROTECT" and item["contradiction"] >= 0.75
            for item in results
            if item["id"] in {"agent_name", "github_policy", "owner_change"}
        ),
        "additive_detail_not_protected": next(item for item in results if item["id"] == "additive_policy_detail")["new_state"]
        != "PROTECT",
    }
    assert all(checks.values()), checks
    print(json.dumps({"ok": True, "checks": checks, "results": results}, indent=2))


if __name__ == "__main__":
    main()
