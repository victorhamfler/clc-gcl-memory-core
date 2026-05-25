from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUT_LOG = REPO_ROOT / "experiments" / "answer_behavior_ogcf_bridge_worklog.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row(memory_id: str, text: str, *, authority_state: str = "standalone", score: float = 0.76) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "rank": 1,
        "namespace": "resolver-shadow-ogcf-worklog",
        "source": "resolver_shadow_ogcf_worklog.md",
        "domain_name": "agent_memory",
        "memory_type": "semantic_note",
        "score": score,
        "cosine": None,
        "authority_state": authority_state,
        "claim_scope_score": 0.82,
        "text_match_score": 0.78,
        "intent_match_score": 0.8,
        "correction_relevance_score": 1.0,
        "supersession_score": -0.32 if authority_state == "stale" else 0.0,
        "relation_supersession_score": -0.32 if authority_state == "stale" else 0.0,
        "text": text,
    }


def selector_snapshot(*, ogcf: bool = False, ordinary: bool = False, stale_conflict: float = 0.0, **diagnostics: Any) -> dict[str, Any]:
    base = {
        "retrieval_count": 4,
        "stale_rows": 0,
        "current_rows": 0,
        "stale_ratio": 0.0,
        "current_ratio": 0.0,
        "stale_current_conflict": stale_conflict,
        "contradiction_peak": 0.0,
        "memory_bad_rate": 0.18,
        "probe_drop": 0.04,
        "csd_ratio": 0.75,
        "hard": False,
    }
    if ogcf:
        base.update(
            {
                "ogcf_bridge_overload_score": 0.91,
                "ogcf_effective_affected_memory_ratio": 0.82,
                "ogcf_intent": "ordinary_fact_lookup" if ordinary else "bridge_geometry_query",
                "ogcf_intent_score": 1.0,
                "ogcf_loop_count": 8,
                "ogcf_cluster_count": 2,
            }
        )
    base.update(diagnostics)
    return {
        "ok": True,
        "ogcf_meta_present": any(str(key).startswith("ogcf_") for key in base),
        "decision": {
            "policy": "long_severe_r16_overwrite" if ogcf and not ordinary else "periodic_baseline",
            "action": "LONG_SEVERE_VERIFIED_REFRESH" if ogcf and not ordinary else "PROTECT_PERIODIC",
            "reason": "resolver_shadow_ogcf_worklog",
            "confidence": 0.82,
        },
        "diagnostics": base,
    }


def ask_event(
    *,
    operation_id: str,
    query: str,
    answer: str,
    evidence: list[dict[str, Any]],
    selector: dict[str, Any],
    stale_context: list[dict[str, Any]] | None = None,
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
                "namespace": "resolver-shadow-ogcf-worklog",
                "include_global": False,
                "agent_id": "resolver-shadow-ogcf-worklog",
                "session_id": None,
                "store_session": False,
                "condition_name": "hard_budget144",
                "include_resolver_shadow": True,
            },
            "response": {
                "answer": answer,
                "confidence": 0.72 if evidence else 0.0,
                "conflict": conflict,
                "session_id": None,
                "agent_id": "resolver-shadow-ogcf-worklog",
                "namespace": "resolver-shadow-ogcf-worklog",
                "namespace_warning": None,
                "evidence": evidence,
                "raw_results": evidence + (stale_context or []),
                "source_context": [],
                "stale_context": stale_context or [],
            },
            "selector_snapshot": selector,
        },
    }


