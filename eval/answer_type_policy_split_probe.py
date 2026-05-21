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
OUT_JSON = REPO_ROOT / "experiments" / "answer_type_policy_split_probe_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_type_policy_split_probe_report.md"


POLICY_SPLIT_RULE_NAMES = ("github_upload_policy", "calendar_change_policy")


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "answer_type_policy_split_probe.db"
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
        "github_upload_policy": {
            "text": "GitHub uploads require explicit confirmation in the current conversation.",
            "source": "sample/github_upload_policy.md",
        },
        "calendar_change_policy": {
            "text": "Calendar schedule changes require manual approval before changing meeting events.",
            "source": "sample/calendar_change_policy.md",
        },
        "broad_policy_note": {
            "text": "Broad policy note: approvals should be documented.",
            "source": "sample/broad_policy_note.md",
        },
        "github_filename": {
            "text": "GitHub upload report filename should be github_upload_report.md.",
            "source": "sample/github_upload_filename.md",
        },
    }
    ids: dict[str, str] = {}
    for ref, fixture in fixtures.items():
        result = pipeline.teach(
            fixture["text"],
            source=fixture["source"],
            namespace=namespace,
            agent_id="answer_type_policy_split_probe",
            store_session=False,
            domain="agent_memory",
            memory_type="procedure",
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


def run_case(
    pipeline: MemoryPipeline,
    namespace: str,
    ids: dict[str, str],
    *,
    case_id: str,
    query: str,
    target_ref: str,
    suppressed_refs: tuple[str, ...],
) -> dict[str, Any]:
    rows = pipeline.retrieve(query, top_k=8, namespace=namespace, include_global=False)
    by_id = {row["memory_id"]: row for row in rows}
    target_row = by_id.get(ids[target_ref])
    target_rank = rank_for(rows, ids[target_ref])
    suppressed = []
    for ref in suppressed_refs:
        row = by_id.get(ids[ref])
        suppressed.append(
            {
                "ref": ref,
                "rank": rank_for(rows, ids[ref]),
                "score": None if row is None else row.get("score"),
                "claim_scope_score": None if row is None else row.get("claim_scope_score"),
                "answer_type_score": None if row is None else row.get("answer_type_score"),
            }
        )

    passed = target_rank == 1 and target_row is not None and float(target_row.get("answer_type_score") or 0.0) > 0.0
    for item in suppressed:
        if target_rank is None or item["rank"] is None:
            passed = False
        elif item["rank"] <= target_rank:
            passed = False
        if item["answer_type_score"] is not None and float(item["answer_type_score"]) > 0.0:
            passed = False

    return {
        "case_id": case_id,
        "query": query,
        "passed": passed,
        "target_ref": target_ref,
        "target_rank": target_rank,
        "target_answer_type_score": None if target_row is None else target_row.get("answer_type_score"),
        "suppressed": suppressed,
        "retrieved": [
            {
                "rank": idx,
                "ref": ref_for_memory(ids, row.get("memory_id")),
                "score": row.get("score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "source": row.get("source"),
                "text": row.get("text"),
            }
            for idx, row in enumerate(rows, start=1)
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Answer Type Policy Split Probe",
        "",
        f"Passed: **{report['ok']}**",
        f"Cases: `{report['case_count']}`",
        "",
        "This regression verifies the live answer-type config keeps narrow policy rules separate from broad policy and filename memories.",
        "",
        "| case | pass | target | target rank | target answer-type | suppressed |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        suppressed = ", ".join(
            f"{item['ref']} rank={item['rank']} answer={item['answer_type_score']}"
            for item in case["suppressed"]
        )
        lines.append(
            f"| `{case['case_id']}` | `{case['passed']}` | `{case['target_ref']}` | "
            f"{case['target_rank']} | {case['target_answer_type_score']} | {suppressed or 'none'} |"
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
    namespace = "answer_type_policy_split_probe"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            ids = teach_fixture(pipeline, namespace)
            cases = [
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="github_policy_prefers_upload_rule",
                    query="What is the GitHub upload policy?",
                    target_ref="github_upload_policy",
                    suppressed_refs=("calendar_change_policy", "broad_policy_note", "github_filename"),
                ),
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="github_uploading_prefers_upload_rule",
                    query="What should happen before uploading to GitHub?",
                    target_ref="github_upload_policy",
                    suppressed_refs=("calendar_change_policy", "broad_policy_note", "github_filename"),
                ),
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="calendar_policy_prefers_calendar_rule",
                    query="What calendar change policy should Hermes follow?",
                    target_ref="calendar_change_policy",
                    suppressed_refs=("github_upload_policy", "broad_policy_note", "github_filename"),
                ),
                run_case(
                    pipeline,
                    namespace,
                    ids,
                    case_id="calendar_events_prefers_calendar_rule",
                    query="What should happen before changing calendar events?",
                    target_ref="calendar_change_policy",
                    suppressed_refs=("github_upload_policy", "broad_policy_note", "github_filename"),
                ),
            ]
        finally:
            pipeline.close()

    report = {
        "ok": all(case["passed"] for case in cases),
        "case_count": len(cases),
        "policy_rules": list(POLICY_SPLIT_RULE_NAMES),
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
