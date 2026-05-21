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
OUT_JSON = REPO_ROOT / "experiments" / "answer_type_relation_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_type_relation_regression_report.md"


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "answer_type_relation.db"
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
    rows = {
        "owner_assignment": {
            "text": "Mina has the assignment.",
            "source": "sample/report_assignment.md",
        },
        "owner_note": {
            "text": "Deadline owner note: Mina owns the report draft.",
            "source": "sample/deadline_owner.md",
        },
        "deadline_due": {
            "text": "The report is due Friday.",
            "source": "sample/report_deadline.md",
        },
        "filename": {
            "text": "Selector feedback report filename should be feedback_gate_report.md.",
            "source": "sample/report_filename.md",
        },
    }
    ids: dict[str, str] = {}
    for ref, row in rows.items():
        result = pipeline.teach(
            row["text"],
            source=row["source"],
            namespace=namespace,
            agent_id="answer_type_relation_regression",
            store_session=False,
            domain="agent_memory",
            memory_type="semantic_note",
        )
        ids[ref] = result["memory"]["memory_id"]
    return ids


def run_case(
    pipeline: MemoryPipeline,
    namespace: str,
    ids: dict[str, str],
    *,
    case_id: str,
    query: str,
    target_ref: str,
    suppressed_refs: tuple[str, ...] = (),
    acceptable_target_refs: tuple[str, ...] = (),
) -> dict[str, Any]:
    rows = pipeline.retrieve(query, top_k=8, namespace=namespace, include_global=False)
    by_id = {row["memory_id"]: row for row in rows}
    acceptable_refs = acceptable_target_refs or (target_ref,)
    target_candidates = [
        {
            "ref": ref,
            "rank": rank_for(rows, ids[ref]),
            "row": by_id.get(ids[ref]),
        }
        for ref in acceptable_refs
    ]
    present_targets = [item for item in target_candidates if item["rank"] is not None]
    best_target = min(present_targets, key=lambda item: item["rank"]) if present_targets else None
    target_rank = None if best_target is None else best_target["rank"]
    target_row = None if best_target is None else best_target["row"]
    suppressed = []
    for ref in suppressed_refs:
        memory_id = ids[ref]
        row = by_id.get(memory_id)
        suppressed.append(
            {
                "ref": ref,
                "rank": rank_for(rows, memory_id),
                "answer_type_score": None if row is None else row.get("answer_type_score"),
                "score": None if row is None else row.get("score"),
            }
        )
    top_row = rows[0] if rows else None
    passed = target_rank == 1
    for item in suppressed:
        if target_rank is None or (item["rank"] is not None and item["rank"] <= target_rank):
            passed = False
    return {
        "case_id": case_id,
        "query": query,
        "passed": passed,
        "target_ref": target_ref,
        "acceptable_target_refs": list(acceptable_refs),
        "best_target_ref": None if best_target is None else best_target["ref"],
        "target_rank": target_rank,
        "target_score": None if target_row is None else target_row.get("score"),
        "target_answer_type_score": None if target_row is None else target_row.get("answer_type_score"),
        "top_ref": ref_for_memory(ids, top_row.get("memory_id") if top_row else None),
        "suppressed": suppressed,
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


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Answer Type Relation Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| case | pass | target | best target | target rank | target answer-type | suppressed |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        suppressed = ", ".join(
            f"{item['ref']} rank={item['rank']} answer={item['answer_type_score']}"
            for item in case["suppressed"]
        )
        lines.append(
            f"| `{case['case_id']}` | `{case['passed']}` | `{case['target_ref']}` | "
            f"`{case['best_target_ref']}` | {case['target_rank']} | {case['target_answer_type_score']} | "
            f"{suppressed or 'none'} |"
        )
    lines.extend(["", "## Case Details", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"Query: `{case['query']}`",
                "",
                "| rank | ref | score | claim-scope | answer-type | source | text |",
                "| ---: | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for row in case["retrieved"]:
            text = str(row.get("text") or "").replace("|", "\\|")
            lines.append(
                f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['claim_scope_score']} | "
                f"{row['answer_type_score']} | `{row['source']}` | {text} |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "answer_type_relation_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            ids = teach_fixture(pipeline, namespace)
            cases = [
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="owner_question_prefers_assignment",
                    query="Who is the owner of the report?",
                    target_ref="owner_assignment",
                    acceptable_target_refs=("owner_assignment", "owner_note"),
                    suppressed_refs=("deadline_due",),
                ),
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="deadline_question_prefers_due_date",
                    query="When is the selector feedback report due?",
                    target_ref="deadline_due",
                    suppressed_refs=("owner_assignment", "owner_note"),
                ),
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="deadline_query_suppresses_owner_note",
                    query="What deadline should Hermes remember for the feedback report?",
                    target_ref="deadline_due",
                    suppressed_refs=("owner_note",),
                ),
            ]
        finally:
            pipeline.close()

    report = {
        "ok": all(case["passed"] for case in cases),
        "case_count": len(cases),
        "cases": cases,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "case_count": report["case_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
