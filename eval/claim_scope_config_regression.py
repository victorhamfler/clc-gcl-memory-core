from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_config_regression_report.md"


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "claim_scope_config.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        claim_scope_config={
            "slot_aliases": {
                "policy": ["manual", "approval", "schedule", "change", "changes"],
                "color": ["blue", "green"],
            },
            "excluded_terms": {
                "policy": ["color"],
            },
        },
    )


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows = report["retrieved"]
    lines = [
        "# Claim Scope Config Regression",
        "",
        f"Passed: **{report['passed']}**",
        "",
        "## Ranking",
        "",
        "| rank | source | score | claim_scope | text |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(rows, start=1):
        text = str(row["text"]).replace("|", "\\|")
        lines.append(
            f"| {idx} | `{row['source']}` | {row['score']:.6f} | "
            f"{row['claim_scope_score']:.6f} | {text} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    query = "What calendar policy should Hermes use?"
    namespace = "claim_scope_config_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            target = pipeline.teach(
                "Hermes calendar policy should use manual approval for schedule changes.",
                source="agent_memory_v3/calendar_policy.md",
                namespace=namespace,
                agent_id="claim_scope_config_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="procedure",
            )["memory"]["memory_id"]
            stale = pipeline.teach(
                "Hermes calendar color should be blue.",
                source="agent_memory_v1/calendar_color.md",
                namespace=namespace,
                agent_id="claim_scope_config_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )["memory"]["memory_id"]
            current_color = pipeline.correct(
                "Hermes calendar color should be green, not blue.",
                target_memory_ids=[stale],
                target_query="What calendar color should Hermes use?",
                top_k=6,
                source="agent_memory_v2/calendar_color.md",
                namespace=namespace,
                agent_id="claim_scope_config_regression",
                store_session=False,
                relation_type="corrects",
                domain="agent_memory",
                memory_type="semantic_note",
            )["correction_memory"]["memory_id"]
            rows = pipeline.retrieve(query, top_k=6, namespace=namespace, include_global=False)
        finally:
            pipeline.close()

    row_by_id = {row["memory_id"]: row for row in rows}
    target_row = row_by_id[target]
    color_row = row_by_id[current_color]
    target_rank = rows.index(target_row) + 1
    color_rank = rows.index(color_row) + 1
    passed = (
        target_rank < color_rank
        and target_row["claim_scope_score"] >= 0.5
        and color_row["claim_scope_score"] < target_row["claim_scope_score"]
    )
    report = {
        "passed": passed,
        "query": query,
        "target_rank": target_rank,
        "color_correction_rank": color_rank,
        "target_claim_scope_score": target_row["claim_scope_score"],
        "color_correction_claim_scope_score": color_row["claim_scope_score"],
        "retrieved": [
            {
                "memory_id": row["memory_id"],
                "source": row["source"],
                "score": row["score"],
                "claim_scope_score": row["claim_scope_score"],
                "text": row["text"],
            }
            for row in rows
        ],
    }
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
