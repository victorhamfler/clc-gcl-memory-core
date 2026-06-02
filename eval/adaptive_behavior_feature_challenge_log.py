from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_behavior_shadow import adaptive_behavior_shadow_advisories  # noqa: E402
from core.config import load_config  # noqa: E402


BASE_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_rerun_outcomes.jsonl"
OUT_LOG = REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_outcomes.jsonl"
OUT_COMBINED = REPO_ROOT / "experiments" / "adaptive_behavior_feature_combined_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_log_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_feature_challenge_log_report.md"


@dataclass
class ChallengeContext:
    diagnostics: dict[str, Any]
    retrieval_context: list[dict[str, Any]]
    ogcf_meta_present: bool = False
    ok: bool = True

    def feature_dict(self) -> dict[str, Any]:
        return {
            "memory_bad_rate": self.diagnostics.get("memory_bad_rate", 0.18),
            "probe_drop": self.diagnostics.get("probe_drop", 0.04),
            "csd_ratio": self.diagnostics.get("csd_ratio", 0.75),
        }


def row(
    idx: int,
    *,
    score: float,
    claim: float,
    text: float,
    answer_type: float = 0.0,
    intent: float = 0.0,
    authority: str = "standalone",
    contradiction: float = 0.0,
    scope_deflection: float = 0.0,
    supersession: float = 0.0,
) -> dict[str, Any]:
    return {
        "memory_id": f"challenge_mem_{idx:03d}",
        "rank": idx,
        "namespace": "challenge",
        "source": "eval/adaptive_behavior_feature_challenge_log.py",
        "domain_name": "challenge",
        "memory_type": "challenge_case",
        "score": round(score, 6),
        "cosine": round(score + 0.04, 6),
        "feedback_score": 0.0,
        "usage_count": 0,
        "text_match_score": round(text, 6),
        "intent_match_score": round(intent, 6),
        "answer_type_score": round(answer_type, 6),
        "authority_state": authority,
        "claim_scope_score": round(claim, 6),
        "identifier_match_score": 0.0,
        "broad_generic_penalty": 0.0,
        "scope_deflection_penalty": round(scope_deflection, 6),
        "correction_relevance_score": 1.0,
        "correction_chain_score": 0.0,
        "supersession_score": round(supersession, 6),
        "relation_supersession_score": 0.0,
        "summary_relation_score": 0.0,
        "stored_contradiction_score": round(contradiction, 6),
        "text": f"Challenge evidence {idx}: controlled adaptive behavior feature case.",
    }


def base_diagnostics(rows: list[dict[str, Any]], *, memory_bad_rate: float = 0.18, stale_conflict: float = 0.0) -> dict[str, Any]:
    return {
        "retrieval_count": len(rows),
        "memory_bad_rate": memory_bad_rate,
        "stale_current_conflict": stale_conflict,
        "contradiction_peak": max((float(item.get("stored_contradiction_score") or 0.0) for item in rows), default=0.0),
        "ogcf_bridge_overload_score": 0.0,
        "ogcf_effective_affected_memory_ratio": 0.0,
        "ogcf_structural_pressure": 0.0,
    }


