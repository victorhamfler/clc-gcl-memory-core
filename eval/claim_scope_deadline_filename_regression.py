from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_deadline_filename_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_deadline_filename_regression_report.md"


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "claim_scope_deadline_filename.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    config = load_config(ROOT)
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=config.get("retrieval_weights") or {},
        claim_scope_config=config.get("claim_scope") or {},
        answer_type_config=config.get("answer_type") or {},
    )


def teach_fixture(pipeline: MemoryPipeline, namespace: str) -> dict[str, str]:
    fixtures = {
        "deadline": {
            "text": "The selector feedback report is due Friday.",
            "source": "sample/feedback_report_deadline.md",
        },
        "filename": {
            "text": "Selector feedback report filename should be selector_feedback_report.md.",
            "source": "sample/feedback_report_filename.md",
        },
        "owner": {
            "text": "Mina owns the selector feedback report draft.",
            "source": "sample/feedback_report_owner.md",
        },
    }
    ids: dict[str, str] = {}
    for ref, fixture in fixtures.items():
        result = pipeline.teach(
            fixture["text"],
            source=fixture["source"],
            namespace=namespace,
            agent_id="claim_scope_deadline_filename_regression",
            store_session=False,
            domain="agent_memory",
            memory_type="semantic_note",
        )
        ids[ref] = result["memory"]["memory_id"]
    return ids


def rank_for(rows: list[dict[str, Any]], memory_id: str) -> int | None:
    for idx, row in enumerate(rows, start=1):
        if row.get("memory_id") == memory_id:
            return idx
    return None


def ref_for_memory(ids: dict[str, str], memory_id: str | None) -> str | None:
    for ref, mid in ids.items():
        if mid == memory_id:
            return ref
    return None


def run_case(pipeline: MemoryPipeline, namespace: str, ids: dict[str, str], query: str) -> dict[str, Any]:
    rows = pipeline.retrieve(query, top_k=6, namespace=namespace, include_global=False)
    by_id = {row["memory_id"]: row for row in rows}
    deadline_row = by_id.get(ids["deadline"])
    filename_row = by_id.get(ids["filename"])
    owner_row = by_id.get(ids["owner"])
    deadline_rank = rank_for(rows, ids["deadline"])
    filename_rank = rank_for(rows, ids["filename"])
    owner_rank = rank_for(rows, ids["owner"])
    filename_claim = None if filename_row is None else float(filename_row.get("claim_scope_score") or 0.0)
    deadline_claim = None if deadline_row is None else float(deadline_row.get("claim_scope_score") or 0.0)
    owner_claim = None if owner_row is None else float(owner_row.get("claim_scope_score") or 0.0)
    passed = (
        deadline_rank == 1
        and filename_rank is not None
        and owner_rank is not None
        and deadline_rank < filename_rank
        and deadline_rank < owner_rank
        and deadline_claim is not None
        and deadline_claim >= 0.5
        and filename_claim == 0.0
        and owner_claim == 0.0
    )
    return {
        "query": query,
        "passed": passed,
        "deadline_rank": deadline_rank,
        "filename_rank": filename_rank,
        "owner_rank": owner_rank,
        "deadline_claim_scope": deadline_claim,
        "filename_claim_scope": filename_claim,
        "owner_claim_scope": owner_claim,
        "retrieved": [
            {
                "rank": idx,
                "ref": ref_for_memory(ids, row.get("memory_id")),
                "source": row.get("source"),
                "score": row.get("score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "text": row.get("text"),
            }
            for idx, row in enumerate(rows, start=1)
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Claim Scope Deadline/Filename Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Query: `{report['query']}`",
        f"Deadline rank: `{report['deadline_rank']}` claim-scope `{report['deadline_claim_scope']}`",
        f"Filename rank: `{report['filename_rank']}` claim-scope `{report['filename_claim_scope']}`",
        f"Owner rank: `{report['owner_rank']}` claim-scope `{report['owner_claim_scope']}`",
        "",
        "| rank | ref | score | claim-scope | answer-type | source | text |",
        "| ---: | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report["retrieved"]:
        text = str(row.get("text") or "").replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['claim_scope_score']} | "
            f"{row['answer_type_score']} | `{row['source']}` | {text} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "claim_scope_deadline_filename_regression"
    query = "What deadline should Hermes remember?"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            ids = teach_fixture(pipeline, namespace)
            report = run_case(pipeline, namespace, ids, query)
        finally:
            pipeline.close()

    report["ok"] = bool(report["passed"])
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "deadline_rank": report["deadline_rank"],
                "filename_rank": report["filename_rank"],
                "filename_claim_scope": report["filename_claim_scope"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
