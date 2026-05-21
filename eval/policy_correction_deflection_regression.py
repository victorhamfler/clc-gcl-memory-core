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


OUT_JSON = REPO_ROOT / "experiments" / "policy_correction_deflection_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "policy_correction_deflection_regression_report.md"


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "policy_correction_deflection.db"
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


def source_ref(row: dict[str, Any]) -> str | None:
    source = str(row.get("source") or "")
    if source == "policy/github_upload_policy.md":
        return "github_upload_policy"
    if source == "policy/calendar_change_policy.md":
        return "calendar_change_policy"
    if source == "pressure/github_issue_note.md":
        return "github_issue_note"
    if source == "pressure/calendar_attendance_note.md":
        return "calendar_attendance_note"
    if source.startswith("correction:") and "github issue notes" in str(row.get("text") or "").lower():
        return "github_issue_note_correction"
    if source.startswith("correction:") and "calendar attendance notes" in str(row.get("text") or "").lower():
        return "calendar_attendance_note_correction"
    return None


def compact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": idx,
            "ref": source_ref(row),
            "score": row.get("score"),
            "claim_scope_score": row.get("claim_scope_score"),
            "answer_type_score": row.get("answer_type_score"),
            "scope_deflection_penalty": row.get("scope_deflection_penalty"),
            "source": row.get("source"),
            "text": row.get("text"),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def run_case(pipeline: MemoryPipeline, namespace: str, query: str, expected_ref: str, required_text: str) -> dict[str, Any]:
    rows = pipeline.retrieve(query, top_k=8, namespace=namespace, include_global=False)
    answer = pipeline.ask(query, top_k=8, namespace=namespace, include_global=False, store_session=False)
    evidence = answer.get("evidence") or []
    top_ref = source_ref(rows[0]) if rows else None
    evidence_ref = source_ref(evidence[0]) if evidence else None
    answer_text = str(answer.get("answer") or "")
    passed = top_ref == expected_ref and evidence_ref == expected_ref and required_text.lower() in answer_text.lower()
    return {
        "query": query,
        "passed": passed,
        "expected_ref": expected_ref,
        "retrieval_top_ref": top_ref,
        "answer_top_ref": evidence_ref,
        "answer": answer_text,
        "retrieved": compact(rows),
        "evidence": compact(evidence),
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Policy Correction Deflection Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "| query | pass | expected | retrieval top | answer top |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['query']}` | `{case['passed']}` | `{case['expected_ref']}` | "
            f"`{case['retrieval_top_ref']}` | `{case['answer_top_ref']}` |"
        )
    lines.extend(["", "## Details", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['query']}",
                "",
                f"Answer: {case['answer']}",
                "",
                "| rank | ref | score | answer-type | deflection penalty | source |",
                "| ---: | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for row in case["retrieved"][:5]:
            lines.append(
                f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['answer_type_score']} | "
                f"{row['scope_deflection_penalty']} | `{row['source']}` |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    namespace = "policy_correction_deflection_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            github = pipeline.teach(
                "GitHub uploads require explicit confirmation in the current conversation before any upload action.",
                source="policy/github_upload_policy.md",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="procedure",
            )
            issue = pipeline.teach(
                "GitHub issue notes can mention upload blockers, but they do not authorize repository uploads.",
                source="pressure/github_issue_note.md",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )
            calendar = pipeline.teach(
                "Calendar schedule changes require manual approval before changing meeting events.",
                source="policy/calendar_change_policy.md",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="procedure",
            )
            attendance = pipeline.teach(
                "Calendar attendance notes record who joined a meeting but do not change meeting events.",
                source="pressure/calendar_attendance_note.md",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )
            pipeline.correct(
                "GitHub issue notes can mention upload blockers, but they are not permission to upload to the repository.",
                target_memory_ids=[issue["memory"]["memory_id"]],
                target_query="What GitHub upload policy should Hermes follow?",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )
            pipeline.correct(
                "Calendar attendance notes preserve attendees only; changing meeting events still follows the separate calendar policy.",
                target_memory_ids=[attendance["memory"]["memory_id"]],
                target_query="What calendar change policy should Hermes follow?",
                namespace=namespace,
                agent_id="policy_correction_deflection_regression",
                store_session=False,
                domain="agent_memory",
                memory_type="semantic_note",
            )
            cases = [
                run_case(
                    pipeline,
                    namespace,
                    "What GitHub upload policy should Hermes follow?",
                    "github_upload_policy",
                    "explicit confirmation",
                ),
                run_case(
                    pipeline,
                    namespace,
                    "Can Hermes upload to GitHub automatically?",
                    "github_upload_policy",
                    "explicit confirmation",
                ),
                run_case(
                    pipeline,
                    namespace,
                    "What calendar change policy should Hermes follow?",
                    "calendar_change_policy",
                    "manual approval",
                ),
            ]
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
