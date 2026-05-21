from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_outcome_replay_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_outcome_replay_eval_report.md"
POSITIVE_LABELS = {"accepted", "correct", "excellent", "good", "helpful", "useful"}
NEGATIVE_LABELS = {"bad", "incomplete", "incorrect", "missing_source", "stale", "wrong", "wrong_domain"}
PROMOTED_SLOTS = {
    "backend_port",
    "calendar_change",
    "csd",
    "deadline",
    "gcl_curvature",
    "github_upload",
}


def default_log_path() -> Path:
    config = load_config(ROOT)
    cfg = config.get("outcome_log") if isinstance(config.get("outcome_log"), dict) else {}
    return resolve_project_path(ROOT, cfg.get("path"), "logs/memory_outcomes.jsonl")


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            events.append(
                {
                    "operation_id": f"parse_error_{line_no}",
                    "event_type": "parse_error",
                    "payload": {"line_no": line_no, "error": str(exc)},
                }
            )
    return events


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def feedback_signal(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    feedback = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else {}
    label = str(request.get("label") or feedback.get("label") or "").strip().lower()
    memory_id = str(request.get("memory_id") or feedback.get("memory_id") or "").strip() or None
    try:
        rating = float(request.get("rating", feedback.get("rating", 0.0)) or 0.0)
    except (TypeError, ValueError):
        rating = 0.0
    if label in POSITIVE_LABELS or rating >= 0.5:
        kind = "positive"
    elif label in NEGATIVE_LABELS or rating <= -0.5:
        kind = "negative"
    else:
        kind = "unclear"
    return {
        "kind": kind,
        "label": label,
        "rating": rating,
        "memory_id": memory_id,
        "rank": request.get("rank"),
        "retrieval_score": request.get("retrieval_score"),
        "notes": request.get("notes"),
    }


def retrieval_rows(source_event: dict[str, Any]) -> list[dict[str, Any]]:
    payload = event_payload(source_event)
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    out = []
    seen = set()
    for section in ("raw_results", "evidence", "source_context", "stale_context"):
        for row in response.get(section) or []:
            memory_id = str(row.get("memory_id") or "").strip()
            if not memory_id or memory_id in seen:
                continue
            seen.add(memory_id)
            row_copy = dict(row)
            row_copy["_section"] = section
            out.append(row_copy)
    return out


def init_scoring_pipeline(
    tmp: Path,
    claim_scope_config: dict[str, Any],
    answer_type_config: dict[str, Any] | None = None,
) -> MemoryPipeline:
    tmp.mkdir(parents=True, exist_ok=True)
    db_path = tmp / "claim_scope_replay.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        claim_scope_config=claim_scope_config,
        answer_type_config=answer_type_config,
    )


def remove_promoted_slots(pipeline: MemoryPipeline) -> None:
    aliases = dict(pipeline.claim_scope_config.get("slot_aliases") or {})
    excluded = dict(pipeline.claim_scope_config.get("excluded_terms") or {})
    for slot in PROMOTED_SLOTS:
        aliases.pop(slot, None)
        excluded.pop(slot, None)
    pipeline.claim_scope_config["slot_aliases"] = aliases
    pipeline.claim_scope_config["excluded_terms"] = excluded


def legacy_claim_scope_config(config: dict[str, Any]) -> dict[str, Any]:
    claim_scope = json.loads(json.dumps(config.get("claim_scope") or {}))
    aliases = dict(claim_scope.get("slot_aliases") or {})
    excluded = dict(claim_scope.get("excluded_terms") or {})
    for slot in PROMOTED_SLOTS:
        aliases.pop(slot, None)
        excluded.pop(slot, None)
    claim_scope["slot_aliases"] = aliases
    claim_scope["excluded_terms"] = excluded
    return claim_scope


