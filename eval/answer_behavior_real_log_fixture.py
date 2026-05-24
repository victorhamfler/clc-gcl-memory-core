from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_LOG = REPO_ROOT / "experiments" / "answer_behavior_real_log_missing_cases.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ask_event(
    *,
    operation_id: str,
    query: str,
    answer: str,
    evidence: list[dict[str, Any]],
    raw_results: list[dict[str, Any]] | None = None,
    stale_context: list[dict[str, Any]] | None = None,
    selector_snapshot: dict[str, Any] | None = None,
    conflict: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": None,
        "event_type": "ask",
        "created_at": now(),
        "payload": {
            "request": {
                "query": query,
                "top_k": 8,
                "namespace": "answer_behavior_shadow_fixture",
                "include_global": False,
                "agent_id": "answer-behavior-shadow-fixture",
                "session_id": None,
                "store_session": False,
                "condition_name": "hard_budget144",
            },
            "response": {
                "answer": answer,
                "confidence": 0.72 if evidence else 0.0,
                "conflict": conflict,
                "session_id": None,
                "agent_id": "answer-behavior-shadow-fixture",
                "namespace": "answer_behavior_shadow_fixture",
                "namespace_warning": None,
                "evidence": evidence,
                "raw_results": raw_results if raw_results is not None else evidence,
                "source_context": [],
                "stale_context": stale_context or [],
            },
            "selector_snapshot": selector_snapshot or base_selector_snapshot(),
        },
    }


def feedback_event(
    *,
    operation_id: str,
    linked_operation_id: str,
    label: str,
    rating: float,
    query: str,
    selected_memory_ids: list[str],
    answer: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "linked_operation_id": linked_operation_id,
        "event_type": "feedback",
        "created_at": now(),
        "payload": {
            "request": {
                "memory_id": "",
                "feedback_scope": "answer",
                "label": label,
                "rating": rating,
                "query": query,
                "rank": None,
                "retrieval_score": None,
                "notes": notes,
                "linked_operation_id": linked_operation_id,
                "selected_memory_ids": selected_memory_ids,
                "answer": answer,
                "answer_summary": answer[:240],
            },
            "feedback": {
                "id": None,
                "memory_id": None,
                "feedback_scope": "answer",
                "label": label,
                "query": query,
                "rating": rating,
                "rank": None,
                "retrieval_score": None,
                "notes": notes,
                "metadata": {"linked_operation_id": linked_operation_id},
                "selected_memory_ids": selected_memory_ids,
            },
        },
    }


def base_selector_snapshot(**diagnostics: Any) -> dict[str, Any]:
    base_diagnostics = {
        "retrieval_count": 3,
        "stale_rows": 0,
        "current_rows": 0,
        "stale_ratio": 0.0,
        "current_ratio": 0.0,
        "contradiction_peak": 0.0,
        "stale_current_conflict": 0.0,
        "memory_bad_rate": 0.18,
        "probe_drop": 0.04,
        "csd_ratio": 0.75,
        "hard": False,
    }
    base_diagnostics.update(diagnostics)
    return {
        "ok": True,
        "ogcf_meta_present": any(str(key).startswith("ogcf_") for key in base_diagnostics),
        "decision": {
            "policy": "periodic_baseline",
            "action": "PROTECT_PERIODIC",
            "reason": "answer_behavior_shadow_fixture",
            "confidence": 0.95,
        },
        "diagnostics": base_diagnostics,
    }


def row(memory_id: str, text: str, *, authority_state: str = "standalone", score: float = 0.7) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "rank": 1,
        "namespace": "answer_behavior_shadow_fixture",
        "source": "answer_behavior_fixture.md",
        "domain_name": "agent_memory",
        "memory_type": "semantic_note",
        "score": score,
        "cosine": None,
        "authority_state": authority_state,
        "claim_scope_score": 0.8,
        "correction_relevance_score": 1.0,
        "supersession_score": -0.3 if authority_state == "stale" else 0.0,
        "relation_supersession_score": -0.3 if authority_state == "stale" else 0.0,
        "text": text,
    }


def case_pair(
    *,
    stem: str,
    query: str,
    answer: str,
    label: str,
    rating: float,
    selected_memory_ids: list[str],
    evidence: list[dict[str, Any]],
    selector_snapshot: dict[str, Any] | None = None,
    stale_context: list[dict[str, Any]] | None = None,
    conflict: bool = False,
    notes: str,
) -> list[dict[str, Any]]:
    ask_id = f"ask_{stem}"
    feedback_id = f"fb_{stem}"
    return [
        ask_event(
            operation_id=ask_id,
            query=query,
            answer=answer,
            evidence=evidence,
            raw_results=evidence + (stale_context or []),
            stale_context=stale_context,
            selector_snapshot=selector_snapshot,
            conflict=conflict,
        ),
        feedback_event(
            operation_id=feedback_id,
            linked_operation_id=ask_id,
            label=label,
            rating=rating,
            query=query,
            selected_memory_ids=selected_memory_ids,
            answer=answer,
            notes=notes,
        ),
    ]


