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
OUT_JSON = REPO_ROOT / "experiments" / "answer_type_config_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_type_config_regression_report.md"


CUSTOM_ANSWER_TYPE = {
    "rules": {
        "deployment_environment": {
            "query_terms": "environment,env,runtime",
            "positive_terms": "production,staging,local,environment,runtime",
            "negative_terms": "owner,owns,assignee,responsible,assignment",
            "positive_score": 1.0,
            "negative_score": -1.0,
        }
    }
}


def init_pipeline(tmp: Path) -> MemoryPipeline:
    db_path = tmp / "answer_type_config.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        retrieval_weights={"vector": 0.16, "text": 0.08, "claim_scope": 0.0, "answer_type": 0.35},
        answer_type_config=CUSTOM_ANSWER_TYPE,
    )


def teach_fixture(pipeline: MemoryPipeline, namespace: str) -> dict[str, str]:
    fixtures = {
        "deployment_environment": {
            "text": "Production is the required runtime.",
            "source": "sample/deployment_environment.md",
        },
        "environment_owner": {
            "text": "Mina owns the deployment note.",
            "source": "sample/environment_owner.md",
        },
        "unrelated_filename": {
            "text": "Deployment report filename should be rollout_plan.md.",
            "source": "sample/deployment_filename.md",
        },
    }
    ids: dict[str, str] = {}
    for ref, fixture in fixtures.items():
        result = pipeline.teach(
            fixture["text"],
            source=fixture["source"],
            namespace=namespace,
            agent_id="answer_type_config_regression",
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


def main() -> int:
    namespace = "answer_type_config_regression"
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp))
        try:
            ids = teach_fixture(pipeline, namespace)
            query = "Which runtime environment should Hermes use?"
            positive_score = pipeline._answer_type_affinity(query, "Production is the required runtime.")
            negative_score = pipeline._answer_type_affinity(query, "Mina owns the deployment note.")
            rows = pipeline.retrieve(query, top_k=6, namespace=namespace, include_global=False)
            target_rank = rank_for(rows, ids["deployment_environment"])
            owner_rank = rank_for(rows, ids["environment_owner"])
            config_view = {
                "rules": sorted(pipeline.answer_type_config["rules"]),
                "custom_query_terms": list(
                    pipeline.answer_type_config["rules"]["deployment_environment"]["query_terms"]
                ),
            }
        finally:
            pipeline.close()

    failures = []
    if positive_score != 1.0:
        failures.append(f"custom positive answer-type score should be 1.0, got {positive_score}")
    if negative_score != -1.0:
        failures.append(f"custom negative answer-type score should be -1.0, got {negative_score}")
    if target_rank != 1:
        failures.append(f"deployment environment target should rank first, got {target_rank}")
    if owner_rank is not None and target_rank is not None and owner_rank <= target_rank:
        failures.append(f"owner distractor should rank below target, got owner={owner_rank} target={target_rank}")
    report = {
        "ok": not failures,
        "query": query,
        "positive_answer_type_score": positive_score,
        "negative_answer_type_score": negative_score,
        "target_rank": target_rank,
        "owner_rank": owner_rank,
        "config_view": config_view,
        "failures": failures,
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
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "target_rank": report["target_rank"],
                "owner_rank": report["owner_rank"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Answer Type Config Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Query: `{report['query']}`",
        f"Positive score: `{report['positive_answer_type_score']}`",
        f"Negative score: `{report['negative_answer_type_score']}`",
        f"Target rank: `{report['target_rank']}`",
        f"Owner rank: `{report['owner_rank']}`",
        f"Failures: `{', '.join(report['failures']) or 'none'}`",
        "",
        "## Retrieved",
        "",
        "| rank | ref | score | answer-type | source | text |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for row in report["retrieved"]:
        text = str(row.get("text") or "").replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['answer_type_score']} | "
            f"`{row['source']}` | {text} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