def score_rows(
    query: str,
    rows: list[dict[str, Any]],
    *,
    pipeline: MemoryPipeline,
    claim_weight: float,
    answer_type_weight: float = 0.0,
) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        original_score = float(row.get("score") or 0.0)
        logged_claim = row.get("claim_scope_score")
        try:
            logged_claim_score = float(logged_claim)
        except (TypeError, ValueError):
            logged_claim_score = 0.0
        claim_score = pipeline._claim_scope_affinity(query, str(row.get("text") or ""), str(row.get("source") or ""))
        answer_type_score = pipeline._answer_type_affinity(
            query,
            str(row.get("text") or ""),
            str(row.get("source") or ""),
        )
        adjusted_score = (
            original_score
            - claim_weight * logged_claim_score
            + claim_weight * claim_score
            + answer_type_weight * answer_type_score
        )
        scored.append(
            {
                "memory_id": row.get("memory_id"),
                "source": row.get("source"),
                "authority_state": row.get("authority_state"),
                "text": row.get("text"),
                "original_score": round(original_score, 6),
                "logged_claim_scope_score": round(logged_claim_score, 6),
                "claim_scope_score": round(claim_score, 6),
                "answer_type_score": round(answer_type_score, 6),
                "adjusted_score": round(adjusted_score, 6),
            }
        )
    scored.sort(key=lambda row: row["adjusted_score"], reverse=True)
    for idx, row in enumerate(scored, start=1):
        row["rank"] = idx
    return scored


def row_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("memory_id")): row for row in rows if row.get("memory_id")}