def feedback_event(
    *,
    operation_id: str,
    linked_operation_id: str,
    query: str,
    answer: str,
    label: str,
    rating: float,
    selected_memory_ids: list[str],
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


def pair(
    *,
    stem: str,
    query: str,
    answer: str,
    label: str,
    rating: float,
    evidence: list[dict[str, Any]],
    selector: dict[str, Any],
    stale_context: list[dict[str, Any]] | None = None,
    conflict: bool = False,
    notes: str,
) -> list[dict[str, Any]]:
    selected = [str(item.get("memory_id")) for item in evidence if item.get("memory_id")]
    ask_id = f"ask_{stem}"
    return [
        ask_event(
            operation_id=ask_id,
            query=query,
            answer=answer,
            evidence=evidence,
            selector=selector,
            stale_context=stale_context,
            conflict=conflict,
        ),
        feedback_event(
            operation_id=f"fb_{stem}",
            linked_operation_id=ask_id,
            query=query,
            answer=answer,
            label=label,
            rating=rating,
            selected_memory_ids=selected,
            notes=notes,
        ),
    ]


def build_events() -> list[dict[str, Any]]:
    weather_selector = row(
        "mem_ogcf_weather_selector",
        "Bridge synthesis note: weather uncertainty can interact with selector refresh evidence across project clusters.",
    )
    deployment_selector = row(
        "mem_ogcf_deploy_selector",
        "Bridge synthesis note: deployment risk and selector refresh evidence can share a fragile cross-domain path.",
    )
    bridge_room = row(
        "mem_ogcf_bridge_room",
        "Calendar note: Bridge Room is the ordinary location for the Tuesday review.",
    )
    weak_bridge = row(
        "mem_ogcf_weak_bridge",
        "Loose note: the project has a bridge metaphor in one memo title.",
        score=0.42,
    )
    citation_rule = row(
        "mem_ogcf_citation_rule",
        "Resolver shadow rule: supported answers should stay grounded in selected evidence ids.",
    )
    support_rule = row(
        "mem_ogcf_support_rule",
        "Answer support rule: when evidence is selected, Hermes should answer from that evidence and mark uncertainty.",
    )
    current = row(
        "mem_ogcf_current_bridge_policy",
        "Current policy: bridge-risk answers should mention selected evidence and uncertainty when OGCF pressure is high.",
        authority_state="current",
    )
    stale = row(
        "mem_ogcf_stale_bridge_policy",
        "Old policy: bridge-risk answers can be treated like ordinary supported answers.",
        authority_state="stale",
        score=0.5,
    )

    events: list[dict[str, Any]] = []
    events.extend(
        pair(
            stem="supported_citation_rule",
            query="What should supported resolver-shadow answers stay grounded in?",
            answer="Relevant memory indicates: supported answers should stay grounded in selected evidence ids.",
            label="answer_correct",
            rating=1.0,
            evidence=[citation_rule],
            selector=selector_snapshot(),
            notes="Ordinary supported answer should require evidence grounding without bridge warning.",
        )
    )
    events.extend(
        pair(
            stem="supported_uncertainty_rule",
            query="How should Hermes answer when selected evidence exists?",
            answer="Relevant memory indicates: Hermes should answer from selected evidence and mark uncertainty.",
            label="answer_good_citation",
            rating=1.0,
            evidence=[support_rule],
            selector=selector_snapshot(),
            notes="Second supported positive answer gives the bank enough non-bridge answer-quality support.",
        )
    )
    events.extend(
        pair(
            stem="useful_bridge_score",
            query="How can weather uncertainty interact with selector refresh evidence across clusters?",
            answer="Relevant memory indicates: weather uncertainty can interact with selector refresh evidence across project clusters.",
            label="answer_bridge_warning_useful",
            rating=1.0,
            evidence=[weather_selector],
            selector=selector_snapshot(ogcf=True),
            notes="High OGCF bridge score with selected evidence should emit bridge warning.",
        )
    )
    events.extend(
        pair(
            stem="useful_bridge_effective_ratio",
            query="How does deployment risk connect to selector refresh evidence?",
            answer="Relevant memory indicates: deployment risk and selector refresh evidence can share a fragile cross-domain path.",
            label="answer_bridge_warning_useful",
            rating=1.0,
            evidence=[deployment_selector],
            selector=selector_snapshot(
                ogcf=True,
                ogcf_bridge_overload_score=0.4,
                ogcf_effective_affected_memory_ratio=0.76,
                ogcf_intent="cross_domain_bridge_synthesis",
            ),
            notes="Effective affected-memory ratio alone should be enough for a useful bridge warning.",
        )
    )
    events.extend(
        pair(
            stem="ordinary_bridge_room",
            query="What is the location named Bridge Room for the Tuesday review?",
            answer="Relevant memory indicates: Bridge Room is the ordinary location for the Tuesday review.",
            label="answer_bridge_warning_noise",
            rating=-1.0,
            evidence=[bridge_room],
            selector=selector_snapshot(ogcf=True, ordinary=True),
            notes="Bridge as a room/location name should suppress bridge warning even with OGCF-looking metadata.",
        )
    )
    events.extend(
        pair(
            stem="weak_bridge_noise",
            query="Does the memo title mention a bridge metaphor?",
            answer="Relevant memory indicates: the project has a bridge metaphor in one memo title.",
            label="answer_bridge_warning_noise",
            rating=-0.75,
            evidence=[weak_bridge],
            selector=selector_snapshot(
                ogcf=True,
                ogcf_bridge_overload_score=0.31,
                ogcf_effective_affected_memory_ratio=0.12,
                ogcf_intent="weak_geometry_context",
            ),
            notes="Weak OGCF pressure should not emit bridge warning.",
        )
    )
    events.extend(
        pair(
            stem="unsupported_bridge_private",
            query="What private bridge credential links deployment and weather systems?",
            answer="I do not have enough memory evidence to answer that yet.",
            label="answer_missing_support",
            rating=-0.75,
            evidence=[],
            selector=selector_snapshot(ogcf=True),
            notes="No selected evidence should preserve refusal and avoid bridge warning.",
        )
    )
    events.extend(
        pair(
            stem="stale_bridge_conflict",
            query="What is the current bridge-risk answer policy?",
            answer="Relevant memory indicates: current policy requires selected evidence and uncertainty when OGCF pressure is high.",
            label="answer_bridge_warning_useful",
            rating=1.0,
            evidence=[current],
            stale_context=[stale],
            conflict=True,
            selector=selector_snapshot(ogcf=True, stale_conflict=0.44, stale_rows=1, current_rows=1),
            notes="High bridge pressure plus stale/current conflict should emit bridge warning and stale disclosure.",
        )
    )
    return events


def write_jsonl(events: list[dict[str, Any]], out_log: Path) -> None:
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create live-log-shaped OGCF bridge answer-behavior fixtures.")
    parser.add_argument("--out-log", default=str(OUT_LOG))
    args = parser.parse_args()
    out_log = Path(args.out_log)
    events = build_events()
    write_jsonl(events, out_log)
    print(json.dumps({"ok": True, "event_count": len(events), "answer_feedback_cases": len(events) // 2, "log": str(out_log)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
