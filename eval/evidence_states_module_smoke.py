from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.evidence_states import (  # noqa: E402
    classify_memory_state,
    evidence_is_too_weak,
    normalize_evidence_state_config,
    requires_sensitive_evidence,
)
from core.resolver import classify_memory_state as resolver_classify_memory_state  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "evidence_states_module_smoke_results.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_states_module_smoke_report.md"


def row(**kwargs) -> dict:
    out = {
        "score": 0.5,
        "text_match_score": 0.5,
        "intent_match_score": 0.0,
        "supersession_score": 0.0,
        "relation_supersession_score": 0.0,
        "summary_relation_score": 0.0,
        "feedback_score": 0.0,
        "text": "Historical note.",
        "authority_state": "",
    }
    out.update(kwargs)
    return out


def main() -> int:
    custom_config = normalize_evidence_state_config(
        {
            "current_threshold": 0.8,
            "stale_threshold": -0.6,
            "stale_feedback_threshold": -0.9,
            "disputed_feedback_threshold": -0.4,
            "stale_language_terms": "retired truth",
            "correction_language_terms": "replacement:",
            "sensitive_lookup_terms": "routing,contact",
            "weak_evidence": {
                "score_threshold": 0.4,
                "text_match_threshold": 0.6,
                "intent_match_threshold": 0.9,
                "intent_text_match_threshold": 0.5,
            },
        }
    )
    cases = [
        ("authority_current", row(authority_state="current"), "current"),
        ("authority_superseded", row(authority_state="superseded"), "stale"),
        ("superseded_by_ids", row(superseded_by_memory_ids=["mem_new"]), "stale"),
        ("summary_prefix", row(text="Consolidated summary: source memory ids: mem_a"), "summary"),
        ("summary_relation", row(summary_relation_score=0.5, text="Topic summary. Source memory ids: mem_a"), "summary"),
        ("negative_supersession", row(supersession_score=-0.5), "stale"),
        ("negative_feedback_stale", row(feedback_score=-0.75), "stale"),
        ("negative_feedback_disputed", row(feedback_score=-0.3), "disputed"),
        ("positive_supersession", row(supersession_score=0.5), "current"),
        ("correction_language", row(text="Correction: use the current policy."), "current"),
        ("old_policy_language", row(text="Old policy memory: no longer current."), "stale"),
        ("plain_historical", row(text="Project note for later reference."), "historical"),
    ]
    checks = []
    for case_id, item, expected in cases:
        direct = classify_memory_state(item)
        via_resolver = resolver_classify_memory_state(item)
        checks.append(
            {
                "id": case_id,
                "expected": expected,
                "direct": direct,
                "via_resolver": via_resolver,
                "ok": direct == expected and via_resolver == expected,
            }
        )
    checks.extend(
        [
            {
                "id": "weak_evidence_low_score",
                "ok": evidence_is_too_weak([row(score=0.1, text_match_score=0.1)]) is True,
            },
            {
                "id": "weak_evidence_authority_signal_not_weak",
                "ok": evidence_is_too_weak([row(score=0.1, text_match_score=0.1, supersession_score=0.5)])
                is False,
            },
            {
                "id": "sensitive_lookup_default_terms",
                "ok": requires_sensitive_evidence("What is the private routing key?") is True,
            },
            {
                "id": "custom_current_threshold",
                "ok": classify_memory_state(row(supersession_score=0.5), custom_config) == "historical",
            },
            {
                "id": "custom_correction_language",
                "ok": classify_memory_state(row(text="Replacement: use the new rule."), custom_config) == "current",
            },
            {
                "id": "custom_stale_language",
                "ok": classify_memory_state(row(text="This is retired truth for the old rule."), custom_config) == "stale",
            },
            {
                "id": "custom_weak_evidence_threshold",
                "ok": evidence_is_too_weak([row(score=0.3, text_match_score=0.55)], custom_config) is True,
            },
            {
                "id": "custom_sensitive_terms",
                "ok": requires_sensitive_evidence("What is the contact route?", config=custom_config) is True,
            },
        ]
    )
    ok = all(check["ok"] for check in checks)
    payload = {"ok": ok, "checks": checks}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Evidence States Module Smoke\n\n"
        + f"Result: {'PASS' if ok else 'FAIL'}\n\n"
        + "\n".join(f"- {check['id']}: {'PASS' if check['ok'] else 'FAIL'}" for check in checks)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**payload, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