def replay_report(log_path: Path) -> dict[str, Any]:
    config = load_config(ROOT)
    weights = config.get("retrieval_weights") or {}
    claim_weight = float(weights.get("claim_scope", 0.14) or 0.14)
    answer_type_weight = float(weights.get("answer_type", 0.0) or 0.0)
    legacy_config = legacy_claim_scope_config(config)
    current_config = dict(config.get("claim_scope") or {})
    events = load_events(log_path)
    by_operation = {str(event.get("operation_id")): event for event in events if event.get("operation_id")}
    feedback_events = [event for event in events if event.get("event_type") == "feedback"]

    examples = []
    positive_items = []
    negative_items = []
    skipped = []
    with TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        legacy_pipeline = init_scoring_pipeline(tmp / "legacy", legacy_config)
        current_pipeline = init_scoring_pipeline(
            tmp / "current",
            current_config,
            config.get("answer_type") or {},
        )
        remove_promoted_slots(legacy_pipeline)
        try:
            for feedback_event in feedback_events:
                linked_id = str(feedback_event.get("linked_operation_id") or "").strip()
                source_event = by_operation.get(linked_id)
                signal = feedback_signal(feedback_event)
                memory_id = signal.get("memory_id")
                if source_event is None or not memory_id or signal["kind"] == "unclear":
                    skipped.append(
                        {
                            "feedback_operation_id": feedback_event.get("operation_id"),
                            "linked_operation_id": linked_id or None,
                            "reason": "missing_source_memory_or_clear_label",
                            "kind": signal["kind"],
                            "label": signal["label"],
                        }
                    )
                    continue
                payload = event_payload(source_event)
                request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
                query = str(request.get("query") or "").strip()
                rows = retrieval_rows(source_event)
                if not query or not rows:
                    skipped.append(
                        {
                            "feedback_operation_id": feedback_event.get("operation_id"),
                            "linked_operation_id": linked_id,
                            "reason": "missing_query_or_rows",
                            "kind": signal["kind"],
                            "label": signal["label"],
                        }
                    )
                    continue
                legacy_rows = score_rows(query, rows, pipeline=legacy_pipeline, claim_weight=claim_weight)
                current_rows = score_rows(
                    query,
                    rows,
                    pipeline=current_pipeline,
                    claim_weight=claim_weight,
                    answer_type_weight=answer_type_weight,
                )
                legacy_row = row_by_id(legacy_rows).get(memory_id)
                current_row = row_by_id(current_rows).get(memory_id)
                if legacy_row is None or current_row is None:
                    skipped.append(
                        {
                            "feedback_operation_id": feedback_event.get("operation_id"),
                            "linked_operation_id": linked_id,
                            "reason": "feedback_memory_not_in_retrieval_rows",
                            "kind": signal["kind"],
                            "label": signal["label"],
                            "memory_id": memory_id,
                        }
                    )
                    continue
                item = {
                    "query": query,
                    "operation_id": linked_id,
                    "feedback_operation_id": feedback_event.get("operation_id"),
                    "memory_id": memory_id,
                    "kind": signal["kind"],
                    "label": signal["label"],
                    "rating": signal["rating"],
                    "legacy_rank": legacy_row["rank"],
                    "current_rank": current_row["rank"],
                    "rank_delta": legacy_row["rank"] - current_row["rank"],
                    "legacy_claim_scope_score": legacy_row["claim_scope_score"],
                    "current_claim_scope_score": current_row["claim_scope_score"],
                    "current_answer_type_score": current_row["answer_type_score"],
                    "claim_scope_lift": round(
                        current_row["claim_scope_score"] - legacy_row["claim_scope_score"],
                        6,
                    ),
                    "answer_type_lift": current_row["answer_type_score"],
                    "legacy_adjusted_score": legacy_row["adjusted_score"],
                    "current_adjusted_score": current_row["adjusted_score"],
                    "score_delta": round(current_row["adjusted_score"] - legacy_row["adjusted_score"], 6),
                    "source": current_row.get("source"),
                    "authority_state": current_row.get("authority_state"),
                    "text": current_row.get("text"),
                }
                if signal["kind"] == "positive":
                    positive_items.append(item)
                else:
                    negative_items.append(item)
                if item["claim_scope_lift"] != 0.0 or item["rank_delta"] != 0:
                    examples.append(item)
        finally:
            legacy_pipeline.close()
            current_pipeline.close()

    positive_improved = sum(1 for item in positive_items if item["rank_delta"] > 0)
    positive_worse = sum(1 for item in positive_items if item["rank_delta"] < 0)
    negative_suppressed = sum(1 for item in negative_items if item["rank_delta"] < 0)
    negative_promoted = sum(1 for item in negative_items if item["rank_delta"] > 0)
    negative_claim_lift_violations = [
        item for item in negative_items if item["claim_scope_lift"] >= 0.25 and item["rank_delta"] > 0
    ]
    negative_answer_type_violations = [
        item for item in negative_items if item["answer_type_lift"] > 0.0 and item["rank_delta"] > 0
    ]
    accepted_claim_lifts = [item["claim_scope_lift"] for item in positive_items]
    rejected_claim_lifts = [item["claim_scope_lift"] for item in negative_items]
    accepted_answer_type_lifts = [item["answer_type_lift"] for item in positive_items]
    rejected_answer_type_lifts = [item["answer_type_lift"] for item in negative_items]
    return {
        "ok": not negative_claim_lift_violations and not negative_answer_type_violations,
        "log_path": str(log_path),
        "event_count": len(events),
        "feedback_count": len(feedback_events),
        "evaluated_positive": len(positive_items),
        "evaluated_negative": len(negative_items),
        "skipped_count": len(skipped),
        "claim_weight": claim_weight,
        "answer_type_weight": answer_type_weight,
        "promoted_slots_removed_from_legacy": sorted(PROMOTED_SLOTS),
        "metrics": {
            "positive_rank_improved": positive_improved,
            "positive_rank_worse": positive_worse,
            "negative_rank_suppressed": negative_suppressed,
            "negative_rank_promoted": negative_promoted,
            "negative_claim_lift_violations": len(negative_claim_lift_violations),
            "negative_answer_type_violations": len(negative_answer_type_violations),
            "positive_claim_lift_total": round(sum(accepted_claim_lifts), 6),
            "negative_claim_lift_total": round(sum(rejected_claim_lifts), 6),
            "positive_answer_type_lift_total": round(sum(accepted_answer_type_lifts), 6),
            "negative_answer_type_lift_total": round(sum(rejected_answer_type_lifts), 6),
            "positive_claim_lift_avg": round(
                sum(accepted_claim_lifts) / max(1, len(accepted_claim_lifts)),
                6,
            ),
            "negative_claim_lift_avg": round(
                sum(rejected_claim_lifts) / max(1, len(rejected_claim_lifts)),
                6,
            ),
            "positive_answer_type_lift_avg": round(
                sum(accepted_answer_type_lifts) / max(1, len(accepted_answer_type_lifts)),
                6,
            ),
            "negative_answer_type_lift_avg": round(
                sum(rejected_answer_type_lifts) / max(1, len(rejected_answer_type_lifts)),
                6,
            ),
        },
        "top_positive_lifts": sorted(positive_items, key=lambda item: item["claim_scope_lift"], reverse=True)[:12],
        "top_negative_lifts": sorted(negative_items, key=lambda item: item["claim_scope_lift"], reverse=True)[:12],
        "rank_change_examples": sorted(
            examples,
            key=lambda item: (abs(item["rank_delta"]), abs(item["claim_scope_lift"])),
            reverse=True,
        )[:20],
        "negative_claim_lift_violations": negative_claim_lift_violations[:20],
        "negative_answer_type_violations": negative_answer_type_violations[:20],
        "skipped": skipped[:20],
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    metrics = report["metrics"]
    lines = [
        "# Claim Scope Outcome Replay Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Log: `{report['log_path']}`",
        f"Events: `{report['event_count']}`",
        f"Feedback rows: `{report['feedback_count']}`",
        f"Evaluated positives: `{report['evaluated_positive']}`",
        f"Evaluated negatives: `{report['evaluated_negative']}`",
        f"Skipped: `{report['skipped_count']}`",
        f"Claim weight: `{report['claim_weight']}`",
        f"Answer-type weight: `{report['answer_type_weight']}`",
        f"Legacy excludes promoted slots: `{', '.join(report['promoted_slots_removed_from_legacy'])}`",
        "",
        "## Metrics",
        "",
        f"- Positive rank improved: `{metrics['positive_rank_improved']}`",
        f"- Positive rank worse: `{metrics['positive_rank_worse']}`",
        f"- Negative rank suppressed: `{metrics['negative_rank_suppressed']}`",
        f"- Negative rank promoted: `{metrics['negative_rank_promoted']}`",
        f"- Negative claim-lift violations: `{metrics['negative_claim_lift_violations']}`",
        f"- Negative answer-type violations: `{metrics['negative_answer_type_violations']}`",
        f"- Positive claim lift total: `{metrics['positive_claim_lift_total']}`",
        f"- Negative claim lift total: `{metrics['negative_claim_lift_total']}`",
        f"- Positive answer-type lift total: `{metrics['positive_answer_type_lift_total']}`",
        f"- Negative answer-type lift total: `{metrics['negative_answer_type_lift_total']}`",
        "",
        "## Top Positive Lifts",
        "",
        "| claim lift | answer lift | rank delta | label | query | source | text |",
        "| ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for item in report["top_positive_lifts"]:
        lines.append(markdown_item_row(item))
    lines.extend(
        [
            "",
            "## Top Negative Lifts",
            "",
        "| claim lift | answer lift | rank delta | label | query | source | text |",
        "| ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for item in report["top_negative_lifts"]:
        lines.append(markdown_item_row(item))
    lines.extend(
        [
            "",
            "## Rank Change Examples",
            "",
        "| kind | claim lift | answer lift | rank delta | label | query | source |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for item in report["rank_change_examples"]:
        query = clean_cell(item["query"])
        source = clean_cell(item.get("source") or "")
        lines.append(
            f"| `{item['kind']}` | {item['claim_scope_lift']:.6f} | {item['answer_type_lift']:.6f} | {item['rank_delta']} | "
            f"`{item['label']}` | {query} | `{source}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def markdown_item_row(item: dict[str, Any]) -> str:
    return (
        f"| {item['claim_scope_lift']:.6f} | {item['answer_type_lift']:.6f} | {item['rank_delta']} | `{item['label']}` | "
        f"{clean_cell(item['query'])} | `{clean_cell(item.get('source') or '')}` | "
        f"{clean_cell(item.get('text') or '', limit=140)} |"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay linked outcome log rows under legacy vs current claim-scope config.")
    parser.add_argument("--log", default=str(default_log_path()))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = replay_report(Path(args.log))
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "evaluated_positive": report["evaluated_positive"],
                "evaluated_negative": report["evaluated_negative"],
                "metrics": report["metrics"],
                "json": str(out_json),
                "markdown": str(out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
