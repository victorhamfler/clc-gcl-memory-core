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
OUT_JSON = REPO_ROOT / "experiments" / "day1_answer_source_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "day1_answer_source_regression_report.md"


FIXTURES = {
    "calendar_change_policy": {
        "text": "Calendar schedule changes require manual approval before changing meeting events.",
        "source": "day1/calendar_change_policy.md",
    },
    "broad_policy_note": {
        "text": "Broad policy note: all approvals should be documented in the change log.",
        "source": "day1/broad_policy_note.md",
    },
    "github_upload_policy": {
        "text": "GitHub uploads require explicit confirmation in the current conversation.",
        "source": "day1/github_upload_policy.md",
    },
}


CASES = [
    {
        "id": "calendar_change_policy_question",
        "query": "What calendar change policy should Hermes follow?",
    },
    {
        "id": "calendar_auto_change_question",
        "query": "Can Hermes change meetings automatically?",
    },
]


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "day1_answer_source.db"
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
    ids: dict[str, str] = {}
    for ref, fixture in FIXTURES.items():
        result = pipeline.teach(
            fixture["text"],
            source=fixture["source"],
            namespace=namespace,
            agent_id="day1_answer_source_regression",
            store_session=False,
            domain="agent_memory",
            memory_type="procedure",
        )
        ids[ref] = result["memory"]["memory_id"]
    return ids


def row_ref(row: dict[str, Any]) -> str | None:
    source = str(row.get("source") or "")
    for ref, fixture in FIXTURES.items():
        if source == fixture["source"]:
            return ref
    return None


def run_case(pipeline: MemoryPipeline, namespace: str, case: dict[str, str]) -> dict[str, Any]:
    rows = pipeline.retrieve(case["query"], top_k=8, namespace=namespace, include_global=False)
    asked = pipeline.ask(
        case["query"],
        top_k=8,
        namespace=namespace,
        include_global=False,
        agent_id="day1_answer_source_regression",
        store_session=False,
    )
    evidence = asked.get("evidence") or []
    answer = str(asked.get("answer") or "")
    retrieved_top_ref = row_ref(rows[0]) if rows else None
    answer_top_ref = row_ref(evidence[0]) if evidence else None
    answer_l = answer.lower()
    passed = (
        retrieved_top_ref == "calendar_change_policy"
        and answer_top_ref == "calendar_change_policy"
        and "manual approval" in answer_l
        and ("meeting" in answer_l or "calendar" in answer_l)
        and not answer_l.startswith("relevant memory indicates: broad policy note")
    )
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": passed,
        "retrieved_top_ref": retrieved_top_ref,
        "answer_top_ref": answer_top_ref,
        "answer": answer,
        "retrieved": [
            {
                "rank": idx,
                "ref": row_ref(row),
                "score": row.get("score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "source": row.get("source"),
                "text": row.get("text"),
            }
            for idx, row in enumerate(rows, start=1)
        ],
        "evidence": [
            {
                "rank": idx,
                "ref": row_ref(row),
                "score": row.get("score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "source": row.get("source"),
                "text": row.get("text"),
            }
            for idx, row in enumerate(evidence, start=1)
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Day 1 Answer Source Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| case | pass | retrieval top | answer evidence top |",
        "| --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case['retrieved_top_ref']}` | `{case['answer_top_ref']}` |"
        )
    lines.extend(["", "## Details", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"Query: `{case['query']}`",
                "",
                f"Answer: {case['answer']}",
                "",
                "| rank | ref | score | claim-scope | answer-type | source |",
                "| ---: | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for row in case["retrieved"]:
            lines.append(
                f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['claim_scope_score']} | "
                f"{row['answer_type_score']} | `{row['source']}` |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "day1_answer_source_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            teach_fixture(pipeline, namespace)
            cases = [run_case(pipeline, namespace, case) for case in CASES]
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