def build_events() -> list[dict[str, Any]]:
    bridge_room = row(
        "mem_bridge_room",
        "Calendar location note: the Bridge Room is the Tuesday audit meeting location.",
    )
    current_policy = row(
        "mem_current_policy",
        "Current policy: Hermes must cite selected evidence ids when support exists.",
        authority_state="current",
        score=0.82,
    )
    stale_policy = row(
        "mem_stale_policy",
        "Old policy: Hermes can answer from broad memory without citing selected evidence.",
        authority_state="stale",
        score=0.48,
    )
    bad_citation = row(
        "mem_citation_rule",
        "Citation rule: answers must cite selected memory ids and mention weak support.",
    )
    wrong_scope = row(
        "mem_calendar_scope",
        "Calendar rule: meeting edits require manual approval before changing events.",
    )

    events: list[dict[str, Any]] = []
    events.extend(
        case_pair(
            stem="bridge_warning_noise",
            query="What is the calendar location named Bridge Room?",
            answer="Relevant memory indicates: the Bridge Room is the Tuesday audit meeting location.",
            label="answer_bridge_warning_noise",
            rating=-1.0,
            selected_memory_ids=["mem_bridge_room"],
            evidence=[bridge_room],
            selector_snapshot=base_selector_snapshot(
                ogcf_bridge_overload_score=0.15,
                ogcf_effective_affected_memory_ratio=0.0,
                ogcf_intent="ordinary_fact_lookup",
                ogcf_intent_score=1.0,
            ),
            notes="Fixture: ordinary fact uses bridge as a location name, so no bridge warning should fire.",
        )
    )
    events.extend(
        case_pair(
            stem="answer_stale",
            query="What is the current evidence citation policy?",
            answer="Relevant memory indicates: current policy requires selected evidence ids. Older notes conflict with this.",
            label="answer_stale",
            rating=-1.0,
            selected_memory_ids=["mem_current_policy"],
            evidence=[current_policy],
            stale_context=[stale_policy],
            selector_snapshot=base_selector_snapshot(
                stale_rows=1,
                current_rows=1,
                stale_ratio=0.5,
                current_ratio=0.5,
                stale_current_conflict=0.45,
            ),
            conflict=True,
            notes="Fixture: stale/current conflict should require disclosure.",
        )
    )
    events.extend(
        case_pair(
            stem="conflict_not_disclosed",
            query="After the correction, how should Hermes cite evidence?",
            answer="Relevant memory indicates: Hermes should cite selected evidence ids.",
            label="answer_conflict_not_disclosed",
            rating=-1.0,
            selected_memory_ids=["mem_current_policy"],
            evidence=[current_policy],
            stale_context=[stale_policy],
            selector_snapshot=base_selector_snapshot(
                stale_rows=1,
                current_rows=1,
                stale_ratio=0.5,
                current_ratio=0.5,
                stale_current_conflict=0.45,
            ),
            conflict=True,
            notes="Fixture: answer omitted conflict disclosure even though stale context existed.",
        )
    )
    events.extend(
        case_pair(
            stem="bad_citation",
            query="What should Hermes cite when memory support exists?",
            answer="Relevant memory indicates: cite the selected memory ids and mention weak support.",
            label="answer_bad_citation",
            rating=-0.75,
            selected_memory_ids=["mem_citation_rule"],
            evidence=[bad_citation],
            notes="Fixture: selected evidence exists, so an evidence-backed answer action should be required.",
        )
    )
    events.extend(
        case_pair(
            stem="wrong_scope",
            query="Can Hermes edit a meeting without approval?",
            answer="Relevant memory indicates: meeting edits require manual approval before changing events.",
            label="answer_wrong_scope",
            rating=-0.75,
            selected_memory_ids=["mem_calendar_scope"],
            evidence=[wrong_scope],
            notes="Fixture: selected evidence exists, but label marks answer-level wrong-scope risk for replay coverage.",
        )
    )
    return events


def write_jsonl(events: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create linked ask/answer-feedback fixture logs for shadow replay.")
    parser.add_argument("--out-log", default=str(OUT_LOG))
    args = parser.parse_args()
    out_log = Path(args.out_log)
    events = build_events()
    write_jsonl(events, out_log)
    print(json.dumps({"ok": True, "event_count": len(events), "answer_feedback_cases": len(events) // 2, "log": str(out_log)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
