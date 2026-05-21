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
from core.runtime import init_db  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "approval_log_ambiguity_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "approval_log_ambiguity_regression_report.md"


FIXTURES = {
    "broad_policy_note": {
        "text": "Broad policy note: all approvals should be documented in the change log.",
        "source": "policy/broad_policy_note.md",
        "memory_type": "procedure",
    },
    "approval_archive_note": {
        "text": "Approval archive entries are stored for audit history after the actual decision has been made.",
        "source": "pressure/approval_archive_note.md",
        "memory_type": "semantic_note",
    },
    "calendar_change_policy": {
        "text": "Calendar schedule changes require manual approval before changing meeting events.",
        "source": "policy/calendar_change_policy.md",
        "memory_type": "procedure",
    },
    "weather_correction": {
        "text": "Correction: The weather radar method uses AccuWeather URL format for Sant Carles de la Rapita, with text extraction fallback when canvas images are unreadable.",
        "source": "correction:approval_log_ambiguity_regression",
        "memory_type": "semantic_note",
    },
}


CASES = [
    {
        "id": "general_approvals_logged",
        "query": "Where should general approvals be logged?",
        "expected_ref": "broad_policy_note",
        "required_terms": ("documented", "change log"),
        "forbidden_terms": ("audit history", "calendar schedule"),
    },
    {
        "id": "overall_policy_recorded",
        "query": "For the overall policy note, how are changes recorded?",
        "expected_ref": "broad_policy_note",
        "required_terms": ("documented", "change log"),
        "forbidden_terms": ("audit history", "calendar schedule"),
    },
    {
        "id": "approval_archive_history",
        "query": "Where are approval archive entries stored for audit history?",
        "expected_ref": "approval_archive_note",
        "required_terms": ("audit history",),
        "forbidden_terms": ("change log", "calendar schedule"),
    },
]


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "approval_log_ambiguity.db"
    init_db(ROOT, db_path)
    config = load_config(ROOT)
    return MemoryPipeline(
        ROOT,
        db_path,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights=config.get("retrieval_weights") or {},
        claim_scope_config=config.get("claim_scope") or {},
        answer_type_config=config.get("answer_type") or {},
    )


def ref_for_row(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    source = str(row.get("source") or "")
    for ref, fixture in FIXTURES.items():
        if source == fixture["source"]:
            return ref
    return None


def run_case(pipeline: MemoryPipeline, namespace: str, case: dict[str, Any]) -> dict[str, Any]:
    rows = pipeline.retrieve(case["query"], top_k=8, namespace=namespace, include_global=False)
    asked = pipeline.ask(case["query"], top_k=8, namespace=namespace, include_global=False, store_session=False)
    evidence = asked.get("evidence") or []
    answer = str(asked.get("answer") or "")
    answer_l = answer.lower()
    retrieval_top_ref = ref_for_row(rows[0]) if rows else None
    answer_top_ref = ref_for_row(evidence[0]) if evidence else None
    missing_terms = [term for term in case["required_terms"] if term.lower() not in answer_l]
    forbidden_hits = [term for term in case["forbidden_terms"] if term.lower() in answer_l]
    passed = (
        retrieval_top_ref == case["expected_ref"]
        and answer_top_ref == case["expected_ref"]
        and not missing_terms
        and not forbidden_hits
    )
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": passed,
        "expected_ref": case["expected_ref"],
        "retrieval_top_ref": retrieval_top_ref,
        "answer_top_ref": answer_top_ref,
        "missing_terms": missing_terms,
        "forbidden_hits": forbidden_hits,
        "answer": answer,
        "retrieved": [
            {
                "rank": idx,
                "ref": ref_for_row(row),
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
                "ref": ref_for_row(row),
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
        "# Approval Log Ambiguity Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| case | pass | expected | retrieval top | answer top | missing | forbidden |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case['expected_ref']}` | "
            f"`{case['retrieval_top_ref']}` | `{case['answer_top_ref']}` | "
            f"`{case['missing_terms']}` | `{case['forbidden_hits']}` |"
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
                "| rank | ref | score | answer-type | source |",
                "| ---: | --- | ---: | ---: | --- |",
            ]
        )
        for row in case["retrieved"][:5]:
            lines.append(
                f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['answer_type_score']} | `{row['source']}` |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "approval_log_ambiguity_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            for ref, fixture in FIXTURES.items():
                pipeline.teach(
                    fixture["text"],
                    source=fixture["source"],
                    namespace=namespace,
                    agent_id="approval_log_ambiguity_regression",
                    store_session=False,
                    domain="agent_memory",
                    memory_type=fixture["memory_type"],
                )
            cases = [run_case(pipeline, namespace, case) for case in CASES]
        finally:
            pipeline.close()

    report = {"ok": all(case["passed"] for case in cases), "case_count": len(cases), "cases": cases}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "case_count": report["case_count"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