def challenge_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for idx in range(10):
        evidence = [row(idx, score=0.30 + idx * 0.008, claim=0.48, text=0.52, answer_type=0.15)]
        specs.append(
            {
                "id": f"supported_low_score_positive_{idx}",
                "query": f"What is the supported low-score design note {idx}?",
                "answer": "Relevant memory indicates: the selected evidence directly answers the design note.",
                "label": "answer_correct",
                "evidence": evidence,
                "retrieval": evidence,
                "stale_context": [],
                "diagnostics": base_diagnostics(evidence, memory_bad_rate=0.20),
            }
        )
    for idx in range(10, 20):
        evidence = [row(idx, score=0.58, claim=0.70, text=0.66)]
        stale = [row(idx + 100, score=0.45, claim=0.55, text=0.50, authority="stale", supersession=-0.30)]
        specs.append(
            {
                "id": f"incidental_stale_answer_stale_{idx}",
                "query": f"What should the system do for archived policy {idx}?",
                "answer": "Relevant memory indicates: archived policy is still being shown without enough conflict disclosure.",
                "label": "answer_stale",
                "evidence": evidence,
                "retrieval": [*evidence, *stale],
                "stale_context": stale,
                "diagnostics": base_diagnostics([*evidence, *stale], memory_bad_rate=0.28),
            }
        )
    for idx in range(20, 30):
        evidence = [row(idx, score=0.32, claim=0.46, text=0.48, intent=0.20)]
        diagnostics = base_diagnostics(evidence, memory_bad_rate=0.22)
        diagnostics["ogcf_bridge_overload_score"] = 0.78
        diagnostics["ogcf_effective_affected_memory_ratio"] = 0.72
        diagnostics["ogcf_structural_pressure"] = 0.5616
        specs.append(
            {
                "id": f"bridge_useful_low_support_{idx}",
                "query": f"How does weather uncertainty interact with memory refresh bridge case {idx}?",
                "answer": "Relevant memory indicates: the bridge warning is useful and the evidence should still be treated as supported.",
                "label": "answer_bridge_warning_useful",
                "evidence": evidence,
                "retrieval": evidence,
                "stale_context": [],
                "diagnostics": diagnostics,
                "ogcf_meta_present": True,
            }
        )
    for idx in range(30, 40):
        evidence = [row(idx, score=0.62, claim=0.72, text=0.72)]
        specs.append(
            {
                "id": f"sensitive_selected_positive_{idx}",
                "query": f"What private project note can be cited safely without exposing a secret token {idx}?",
                "answer": "Relevant memory indicates: the selected public evidence is enough and does not expose private material.",
                "label": "answer_correct",
                "evidence": evidence,
                "retrieval": evidence,
                "stale_context": [],
                "diagnostics": base_diagnostics(evidence, memory_bad_rate=0.18),
            }
        )
    for idx in range(40, 50):
        evidence = [row(idx, score=0.42, claim=0.10, text=0.20, scope_deflection=0.35)]
        specs.append(
            {
                "id": f"wrong_scope_selected_negative_{idx}",
                "query": f"Who approved github upload permission case {idx}?",
                "answer": "Relevant memory indicates: selected evidence answers a different policy scope.",
                "label": "answer_wrong_scope",
                "evidence": evidence,
                "retrieval": evidence,
                "stale_context": [],
                "diagnostics": base_diagnostics(evidence, memory_bad_rate=0.24),
            }
        )
    return specs


def make_events(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = load_config(ROOT).get("adaptive_behavior")
    events = []
    now = datetime.now(timezone.utc).isoformat()
    for idx, spec in enumerate(specs):
        op_id = f"op_feature_challenge_{idx:03d}_{spec['id']}"
        feedback_id = f"op_feature_challenge_feedback_{idx:03d}"
        context = ChallengeContext(
            diagnostics=spec["diagnostics"],
            retrieval_context=spec["retrieval"],
            ogcf_meta_present=bool(spec.get("ogcf_meta_present")),
        )
        shadow = adaptive_behavior_shadow_advisories(
            query=spec["query"],
            answer=spec["answer"],
            evidence=spec["evidence"],
            stale_context=spec["stale_context"],
            adaptive_context=context,
            resolver_shadow=None,
            config=config,
        )
        response = {
            "answer": spec["answer"],
            "confidence": 0.70,
            "query": spec["query"],
            "evidence": spec["evidence"],
            "raw_results": spec["retrieval"],
            "stale_context": spec["stale_context"],
            "selector_snapshot": {"diagnostics": spec["diagnostics"]},
            "adaptive_behavior_shadow": shadow,
        }
        events.append(
            {
                "schema_version": 1,
                "operation_id": op_id,
                "linked_operation_id": None,
                "event_type": "ask",
                "created_at": now,
                "payload": {
                    "request": {
                        "query": spec["query"],
                        "top_k": 5,
                        "namespace": "challenge",
                        "include_adaptive_behavior_shadow": True,
                        "log_adaptive_behavior_shadow": True,
                    },
                    "response": response,
                    "adaptive_behavior_shadow": shadow,
                },
            }
        )
        events.append(
            {
                "schema_version": 1,
                "operation_id": feedback_id,
                "linked_operation_id": op_id,
                "event_type": "feedback",
                "created_at": now,
                "payload": {
                    "label": spec["label"],
                    "feedback_scope": "answer",
                    "request": {"linked_operation_id": op_id, "label": spec["label"]},
                    "feedback": {"label": spec["label"], "metadata": {"linked_operation_id": op_id}},
                },
            }
        )
    return events


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) for event in events) + "\n", encoding="utf-8")


