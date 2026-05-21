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


OUT_JSON = REPO_ROOT / "experiments" / "repo_publish_permission_ambiguity_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "repo_publish_permission_ambiguity_regression_report.md"


FIXTURES = {
    "github_upload_policy": {
        "text": "GitHub uploads require explicit confirmation in the current conversation before any upload action.",
        "source": "policy/github_upload_policy.md",
        "memory_type": "procedure",
    },
    "github_upload_filename": {
        "text": "GitHub upload report filename should be github_upload_report.md.",
        "source": "policy/github_upload_filename.md",
        "memory_type": "semantic_note",
    },
    "repo_publish_draft": {
        "text": "Repository publish drafts describe release notes, but drafts are not upload permission.",
        "source": "pressure/repo_publish_draft.md",
        "memory_type": "semantic_note",
    },
    "report_template_note": {
        "text": "Weekly status reports use a separate template named weekly_status_template.md.",
        "source": "pressure/report_template_note.md",
        "memory_type": "semantic_note",
    },
}


CASES = [
    {
        "id": "repo_publish_report_filename_and_permission",
        "query": "For a repo publish report, give the report filename and the upload permission rule.",
        "expected_refs": ("github_upload_filename", "github_upload_policy"),
        "required_terms": ("github_upload_report.md", "explicit confirmation"),
        "forbidden_terms": ("weekly_status_template.md", "not upload permission"),
    },
    {
        "id": "repo_publish_permission_only",
        "query": "Before publishing something to the repo, what permission does Hermes need?",
        "expected_refs": ("github_upload_policy",),
        "required_terms": ("explicit confirmation",),
        "forbidden_terms": ("not upload permission", "weekly_status_template.md"),
    },
    {
        "id": "github_report_filename_only",
        "query": "What GitHub upload report filename should be used?",
        "expected_refs": ("github_upload_filename",),
        "required_terms": ("github_upload_report.md",),
        "forbidden_terms": ("explicit confirmation", "not upload permission"),
    },
]


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "repo_publish_permission_ambiguity.db"
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
    retrieval_refs = [ref_for_row(row) for row in rows]
    evidence_refs = [ref_for_row(row) for row in evidence]
    missing_evidence = [ref for ref in case["expected_refs"] if ref not in evidence_refs[:4]]
    missing_answer_terms = [term for term in case["required_terms"] if term.lower() not in answer_l]
    forbidden_hits = [term for term in case["forbidden_terms"] if term.lower() in answer_l]
    passed = not missing_evidence and not missing_answer_terms and not forbidden_hits
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": passed,
        "expected_refs": case["expected_refs"],
        "retrieval_refs": retrieval_refs[:6],
        "evidence_refs": evidence_refs[:6],
        "missing_evidence": missing_evidence,
        "missing_answer_terms": missing_answer_terms,
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
        "# Repo Publish Permission Ambiguity Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| case | pass | evidence refs | missing evidence | missing answer terms | forbidden |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case['evidence_refs']}` | "
            f"`{case['missing_evidence']}` | `{case['missing_answer_terms']}` | `{case['forbidden_hits']}` |"
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
                f"Retrieval refs: `{case['retrieval_refs']}`",
                "",
                f"Evidence refs: `{case['evidence_refs']}`",
                "",
            ]
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "repo_publish_permission_ambiguity_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            for ref, fixture in FIXTURES.items():
                pipeline.teach(
                    fixture["text"],
                    source=fixture["source"],
                    namespace=namespace,
                    agent_id="repo_publish_permission_ambiguity_regression",
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