def build_report(base_log: Path, out_log: Path, out_combined: Path) -> dict[str, Any]:
    specs = challenge_specs()
    events = make_events(specs)
    write_jsonl(out_log, events)
    if base_log.exists():
        combined_text = base_log.read_text(encoding="utf-8").rstrip() + "\n" + out_log.read_text(encoding="utf-8")
    else:
        combined_text = out_log.read_text(encoding="utf-8")
    out_combined.write_text(combined_text, encoding="utf-8")
    feature_count = 0
    symbolic_wrong_count = 0
    decision_count = 0
    from eval.adaptive_behavior_shadow_real_log_calibration import expected_advisory

    ask_by_id = {event["operation_id"]: event for event in events if event["event_type"] == "ask"}
    for event in events:
        if event["event_type"] != "feedback":
            continue
        ask = ask_by_id.get(str(event.get("linked_operation_id")))
        if not ask:
            continue
        shadow_payload = ((ask.get("payload") or {}).get("adaptive_behavior_shadow") or {})
        diagnostics = shadow_payload.get("diagnostics") if isinstance(shadow_payload.get("diagnostics"), dict) else {}
        if diagnostics.get("evidence_context_features"):
            feature_count += 1
        label = ((event.get("payload") or {}).get("label") or "").lower()
        for decision in shadow_payload.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            decision_count += 1
            expected = expected_advisory(
                label=label,
                behavior_family=str(decision.get("behavior_family") or ""),
                ask_event=ask,
                shadow_payload=shadow_payload,
            )
            symbolic_wrong_count += int(str(decision.get("advisory") or "") != expected)
    return {
        "schema": "adaptive_behavior_feature_challenge_log/v1",
        "ok": bool(events),
        "base_log": str(base_log),
        "challenge_log": str(out_log),
        "combined_log": str(out_combined),
        "challenge_case_count": len(specs),
        "event_count": len(events),
        "feature_export_feedback_count": feature_count,
        "decision_count": decision_count,
        "symbolic_wrong_decision_count": symbolic_wrong_count,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Behavior Feature Challenge Log\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Challenge cases: `{report['challenge_case_count']}`\n"
        + f"Feature-export feedback count: `{report['feature_export_feedback_count']}`\n"
        + f"Symbolic wrong decisions: `{report['symbolic_wrong_decision_count']}` / `{report['decision_count']}`\n"
        + f"Challenge log: `{report['challenge_log']}`\n"
        + f"Combined log: `{report['combined_log']}`\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate hard adaptive-behavior feature logs for learned scorer testing.")
    parser.add_argument("--base-log", type=Path, default=BASE_LOG)
    parser.add_argument("--out-log", type=Path, default=OUT_LOG)
    parser.add_argument("--out-combined", type=Path, default=OUT_COMBINED)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.base_log, args.out_log, args.out_combined)
    write_report(report, args.out_json, args.out_md)
    print(json.dumps({"ok": report["ok"], "combined_log": report["combined_log"], "symbolic_wrong_decision_count": report["symbolic_wrong_decision_count"], "json": str(args.out_json)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
